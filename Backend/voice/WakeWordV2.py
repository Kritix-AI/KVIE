"""
WakeWordV2.py - Energy + WebRTC VAD Wake Word Detection
Uses energy threshold + WebRTC VAD + Whisper STT to detect wake words.

Architecture:
  - Read 100ms frames at 44.1kHz (4410 samples)
  - Batch resample to 16kHz (~1600 samples) using librosa (fast)
  - Split into 30ms WebRTC VAD chunks (480 samples at 16kHz)
  - Any chunk speech -> frame is speech
  - Track consecutive speech/silence frames
  - On silence end -> transcribe with Whisper -> check wake word
"""

import os
import sys
import time
import threading
import numpy as np
import pyaudio
import webrtcvad
from dataclasses import dataclass
from typing import List, Callable, Optional, Dict
from enum import Enum

if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except Exception:
        pass


class WakeWordState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    SPEECH_DETECTED = "speech"
    TRANSCRIBING = "transcribing"
    DETECTED = "detected"
    ERROR = "error"


@dataclass
class WakeWordConfig:
    wake_words: List[str] = None
    sample_rate: int = 44100
    vad_aggressiveness: int = 3      # 0-3
    energy_threshold: int = 2000     # Pre-filter to skip VAD on silence
    vad_speech_frames: int = 2       # Consecutive VAD speech to trigger
    vad_silence_frames: int = 5      # Consecutive VAD silence to end recording
    buffer_seconds: float = 3.0      # Max recording length
    device_index: int = 5
    cooldown_frames: int = 4        # Frames to skip after recording

    @classmethod
    def from_env(cls):
        from dotenv import dotenv_values
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        env = dotenv_values(env_file) if os.path.exists(env_file) else {}

        wake_words_raw = env.get("WakeWords", "hey kritix,hello kritix,listen kritix")
        wake_words = [w.strip().lower() for w in wake_words_raw.split(",") if w.strip()]

        return cls(
            wake_words=wake_words,
            sample_rate=int(env.get("WakeSampleRate", "44100")),
            vad_aggressiveness=int(env.get("WakeVADAggressiveness", "3")),
            energy_threshold=int(env.get("WakeEnergyThreshold", "2000")),
            vad_speech_frames=int(env.get("WakeVADSpeechFrames", "1")),
            vad_silence_frames=int(env.get("WakeVADSilenceFrames", "2")),
            buffer_seconds=float(env.get("WakeBufferSeconds", "3.0")),
            device_index=int(env.get("WakeDeviceIndex", "5")),
            cooldown_frames=int(env.get("WakeCooldownFrames", "10")),
        )


def _resample_441_to_16(pcm_441: np.ndarray) -> np.ndarray:
    """Resample 44100Hz int16 PCM to 16000Hz using scipy."""
    from scipy.signal import resample
    n = int(len(pcm_441) * 16000 / 44100)
    pcm_16 = resample(pcm_441.astype(np.float32), n)
    return np.clip(pcm_16, -32768, 32767).astype(np.int16)


def _check_vad_16k(pcm_16k: np.ndarray, vad: webrtcvad.Vad) -> bool:
    """Check if any 30ms chunk in the 16kHz PCM is speech."""
    chunk = 480  # 30ms @ 16kHz
    for i in range(0, len(pcm_16k) - chunk + 1, chunk):
        if vad.is_speech(pcm_16k[i:i+chunk].tobytes(), 16000):
            return True
    return False


