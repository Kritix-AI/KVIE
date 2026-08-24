"""
Voice/WakeWord.py - Wake Word Detection
Simple energy-based wake word detection with phonetic matching
"""

import os
import sys
import time
import threading
import re
import numpy as np
from typing import Optional, List, Callable, Tuple
from dataclasses import dataclass, field


@dataclass
class WakeWordConfig:
    """Configuration for wake word detection"""
    wake_words: List[str] = field(default_factory=lambda: ["hey kritix", "hello kritix"])
    sensitivity: float = 0.65
    sample_rate: int = 16000
    energy_threshold: float = 0.05  # Low threshold for float samples
    speech_frames_required: int = 2
    silence_frames_end: int = 10  # More frames before stopping
    min_detection_interval: float = 2.0
    min_audio_duration: float = 0.6  # Longer min duration
    max_audio_duration: float = 5.0  # Longer max duration

    @classmethod
    def from_env(cls):
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
        wake_words_raw = env.get("WakeWords") or "hey kritix,hello kritix,listen kritix"
        wake_words = [w.strip().lower() for w in wake_words_raw.split(",") if w.strip()]
        return cls(wake_words=wake_words)


PHONETIC_KRITIX_VARIANTS = {
    "kritix", "critix", "criticks", "kriticks", "kritik", "critik", "critters",
    "krytix", "kratix", "kreetix", "kriotix", "critic", "kritic", "krytic", "kratik",
    "krityx", "critics", "kritics",
    "crittix", "cretix", "kriktix", "critx", "krdicks", "kridicks", "kutrix",
}

PHONETIC_HEY_VARIANTS = {
    "hey", "he", "hi", "hai", "hye", "hay", "hei", "hello", "hallo", "helo", "hullo",
}


def _phonetic_match(text: str, wake_words: List[str]) -> Tuple[bool, str, str]:
    text_lower = text.lower().strip()
    for wake_word in wake_words:
        if wake_word in text_lower:
            cmd_start = text_lower.find(wake_word) + len(wake_word)
            return True, wake_word, text_lower[cmd_start:].strip()

        parts = wake_word.split()
        text_words = re.findall(r'\b\w+\b', text_lower)

        if "kritix" in wake_word and len(parts) == 2:
            if text_words and text_words[0] in PHONETIC_KRITIX_VARIANTS:
                remaining = text_words[1:]
                if remaining:
                    return True, wake_word, " ".join(remaining).strip()

        matched_parts = []
        text_idx = 0
        for part in parts:
            part_lower = part.lower()
            found = False
            variants = PHONETIC_KRITIX_VARIANTS if "kritix" in part_lower else PHONETIC_HEY_VARIANTS
            search_limit = min(text_idx + 3, len(text_words))

            for i in range(text_idx, search_limit):
                word = text_words[i]
                word_clean = word.rstrip('s').rstrip("'s")
                if word in variants or word_clean in variants or word == part_lower:
                    matched_parts.append(part_lower)
                    text_idx = i + 1
                    found = True
                    break

            if not found:
                break

        if len(matched_parts) == len(parts):
            return True, wake_word, " ".join(text_words[text_idx:]).strip()

    return False, "", ""


# Global state
_active_detector: Optional['WakeWordDetector'] = None
_stream_lock = threading.Lock()
_last_detection_time: float = 0.0


def get_active_detector():
    return _active_detector


def is_stream_locked() -> bool:
    return _stream_lock.locked()


def acquire_stream_lock(timeout: float = 30.0) -> bool:
    return _stream_lock.acquire(timeout=timeout)


def release_stream_lock():
    try:
        _stream_lock.release()
    except Exception:
        pass


def _frame_energy(frame: bytes) -> float:
    """Calculate RMS energy from PCM bytes"""
    if not frame:
        return 0.0
    samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


def _open_input_stream(p, sample_rate: int = 16000, frames_per_buffer: int = 1024, device_index: Optional[int] = None):
    """Open the microphone, retrying with stereo when a device rejects mono."""
    try:
        import pyaudio
        audio_format = pyaudio.paInt16
    except Exception:
        audio_format = 8  # paInt16; keeps the helper testable without PyAudio

    options = {
        "format": audio_format,
        "rate": sample_rate,
        "input": True,
        "frames_per_buffer": frames_per_buffer,
    }
    if device_index is not None:
        options["input_device_index"] = device_index
    try:
        return p.open(channels=1, **options)
    except Exception:
        return p.open(channels=2, **options)


