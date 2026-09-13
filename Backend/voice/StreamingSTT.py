"""KVIE streaming speech-to-text engine.

This module owns the audio-to-transcript boundary. It keeps the streaming
contract independent from the UI and from a particular Whisper backend, so
the same engine can be driven by PyAudio, Tauri, or deterministic tests.
"""

from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional, Tuple, Union


@dataclass(frozen=True)
class TranscriptEvent:
    """A single event emitted by the streaming pipeline."""

    kind: str  # started | partial | final | error | stopped
    text: str = ""
    language: str = ""
    confidence: float = 0.0
    start_ms: int = 0
    end_ms: int = 0
    sequence: int = 0
    error: str = ""


Transcriber = Callable[[bytes, float, str], Union[str, Tuple[str, str], Tuple[str, float]]]


@dataclass
class StreamingSTTConfig:
    sample_rate: int = 16_000
    channels: int = 1
    sample_width_bytes: int = 2
    window_ms: int = 2500       # Whisper needs 2-3s minimum for accurate transcription
    overlap_ms: int = 800       # Large overlap for continuity between windows
    min_chunk_ms: int = 1500    # First partial after 1.5 seconds of speech
    language: str = "auto"

    @property
    def bytes_per_second(self) -> int:
        return self.sample_rate * self.channels * self.sample_width_bytes

    @property
    def window_bytes(self) -> int:
        return int(self.bytes_per_second * self.window_ms / 1000)

    @property
    def stride_bytes(self) -> int:
        stride_ms = self.window_ms - self.overlap_ms
        return int(self.bytes_per_second * stride_ms / 1000)

    @property
    def min_chunk_bytes(self) -> int:
        return int(self.bytes_per_second * self.min_chunk_ms / 1000)


class _FlushRequest:
    def __init__(self) -> None:
        self.done = threading.Event()


class _StopRequest:
    pass