class WakeWordDetectorV2:
    def __init__(
        self,
        callback: Callable[[str], None] = None,
        stop_callback: Callable[[], None] = None,
        config: WakeWordConfig = None,
    ):
        self.config = config or WakeWordConfig.from_env()
        self.callback = callback
        self.stop_callback = stop_callback

        self.state = WakeWordState.IDLE
        self.is_running = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Audio
        self._audio: Optional[pyaudio.PyAudio] = None
        self._stream = None
        self._frame_samples = int(self.config.sample_rate * 0.1)  # 100ms at 44.1kHz

        # VAD
        self._vad = webrtcvad.Vad(self.config.vad_aggressiveness)

        # Detection state
        self._recording = False
        self._audio_buffer: List[bytes] = []
        self._consecutive_speech = 0   # VAD speech counter
        self._consecutive_silence = 0  # VAD silence counter
        self._cooldown = 0             # Frames to skip after recording
        self._energy_speech = 0        # Energy pre-filter counter

        print(f"[WAKE] Wake words: {', '.join(self.config.wake_words)}", flush=True)
        print(f"[WAKE] Device: {self.config.device_index} @ {self.config.sample_rate}Hz", flush=True)
        print(f"[WAKE] Energy threshold: {self.config.energy_threshold}, VAD: {self.config.vad_aggressiveness}", flush=True)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self):
        if self.is_running:
            return
        self._running = True
        self.is_running = True
        self.state = WakeWordState.LISTENING
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        print("[WAKE] Started", flush=True)

    def stop(self):
        self._running = False
        self.is_running = False
        self.state = WakeWordState.IDLE
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        if self._audio:
            try:
                self._audio.terminate()
            except Exception:
                pass
        print("[WAKE] Stopped", flush=True)

    def pause(self):
        self.state = WakeWordState.IDLE

    def resume(self):
        if self.state == WakeWordState.IDLE:
            self.state = WakeWordState.LISTENING

    def enable_follow_up(self, timeout: float = None):
        pass

    def enable_command_mode(self, timeout: int = 300):
        pass

    def get_audio_buffer(self) -> List[bytes]:
        return self._audio_buffer.copy()

    def get_status(self) -> Dict:
        return {
            'state': self.state.value,
            'running': self.is_running,
            'wake_words': self.config.wake_words,
        }

    # ── Core Loop ──────────────────────────────────────────────────────────────

    def _listen_loop(self):
        try:
            self._audio = pyaudio.PyAudio()
            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.config.sample_rate,
                input=True,
                frames_per_buffer=self._frame_samples,
                input_device_index=self.config.device_index,
            )
            print(f"[WAKE] Stream: {self.config.sample_rate}Hz, {self._frame_samples} samples/frame", flush=True)

            while self._running:
                try:
                    frame = self._stream.read(self._frame_samples, exception_on_overflow=False)
                except Exception:
                    time.sleep(0.01)
                    continue

                if self.state == WakeWordState.IDLE:
                    time.sleep(0.05)
                    continue

                # Cooldown: skip frames after a recording ended
                if self._cooldown > 0:
                    self._cooldown -= 1
                    time.sleep(0.001)
                    continue

                self._process_frame(frame)
                time.sleep(0.001)

        except Exception as e:
            print(f"[WAKE] Loop error: {e}", flush=True)
            self.state = WakeWordState.ERROR
        finally:
            if self._stream:
                try:
                    self._stream.close()
                except Exception:
                    pass
            if self._audio:
                try:
                    self._audio.terminate()
                except Exception:
                    pass

    def _process_frame(self, frame: bytes):
        pcm = np.frombuffer(frame, dtype=np.int16)
        energy = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))

        # ── Energy pre-filter ───────────────────────────────────────────────
        if energy > self.config.energy_threshold:
            self._energy_speech += 1
        else:
            self._energy_speech = 0

        # ── VAD ─────────────────────────────────────────────────────────────
        try:
            pcm_16k = _resample_441_to_16(pcm)
            vad_speech = _check_vad_16k(pcm_16k, self._vad)
        except Exception:
            vad_speech = energy > self.config.energy_threshold

        if vad_speech:
            self._consecutive_speech += 1
            self._consecutive_silence = 0
        else:
            self._consecutive_silence += 1

        # ── Speech start: both energy and VAD agree ─────────────────────────
        if not self._recording:
            if (self._energy_speech >= 1
                    and self._consecutive_speech >= self.config.vad_speech_frames):
                self._start_recording()
        # ── Speech end: VAD silence while recording ─────────────────────────
        elif self._consecutive_silence >= self.config.vad_silence_frames:
            self._end_recording()

        # ── Max duration safety ─────────────────────────────────────────────
        max_frames = int(self.config.buffer_seconds * 1000 / 100)
        if self._recording and len(self._audio_buffer) >= max_frames:
            self._end_recording()

    # ── Recording Control ──────────────────────────────────────────────────────

    def _start_recording(self):
        self._recording = True
        self._audio_buffer.clear()
        self._consecutive_silence = 0
        print(f"[WAKE] Speech start", flush=True)

    def _end_recording(self):
        frames = self._audio_buffer
        self._recording = False
        self._cooldown = self.config.cooldown_frames
        self._consecutive_silence = 0
        self._consecutive_speech = 0

        if len(frames) < 5:
            return  # Too short

        self.state = WakeWordState.TRANSCRIBING

        def transcribe_task():
            text = self._transcribe(frames)
            if text:
                print(f"[WAKE] Heard: '{text}'", flush=True)
                matched = self._check_wake_word(text)
                if matched:
                    self._fire_detection(matched)
                else:
                    print("[WAKE] No wake word match", flush=True)
            self.state = WakeWordState.LISTENING

        threading.Thread(target=transcribe_task, daemon=True).start()
        self._audio_buffer.clear()

    # ── STT & Matching ─────────────────────────────────────────────────────────

    def _transcribe(self, frames: List[bytes]) -> str:
        try:
            from Backend.SpeechToText import TranscribePCM

            audio_bytes = b''.join(frames)
            duration = len(audio_bytes) / (self.config.sample_rate * 2)
            if duration < 0.2:
                return ""

            text, _lang = TranscribePCM(audio_bytes, duration, wake_mode=True)
            return text.strip().lower()

        except Exception as e:
            print(f"[WAKE] STT error: {e}", flush=True)
            return ""

    def _check_wake_word(self, text: str) -> Optional[str]:
        if not text:
            return None
        for ww in self.config.wake_words:
            if ww in text:
                return ww
        return None

    def _fire_detection(self, wake_word: str):
        self.state = WakeWordState.DETECTED
        print(f"[WAKE] *** DETECTED: '{wake_word}' ***", flush=True)

        if self.callback:
            try:
                self.callback(wake_word)
            except Exception as e:
                print(f"[WAKE] Callback error: {e}", flush=True)

        def reset():
            time.sleep(0.5)
            self.state = WakeWordState.LISTENING
            self._recording = False
            self._audio_buffer.clear()
            self._consecutive_speech = 0
            self._consecutive_silence = 0

        threading.Thread(target=reset, daemon=True).start()