class WakeWordDetector:
    def __init__(
        self,
        callback: Optional[Callable] = None,
        config: Optional[WakeWordConfig] = None,
        stop_callback: Optional[Callable] = None,
        stream_lock: Optional[threading.Lock] = None
    ):
        global _active_detector, _last_detection_time
        self.config = config or WakeWordConfig.from_env()
        self.callback = callback
        self.stop_callback = stop_callback
        self._stream_lock = stream_lock or _stream_lock
        _last_detection_time = 0.0
        self._enabled = True
        self._listening = False
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        _active_detector = self
        print(f"[WAKE] Wake words: {', '.join(self.config.wake_words)}", flush=True)
        print(f"[WAKE] Phonetic matching: ENABLED", flush=True)

    def start(self):
        if self._listening:
            return
        self._stop_flag.clear()
        self._listening = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="WakeWordDetector")
        self._thread.start()
        print("[WAKE] Listening...", flush=True)

    def stop(self):
        self._stop_flag.set()
        self._listening = False
        print("[WAKE] Stopped", flush=True)

    def pause(self):
        self._enabled = False
        print("[WAKE] Paused", flush=True)

    def resume(self):
        self._enabled = True
        if not self._listening:
            self.start()
        print("[WAKE] Resumed", flush=True)

    def is_listening(self) -> bool:
        return self._listening

    def _check_wake_word(self, text: str) -> Optional[str]:
        """Return the configured wake phrase when text contains a match."""
        matched, wake_word, _ = _phonetic_match(text, self.config.wake_words)
        return wake_word if matched else None

    def _listen_loop(self):
        p = None
        stream = None

        try:
            import pyaudio
            p = pyaudio.PyAudio()
            chunk_size = 1024
            stream = _open_input_stream(p, sample_rate=self.config.sample_rate, frames_per_buffer=chunk_size)
            print("[WAKE] Microphone opened", flush=True)
        except Exception as e:
            print(f"[WAKE] Mic error: {e}", flush=True)
            self._listening = False
            return

        # Quick calibration
        print("[WAKE] Calibration...", flush=True)
        noise_energies = []
        for _ in range(20):
            try:
                data = stream.read(chunk_size, exception_on_overflow=False)
                noise_energies.append(_frame_energy(data))
                time.sleep(0.01)
            except Exception:
                break

        # Calculate noise floor
        noise_floor = float(np.median(noise_energies)) if noise_energies else 500.0
        # Lower threshold for better sensitivity
        energy_threshold = max(noise_floor * 1.1, 150.0)

        print(f"[WAKE] Noise floor: {noise_floor:.0f}", flush=True)
        print(f"[WAKE] Threshold: {energy_threshold:.0f}", flush=True)
        print("[WAKE] Ready! Speak clearly...", flush=True)

        speech_count = 0
        recording = False
        audio_frames: List[bytes] = []
        pre_buffer: List[bytes] = []
        pre_buffer_size = 8
        recording_start_time = 0.0
        stop_words = {'stop', 'cancel', 'abort', 'exit', 'quit', 'nevermind'}

        try:
            while not self._stop_flag.is_set():
                if self._stream_lock.locked():
                    time.sleep(0.1)
                    continue

                # Echo cancellation
                try:
                    from Backend.voice.TTS import is_speaking as tts_is_speaking
                    if tts_is_speaking():
                        try:
                            stream.read(chunk_size, exception_on_overflow=False)
                        except Exception:
                            pass
                        time.sleep(0.01)
                        continue
                except ImportError:
                    pass

                try:
                    frame = stream.read(chunk_size, exception_on_overflow=False)
                except OSError:
                    time.sleep(0.05)
                    continue

                energy = _frame_energy(frame)
                is_loud = energy > energy_threshold

                # Update pre-buffer
                pre_buffer.append(frame)
                if len(pre_buffer) > pre_buffer_size:
                    pre_buffer.pop(0)

                # Voice detection
                if not recording:
                    if is_loud:
                        speech_count += 1
                        if speech_count >= self.config.speech_frames_required:
                            recording = True
                            audio_frames = list(pre_buffer)
                            recording_start_time = time.time()
                            print(f"[WAKE] Voice! (E:{energy:.0f})", flush=True)
                    else:
                        speech_count = max(0, speech_count - 1)
                else:
                    elapsed = time.time() - recording_start_time
                    audio_frames.append(frame)

                    # Check for silence - wait longer before stopping
                    if not is_loud:
                        # Check if it's temporary dip or real silence (look back more frames)
                        silence_frames = 1
                        lookback = min(15, len(audio_frames))
                        for i in range(1, lookback):
                            check_frame = audio_frames[-i-1] if len(audio_frames) > i else frame
                            if _frame_energy(check_frame) > energy_threshold * 0.8:
                                silence_frames = 0
                                break

                        if silence_frames and elapsed > self.config.min_audio_duration:
                            print(f"[WAKE] Speech ended ({elapsed:.1f}s)", flush=True)
                            self._process_audio(audio_frames, stop_words)
                            recording = False
                            speech_count = 0
                            audio_frames = []
                            pre_buffer = []
                            continue

                    # Force stop on max duration
                    if elapsed > self.config.max_audio_duration:
                        print(f"[WAKE] Max duration", flush=True)
                        if len(audio_frames) > 10:
                            self._process_audio(audio_frames, stop_words)
                        recording = False
                        speech_count = 0
                        audio_frames = []
                        pre_buffer = []

                time.sleep(0.001)

        finally:
            self._listening = False
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            try:
                p.terminate()
            except Exception:
                pass
            print("[WAKE] Stream closed", flush=True)

    def _process_audio(self, audio_frames: List[bytes], stop_words: set):
        global _last_detection_time

        try:
            from Backend.voice.STT import transcribe
        except ImportError:
            print("[WAKE] STT not available", flush=True)
            return

        try:
            pcm = b''.join(audio_frames)
            duration = len(audio_frames) * 1024 / self.config.sample_rate

            if duration < self.config.min_audio_duration:
                print(f"[WAKE] Too short: {duration:.2f}s", flush=True)
                return

            print(f"[WAKE] Processing {duration:.1f}s...", flush=True)

            text = transcribe(pcm, duration, language="auto")
            if not text:
                print("[WAKE] No speech", flush=True)
                return

            print(f"[WAKE] Heard: '{text}'", flush=True)

            text_lower = text.lower().strip()

            if any(w in text_lower for w in stop_words):
                print("[WAKE] Stop command", flush=True)
                if self.stop_callback:
                    self.stop_callback()
                return

            matched, wake_word, command = _phonetic_match(text, self.config.wake_words)

            if matched:
                current_time = time.time()
                if current_time - _last_detection_time < self.config.min_detection_interval:
                    print("[WAKE] Rate limited", flush=True)
                    return

                _last_detection_time = current_time
                print(f"[WAKE] *** WAKE: {wake_word} ***", flush=True)
                print(f"[WAKE] Command: '{command}'", flush=True)

                try:
                    from Backend.voice.VoiceLearner import VoiceLearner
                    VoiceLearner().learn_wake_success(wake_word, confidence=0.8)
                except Exception:
                    pass

                if self.callback:
                    self.callback(command)
            else:
                print("[WAKE] No wake match", flush=True)
                try:
                    from Backend.voice.VoiceLearner import VoiceLearner
                    VoiceLearner().learn_wake_failure(text)
                except Exception:
                    pass

        except Exception as e:
            print(f"[WAKE] Error: {e}", flush=True)
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("=" * 50, flush=True)
    print("Wake Word Detection", flush=True)
    print("=" * 50, flush=True)

    def on_wake(command):
        print(f"\n[WAKE] *** DETECTED! *** Command: '{command}'", flush=True)

    def on_stop():
        print("\n[WAKE] Stop!", flush=True)

    print("\n[TEST] Phonetic Matching:", flush=True)
    for phrase in ["hey kritix", "hello kritix", "hey critic", "hello critics"]:
        m, w, c = _phonetic_match(phrase, ["hey kritix", "hello kritix", "listen kritix"])
        print(f"  '{phrase}' -> {'MATCH' if m else 'no match'}", flush=True)

    config = WakeWordConfig.from_env()
    detector = WakeWordDetector(callback=on_wake, stop_callback=on_stop, config=config)
    detector.start()

    print("\n[READY] Say 'hey kritix' clearly", flush=True)
    print("[READY] Press Ctrl+C to stop", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[EXIT]", flush=True)
        detector.stop()
