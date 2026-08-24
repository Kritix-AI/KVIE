"""
Voice/WakeWordML.py - ML-Based Wake Word Detection (End-to-End)
Combines DSP preprocessing, ML model inference, and real-time detection.
"""

import os
import sys
import time
import threading
import numpy as np
import pyaudio
from typing import List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

if sys.platform == 'win32':
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except Exception:
        pass


class WakeWordState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    BUFFERING = "buffering"
    DETECTED = "detected"


@dataclass
class WakeWordMLConfig:
    """Configuration for ML wake word detector."""
    wake_words: List[str] = None
    sample_rate: int = 16000
    frame_ms: int = 80
    energy_threshold: int = 500
    silence_frames: int = 4
    buffer_frames: int = 64  # Number of frames for ML model
    ml_threshold: float = 0.7  # Probability threshold
    cooldown_frames: int = 30
    device_index: int = 5
    model_path: str = "models/wake_word/wake_word_model.tflite"

    def __post_init__(self):
        if self.wake_words is None:
            self.wake_words = ["hey_kritix", "hello_kritix"]


class WakeWordMLDetector:
    """
    ML-based wake word detection with real-time streaming.
    Uses energy-based VAD + ML model for accurate detection.
    """

    def __init__(
        self,
        callback: Callable[[str], None] = None,
        config: WakeWordMLConfig = None,
    ):
        self.config = config or WakeWordMLConfig()
        self.callback = callback

        self.state = WakeWordState.IDLE
        self.is_running = False
        self._running = False
        self._thread = None

        # Audio
        self._audio = None
        self._stream = None
        self._frame_samples = int(self.config.sample_rate * self.config.frame_ms / 1000)

        # ML model
        self._model = None
        self._load_model()

        # Detection state
        self._consecutive_speech = 0
        self._audio_buffer = []
        self._cooldown = 0
        self._peak_energy = 0.0

        print(f"[WAKE-ML] Wake words: {self.config.wake_words}")
        print(f"[WAKE-ML] Device: {self.config.device_index} @ {self.config.sample_rate}Hz")
        print(f"[WAKE-ML] Model: {self.config.model_path}")

    def _load_model(self):
        """Load TensorFlow Lite model."""
        import tensorflow as tf

        if os.path.exists(self.config.model_path):
            try:
                self._interpreter = tf.lite.Interpreter(model_path=self.config.model_path)
                self._interpreter.allocate_tensors()
                self._input_details = self._interpreter.get_input_details()
                self._output_details = self._interpreter.get_output_details()
                print("[WAKE-ML] TFLite model loaded")
            except Exception as e:
                print(f"[WAKE-ML] Model load failed: {e}")
                self._interpreter = None
        else:
            print(f"[WAKE-ML] Model not found: {self.config.model_path}")
            self._interpreter = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self.is_running:
            return
        self._running = True
        self.is_running = True
        self.state = WakeWordState.LISTENING
        self._thread = threading.Thread(target=self._listen_loop, daemon=False)
        self._thread.start()
        print("[WAKE-ML] Started")

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
        if self._thread:
            self._thread.join(timeout=2.0)
        print("[WAKE-ML] Stopped")

    # ── Core Loop ─────────────────────────────────────────────────────────────

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

            while self._running:
                try:
                    frame = self._stream.read(self._frame_samples, exception_on_overflow=False)
                except Exception:
                    time.sleep(0.01)
                    continue

                if self.state == WakeWordState.IDLE or self._cooldown > 0:
                    if self._cooldown > 0:
                        self._cooldown -= 1
                    time.sleep(0.001)
                    continue

                self._process_frame(frame)
                time.sleep(0.001)

        except Exception as e:
            print(f"[WAKE-ML] Loop error: {e}")
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

    def _compute_energy(self, frame: bytes) -> float:
        pcm = np.frombuffer(frame, dtype=np.int16)
        return float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))

    def _process_frame(self, frame: bytes):
        energy = self._compute_energy(frame)

        # Energy-based VAD: check for speech
        if energy > self.config.energy_threshold:
            self._consecutive_speech += 1
            if self._consecutive_speech >= 2:
                self._start_buffering(energy)
        else:
            self._consecutive_speech = 0

        if self.state == WakeWordState.BUFFERING:
            self._audio_buffer.append(frame)

            if energy > self._peak_energy:
                self._peak_energy = energy

            # Check if we have enough frames for ML prediction
            if len(self._audio_buffer) >= self.config.buffer_frames:
                self._run_ml_detection()
                self._audio_buffer = []
                self.state = WakeWordState.LISTENING

            # Max duration safety
            if len(self._audio_buffer) > self.config.buffer_frames * 2:
                self._audio_buffer = []
                self.state = WakeWordState.LISTENING

    def _start_buffering(self, energy: float):
        self.state = WakeWordState.BUFFERING
        self._audio_buffer = []
        self._peak_energy = energy
        self._consecutive_speech = 0

    def _run_ml_detection(self):
        """Run ML model prediction on buffered audio."""
        if self._interpreter is None:
            return

        try:
            # Combine frames into audio
            audio_bytes = b''.join(self._audio_buffer[:self.config.buffer_frames])
            audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # Extract features (MFCC)
            from .DSP import extract_mfcc
            mfcc = extract_mfcc(audio, sample_rate=self.config.sample_rate, n_mfcc=13)

            # Prepare input (add batch dimension)
            features = mfcc.reshape(1, *mfcc.shape)

            # Run inference
            self._interpreter.set_tensor(self._input_details[0]['index'], features)
            self._interpreter.invoke()
            output = self._interpreter.get_tensor(self._output_details[0]['index'])
            proba = float(output[0][0])

            print(f"[WAKE-ML] Prediction: {proba:.3f}", flush=True)

            if proba >= self.config.ml_threshold:
                self._fire_detection(proba)

        except Exception as e:
            print(f"[WAKE-ML] Detection error: {e}")

    def _fire_detection(self, proba: float):
        self.state = WakeWordState.DETECTED
        self._cooldown = self.config.cooldown_frames
        print(f"[WAKE-ML] *** DETECTED ({proba:.3f}) ***", flush=True)

        if self.callback:
            try:
                # Pick the first wake word (can be made smarter with confidence per word)
                self.callback(self.config.wake_words[0])
            except Exception as e:
                print(f"[WAKE-ML] Callback error: {e}")


# ── Standalone Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    detections = []

    def on_wake(word):
        detections.append(word)
        print(f"\n>>> WAKE: {word} <<<\n")

    config = WakeWordMLConfig(
        wake_words=["hey kritix", "hello kritix"],
        ml_threshold=0.6,
        energy_threshold=3000,
    )

    detector = WakeWordMLDetector(callback=on_wake, config=config)
    detector.start()

    print("Listening for 10 seconds...")
    time.sleep(10)

    detector.stop()
    print(f"\nTotal detections: {len(detections)}")