class StreamingSTT:
    """Threaded sliding-window transcription with partial/final events.

    ``push_pcm`` accepts little-endian signed PCM. The default transcriber is
    the existing confidence-aware Faster-Whisper function, while tests and
    future Tauri audio sources can inject their own transcriber.
    """

    def __init__(
        self,
        config: Optional[StreamingSTTConfig] = None,
        transcriber: Optional[Transcriber] = None,
        on_event: Optional[Callable[[TranscriptEvent], None]] = None,
    ) -> None:
        self.config = config or StreamingSTTConfig()
        if self.config.overlap_ms >= self.config.window_ms:
            raise ValueError("overlap_ms must be smaller than window_ms")
        self._transcriber = transcriber or self._default_transcriber
        self._on_event = on_event
        self._queue: queue.Queue[Union[bytes, _FlushRequest, _StopRequest]] = queue.Queue()
        self._events: queue.Queue[TranscriptEvent] = queue.Queue()
        self._buffer = bytearray()
        self._buffer_start_ms = 0
        self._sequence = 0
        self._rolling_text = ""
        self._rolling_confidence = 0.0
        self._rolling_language = ""
        self._silence_count = 0
        self._buffer = bytearray()
        self._buffer_start_ms = 0
        self._callback = None
        self._audio_start_ms = None
        self._last_emit_ms = None
        self._consecutive_empty = 0
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()

    @staticmethod
    def _default_transcriber(audio: bytes, duration: float, language: str):
        from Backend.voice.STT import transcribe_with_confidence

        return transcribe_with_confidence(audio, duration, language)

    @staticmethod
    def _transcribe_fast_with_beam(audio: bytes, duration: float, language: str, min_confidence: float = 0.5):
        """Two-pass transcriber: fast single-beam first, wide-beam retry only on low confidence."""
        from Backend.voice.STT import _transcribe_faster_whisper, transcribe_with_confidence

        text, confidence = transcribe_with_confidence(audio, duration, language)
        if confidence >= min_confidence:
            return text, confidence
        # Low confidence → retry with wider beam (5 beams) using the same audio
        try:
            arr = StreamingSTT._bytes_to_numpy(audio)
            text2, _, conf2 = _transcribe_faster_whisper(StreamingSTT._model_ref, arr, language, beam_size=5)
            if conf2 > confidence:
                return text2, conf2
        except Exception:
            pass
        return text, confidence

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._running

    def start(self) -> None:
        with self._state_lock:
            if self._running:
                return
            self._running = True
            self._worker = threading.Thread(target=self._run, name="kvie-streaming-stt", daemon=True)
            self._worker.start()
        self._emit("started")

    def stop(self, flush: bool = True, timeout: float = 10.0) -> None:
        if not self.is_running:
            return
        if flush:
            self.flush(timeout=timeout)
        self._queue.put(_StopRequest())
        worker = self._worker
        if worker:
            worker.join(timeout=timeout)
        with self._state_lock:
            self._running = False
        self._lock = threading.Lock()
        self._emit("stopped")

    def push_pcm(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._queue.put(bytes(pcm))

    def flush(self, timeout: float = 10.0) -> None:
        if not self.is_running:
            return
        request = _FlushRequest()
        self._queue.put(request)
        if not request.done.wait(timeout):
            raise TimeoutError("streaming STT flush timed out")

    def events(self) -> Iterator[TranscriptEvent]:
        """Yield currently queued events without blocking."""

        while True:
            try:
                yield self._events.get_nowait()
            except queue.Empty:
                return

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if isinstance(item, bytes):
                    self._buffer.extend(item)
                    self._drain_windows(final=False)
                elif isinstance(item, _FlushRequest):
                    self._drain_windows(final=True)
                    item.done.set()
                elif isinstance(item, _StopRequest):
                    return
            finally:
                self._queue.task_done()

    def _drain_windows(self, final: bool) -> None:
        # Phase 1: full window transcribes
        while len(self._buffer) >= self.config.window_bytes:
            window = bytes(self._buffer[: self.config.window_bytes])
            self._transcribe(window, self._buffer_start_ms, final=False)
            self._discard_stride()

        # Phase 2: early draft — enough audio accumulated but not a full window yet.
        # Fire a partial so the client can show the user what we have so far.
        if not final and len(self._buffer) >= self.config.min_chunk_bytes:
            window = bytes(self._buffer)
            duration_ms = int(len(window) / self.config.bytes_per_second * 1000)
            self._transcribe(window, self._buffer_start_ms, final=False, is_draft=True)

        # Phase 3: flush remaining
        if final and self._buffer:
            window = bytes(self._buffer)
            duration_ms = int(len(window) / self.config.bytes_per_second * 1000)
            if duration_ms >= 200:
                self._transcribe(window, self._buffer_start_ms, final=True)
            self._buffer.clear()
            self._buffer_start_ms = 0
            self._rolling_text = ""
            self._rolling_confidence = 0.0
            self._silence_count = 0

    def _discard_stride(self) -> None:
        stride = min(len(self._buffer), self.config.stride_bytes)
        self._buffer = self._buffer[stride:]
        self._buffer_start_ms += int(stride / self.config.bytes_per_second * 1000)

    def _transcribe(self, audio: bytes, start_ms: int, final: bool,
                    is_draft: bool = False) -> None:
        duration = len(audio) / self.config.bytes_per_second
        try:
            result = self._transcriber(audio, duration, self.config.language)
            text, language, confidence = self._normalize_result(result)
            cleaned = text.strip()
            if cleaned:
                self._silence_count = 0
                if language:
                    self._rolling_language = language
                # Skip very low-confidence non-final emissions to reduce noise
                if not final and confidence < 0.15:
                    return
                if self._rolling_confidence < 0.15 and confidence >= 0.35:
                    merged_text = cleaned
                else:
                    merged_text = self._merge_rolling_text(self._rolling_text, cleaned)
                self._rolling_text = merged_text
                self._rolling_confidence = max(self._rolling_confidence, confidence)

                # Compact partial: no timestamps/confidence metadata, just text
                if not final:
                    self._emit("partial", text=merged_text)
                else:
                    self._emit(
                        "final", text=merged_text,
                        language=self._rolling_language or language,
                        confidence=confidence,
                        start_ms=start_ms,
                        end_ms=start_ms + int(duration * 1000),
                    )
                    self._rolling_text = ""
                    self._rolling_confidence = 0.0
                    self._silence_count = 0
            else:
                # Silence window detected — log for telemetry
                self._silence_count += 1
                if self._silence_count >= 2 and self._rolling_text.strip() and not final:
                    # User took a natural pause: finalize the previous sentence
                    self._emit(
                        "final",
                        text=self._rolling_text,
                        language=self._rolling_language,
                        confidence=self._rolling_confidence,
                        start_ms=start_ms,
                        end_ms=start_ms + int(duration * 1000),
                    )
                    self._rolling_text = ""
                    self._rolling_confidence = 0.0
                    self._rolling_language = ""
                    self._silence_count = 0
        except Exception as exc:  # keep audio capture alive after a model error
            self._emit("error", error=str(exc), start_ms=start_ms)

    @staticmethod
    def _normalize_result(result) -> Tuple[str, str, float]:
        """Normalize transcriber output to (text, language, confidence).

        Accepted return shapes from transcribers:
          - str                         → (text, "", 0.0)
          - (str, float)                → (text, "", confidence)
          - (str, str)                  → (text, language, 0.0)
          - (str, float, str) or
            (str, str, float)           → (text, language, confidence)
        """
        if isinstance(result, str):
            return result, "", 0.0

        if not isinstance(result, tuple):
            raise TypeError("transcriber must return text or a tuple")

        if len(result) == 2:
            text, meta = result
            if isinstance(meta, float):
                return str(text), "", max(0.0, min(1.0, meta))
            return str(text), str(meta), 0.0

        if len(result) == 3:
            text, second, third = result
            # (str, str, float)
            if isinstance(second, str) and isinstance(third, float):
                return str(text), second, max(0.0, min(1.0, third))
            # (str, float, str)
            if isinstance(second, float) and isinstance(third, str):
                return str(text), third, max(0.0, min(1.0, second))
            # fallback: treat second as language, third as confidence
            return str(text), str(second), max(0.0, min(1.0, float(third)))

        raise TypeError(f"transcriber returned unexpected tuple of length {len(result)}")

    def _emit(self, kind: str, **kwargs) -> None:
        self._sequence += 1
        event = TranscriptEvent(kind=kind, sequence=self._sequence, **kwargs)
        self._events.put(event)
        if self._on_event:
            try:
                self._on_event(event)
            except Exception:
                pass

    @staticmethod
    def _merge_rolling_text(existing: str, incoming: str) -> str:
        """Merge overlapping Whisper windows without duplicating shared words."""
        left, right = existing.strip(), incoming.strip()
        if not left:
            return right
        if not right:
            return left
        left_lower, right_lower = left.lower(), right.lower()
        if right_lower in left_lower:
            return left
        if left_lower in right_lower:
            return right

        def normalize_w(w: str) -> str:
            return re.sub(r"[^\w]", "", w).lower()

        left_words = re.findall(r"\S+", left)
        right_words = re.findall(r"\S+", right)
        left_clean = [normalize_w(w) for w in left_words if normalize_w(w)]
        right_clean = [normalize_w(w) for w in right_words if normalize_w(w)]

        overlap = 0
        max_check = min(len(left_clean), len(right_clean), 10)
        for size in range(max_check, 0, -1):
            if left_clean[-size:] == right_clean[:size]:
                overlap = size
                break

        if overlap > 0:
            tail = " ".join(right_words[overlap:]).strip()
            if not tail:
                return left
            return f"{left} {tail}".strip()

        return f"{left} {right}".strip()

