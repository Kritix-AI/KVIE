"""KVIE streaming speech-to-text engine.

This module owns the audio-to-transcript boundary. It keeps the streaming
contract independent from the UI and from a particular Whisper backend, so
the same engine can be driven by PyAudio, Tauri, or deterministic tests.
"""

from __future__ import annotations

import collections
import math
import os
import queue
import re
import struct
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


def _count_speech_bytes(
    pcm_bytes: bytes,
    sample_rate: int = 16_000,
    threshold: float = 200.0,
    channels: int = 1,
    sample_width_bytes: int = 2,
) -> int:
    """Count bytes in 20ms frames whose RMS energy is >= threshold."""
    if not pcm_bytes or threshold <= 0:
        return len(pcm_bytes)

    bytes_per_sample = channels * sample_width_bytes
    frame_samples = max(1, int(sample_rate * 0.02))
    frame_bytes = frame_samples * bytes_per_sample
    if frame_bytes <= 0:
        return len(pcm_bytes)

    speech_bytes = 0
    total_len = len(pcm_bytes)

    try:
        import numpy as np

        for offset in range(0, total_len, frame_bytes):
            chunk = pcm_bytes[offset : offset + frame_bytes]
            usable_bytes = (len(chunk) // bytes_per_sample) * bytes_per_sample
            if usable_bytes == 0:
                break
            dtype = np.int16 if sample_width_bytes == 2 else np.int8
            samples = np.frombuffer(chunk[:usable_bytes], dtype=dtype).astype(np.float32)
            if samples.size == 0:
                break
            rms = float(np.sqrt(np.mean(samples ** 2)))
            if rms >= threshold:
                speech_bytes += len(chunk)
        return speech_bytes
    except Exception:
        pass

    fmt_char = "h" if sample_width_bytes == 2 else "b"
    for offset in range(0, total_len, frame_bytes):
        chunk = pcm_bytes[offset : offset + frame_bytes]
        num_samples = len(chunk) // bytes_per_sample
        if num_samples == 0:
            break
        usable_bytes = num_samples * sample_width_bytes
        samples = struct.unpack(f"<{num_samples}{fmt_char}", chunk[:usable_bytes])
        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / num_samples)
        if rms >= threshold:
            speech_bytes += len(chunk)

    return speech_bytes


Transcriber = Callable[[bytes, float, str], Union[str, Tuple[str, str], Tuple[str, float]]]