# ── Legacy Compatibility ────────────────────────────────────────────────────────

_wake_words = ["hey kritix", "hello kritix", "listen kritix"]

def set_wake_words(wake_words: List[str]):
    global _wake_words
    _wake_words = wake_words

def get_active_detector() -> Optional[WakeWordDetectorV2]:
    return None

def is_stream_locked() -> bool:
    return False

def acquire_stream_lock(timeout: float = 30.0) -> bool:
    return True

def release_stream_lock():
    pass


# ── Standalone Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Wake Word V2 — Energy + WebRTC VAD", flush=True)

    detections = []

    def on_wake(word):
        detections.append(word)
        print(f"\n>>> *** WAKE: {word} ***", flush=True)

    config = WakeWordConfig(
        wake_words=["hey kritix", "hello kritix"],
        device_index=5,
        energy_threshold=2000,
        vad_speech_frames=1,
        vad_silence_frames=2,
        cooldown_frames=10,
    )

    d = WakeWordDetectorV2(config=config, callback=on_wake)

    # Patch transcribe to show output
    def debug_transcribe(frames):
        audio_bytes = b''.join(frames)
        dur = len(audio_bytes) / (44100 * 2)
        print(f"[WAKE] Transcribing {dur:.1f}s...", flush=True)
        if dur < 0.2:
            return ""
        try:
            from Backend.SpeechToText import TranscribePCM
            text, _ = TranscribePCM(audio_bytes, dur, wake_mode=True)
            print(f"[WAKE] Heard: '{text.strip()}'", flush=True)
            return text.strip().lower()
        except Exception as e:
            print(f"[WAKE] STT err: {e}", flush=True)
            return ""

    d._transcribe = debug_transcribe
    d.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        d.stop()

    print(f"\nTotal: {len(detections)} detections")