@dataclass
class StreamingSTTConfig:
    sample_rate: int = 16_000
    channels: int = 1
    sample_width_bytes: int = 2
    window_ms: int = 2000       # Responsive sliding window
    overlap_ms: int = 600       # Overlap for continuity between windows
    min_chunk_ms: int = 400     # First partial after 0.4 seconds of speech for instant feedback
    draft_interval_ms: int = 250  # 250ms cadence for live real-time partial updates
    language: str = "auto"
    speech_threshold: float = 200.0

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
        # Bounded event log: the service drains nothing from events(), so an
        # unbounded queue would leak memory for every session.
        self._events: "collections.deque[TranscriptEvent]" = collections.deque(maxlen=256)
        self._buffer = bytearray()
        self._audio_bytes_processed = 0
        self._last_draft_processed_bytes = 0
        self._committed_bytes = 0
        self._buffer_start_ms = 0
        self._sequence = 0
        self._rolling_text = ""
        self._rolling_confidence = 0.0
        self._rolling_language = ""
        self._silence_count = 0
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._state_lock = threading.Lock()

    def _count_speech_bytes(self, pcm_bytes: bytes) -> int:
        return _count_speech_bytes(
            pcm_bytes,
            sample_rate=self.config.sample_rate,
            threshold=self.config.speech_threshold,
            channels=self.config.channels,
            sample_width_bytes=self.config.sample_width_bytes,
        )

    @staticmethod
    def _default_transcriber(audio: bytes, duration: float, language: str):
        from Backend.voice.STT import transcribe_with_confidence
        from Backend.voice import STT

        # retry=False: the streaming worker must never block on the expensive
        # beam-5 retry, or flushes time out and the session's final text dies.
        result = transcribe_with_confidence(audio, duration, language, retry=False)
        if duration >= 0.3 and not STT.is_loaded():
            raise RuntimeError(
                "The selected speech model could not be loaded. Check the Models page and select an installed STT model."
            )
        return result

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
                yield self._events.popleft()
            except IndexError:
                return

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if isinstance(item, bytes):
                    self._buffer.extend(item)
                    self._audio_bytes_processed += len(item)
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
            if not self._buffer:
                # Buffer was cleared (e.g. pause finalization)
                break
            self._committed_bytes = self._audio_bytes_processed - len(self._buffer) + self.config.window_bytes
            self._discard_stride()

        # Compute speech bytes in uncommitted audio for Phase 2 & 3
        new_bytes = max(0, min(len(self._buffer), self._audio_bytes_processed - self._committed_bytes))
        uncommitted_pcm = bytes(self._buffer[-new_bytes:]) if new_bytes > 0 else b""
        new_speech_bytes = self._count_speech_bytes(uncommitted_pcm)
        min_speech_bytes = int(self.config.bytes_per_second * 0.2)

        # Phase 2: early draft — enough audio accumulated but not a full window yet.
        # Fire a partial so the client can show the user what we have so far.
        draft_interval_bytes = int(
            self.config.bytes_per_second * self.config.draft_interval_ms / 1000
        )
        if (
            not final
            and len(self._buffer) >= self.config.min_chunk_bytes
            and self._audio_bytes_processed - self._last_draft_processed_bytes >= draft_interval_bytes
            and new_speech_bytes >= min_speech_bytes
        ):
            window = bytes(self._buffer)
            self._transcribe(window, self._buffer_start_ms, final=False, is_draft=True)
            self._last_draft_processed_bytes = self._audio_bytes_processed

        # Phase 3: flush remaining
        if final:
            if self._buffer:
                window = bytes(self._buffer)
                duration_ms = int(len(window) / self.config.bytes_per_second * 1000)
                if duration_ms >= 200 and new_speech_bytes >= min_speech_bytes:
                    self._transcribe(window, self._buffer_start_ms, final=True)
                self._buffer.clear()
                self._buffer_start_ms = 0
            # If the trailing window was silence (or too short to transcribe),
            # any text accumulated in the rolling buffer would otherwise be
            # discarded here — emit it as the session's final transcript.
            if self._rolling_text.strip():
                self._emit(
                    "final",
                    text=self._rolling_text,
                    language=self._rolling_language,
                    confidence=self._rolling_confidence,
                    start_ms=self._buffer_start_ms,
                    end_ms=self._buffer_start_ms,
                )
                self._rolling_text = ""
                self._rolling_confidence = 0.0
                self._rolling_language = ""
            self._silence_count = 0
            self._audio_bytes_processed = 0
            self._last_draft_processed_bytes = 0
            self._committed_bytes = 0

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
                if os.environ.get("KVIE_TRACE_STAGES") == "1":
                    import sys
                    print(f"[STAGE 1: RAW STT] duration={duration:.2f}s is_draft={is_draft} lang={language or self.config.language!r} conf={confidence:.2f} text={cleaned!r}", file=sys.stderr, flush=True)

                self._silence_count = 0
                if language and not is_draft:
                    self._rolling_language = language
                # Skip very low-confidence non-final emissions to reduce noise
                if not final and confidence < 0.15:
                    return
                if self._rolling_confidence < 0.15 and confidence >= 0.35:
                    merged_text = cleaned
                else:
                    merged_text = self._merge_rolling_text(self._rolling_text, cleaned)

                if os.environ.get("KVIE_TRACE_STAGES") == "1":
                    import sys
                    kind = "partial (draft)" if is_draft else ("final" if final else "partial (window)")
                    print(f"[STAGE 2: BACKEND MERGED] kind={kind!r} emitted={merged_text!r} rolling_prior={self._rolling_text!r}", file=sys.stderr, flush=True)

                if is_draft:
                    self._emit("partial", text=merged_text)
                    return

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
            elif not is_draft:
                # Silence window detected — log for telemetry
                self._silence_count += 1
                if self._silence_count >= 2 and self._rolling_text.strip() and not final:
                    if os.environ.get("KVIE_TRACE_STAGES") == "1":
                        import sys
                        print(f"[STAGE 2: BACKEND MERGED] kind='final (pause)' emitted={self._rolling_text!r}", file=sys.stderr, flush=True)
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
                    self._buffer.clear()
                    self._buffer_start_ms = 0
                    self._committed_bytes = self._audio_bytes_processed
        except Exception as exc:  # keep audio capture alive after a model error
            message = str(exc).strip() or type(exc).__name__
            self._emit("error", error=f"Transcription failed: {message[:240]}", start_ms=start_ms)

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
        self._events.append(event)
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

        has_terminal_punct = bool(re.search(r"[\.!\?]\s*$", left))

        # Check 1: Exact suffix-to-prefix match between left_clean[-size:] and right_clean[:size]
        overlap = 0
        max_check = min(len(left_clean), len(right_clean), 10)
        for size in range(max_check, 0, -1):
            if left_clean[-size:] == right_clean[:size]:
                overlap = size
                break

        # Check 2: Fuzzy suffix-to-prefix match at index 0 of right_clean using similar()
        if overlap == 0:
            try:
                from difflib import SequenceMatcher

                def similar(a: str, b: str) -> bool:
                    if not a or not b:
                        return False
                    return SequenceMatcher(None, a, b).ratio() >= 0.72

                max_fuzzy = min(len(left_clean), len(right_clean), 5)
                for size in range(max_fuzzy, 0, -1):
                    if all(
                        similar(left_clean[-size + i], right_clean[i])
                        for i in range(size)
                    ):
                        overlap = size
                        break
            except Exception:
                pass

        # If left ends with terminal punctuation, a single-word match across the boundary
        # is a valid sentence beginning, not a sliding-window overlap.
        # Preserve text when ambiguous; require size >= 2 for cross-sentence overlap.
        clause_starters = {
            "i", "we", "you", "he", "she", "it", "they", "there", "this", "that",
            "will", "would", "shall", "should", "can", "could", "do", "did", "does",
            "is", "are", "was", "were", "have", "has", "had", "not", "am"
        }
        is_new_sentence_or_clause = bool(
            right_words and (
                right_words[0][0].isupper()
                or right_words[0].endswith((",", ";", ":", "!", "?"))
                or (len(right_words) > 1 and right_words[1].lower().rstrip(".,!?") in clause_starters)
            )
        )
        if has_terminal_punct and overlap < 2 and is_new_sentence_or_clause:
            overlap = 0

        if overlap > 0:
            tail = " ".join(right_words[overlap:]).strip()
            if not tail:
                return left
            return f"{left} {tail}".strip()

        # If no overlap, concatenate
        return f"{left} {right}".strip()
