"""
Voice/DataCollector.py - Wake Word Data Collection and Augmentation
Records and augments wake word samples for ML training.
"""

import os
import json
import threading
import queue
import time
import numpy as np
import pyaudio
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class WakeWordSample:
    """Single wake word audio sample with metadata."""
    audio: bytes              # 16-bit PCM audio
    sample_rate: int           # Sample rate (default 16000)
    label: str                 # Wake word (e.g., "hey_kritix")
    duration: float            # Duration in seconds
    speaker_id: str            # Speaker identifier
    timestamp: str            # ISO timestamp
    energy_rms: float          # RMS energy level
    snr_db: float             # Signal-to-noise ratio estimate
    background_env: str       # Environment (quiet, noisy, etc.)

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items()}


class WakeWordDataCollector:
    """
    Collects wake word audio samples with augmentation.
    Runs in background thread to avoid blocking main application.
    """

    WAKE_WORDS = ["hey_kritix", "hello_kritix", "listen_kritix"]

    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "wake_words"
        )
        os.makedirs(self.data_dir, exist_ok=True)

        self._queue = queue.Queue()
        self._running = False
        self._thread = None

        # Statistics
        self._stats = {ww: 0 for ww in self.WAKE_WORDS}
        self._total_samples = 0

        print(f"[COLLECTOR] Data directory: {self.data_dir}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        """Start background collection thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        print("[COLLECTOR] Started")

    def stop(self):
        """Stop collection thread and save data."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        self._save_manifest()
        print("[COLLECTOR] Stopped")

    def collect_sample(
        self,
        audio: bytes,
        label: str,
        sample_rate: int = 16000,
        speaker_id: str = "default",
        background_env: str = "quiet",
    ) -> bool:
        """
        Add a collected sample to the queue.
        Returns True if queued successfully.
        """
        if label not in self.WAKE_WORDS:
            print(f"[COLLECTOR] Unknown label: {label}")
            return False

        if not audio or len(audio) < 1600:  # <0.1s @ 16kHz
            print("[COLLECTOR] Audio too short")
            return False

        # Calculate metadata
        pcm = np.frombuffer(audio, dtype=np.int16)
        energy_rms = float(np.sqrt(np.mean(pcm.astype(float) ** 2)))
        duration = len(audio) / (sample_rate * 2)

        # Simple SNR estimate
        silence_threshold = np.percentile(np.abs(pcm), 25) / 2.0
        signal_mask = np.abs(pcm) > silence_threshold
        if np.sum(signal_mask) > 0:
            signal_energy = np.mean(pcm[signal_mask].astype(float) ** 2)
            noise_energy = np.mean(pcm[~signal_mask].astype(float) ** 2) + 1e-9
            snr_db = 10.0 * np.log10(signal_energy / noise_energy)
        else:
            snr_db = 0.0

        sample = WakeWordSample(
            audio=audio,
            sample_rate=sample_rate,
            label=label,
            duration=duration,
            speaker_id=speaker_id,
            timestamp=datetime.utcnow().isoformat(),
            energy_rms=energy_rms,
            snr_db=snr_db,
            background_env=background_env,
        )

        self._queue.put(sample)
        return True

    def collect_live(
        self,
        label: str,
        duration: float = 3.0,
        device_index: int = 5,
        sample_rate: int = 16000,
    ) -> bool:
        """
        Record a live sample from microphone.
        Returns True if recording successful.
        """
        print(f"[COLLECTOR] Recording '{label}' ({duration}s)...")

        try:
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024,
            )

            frames = []
            n_frames = int(duration * sample_rate / 1024)
            for _ in range(n_frames):
                frames.append(stream.read(1024, exception_on_overflow=False))

            stream.stop_stream()
            stream.close()
            p.terminate()

            audio = b''.join(frames)
            return self.collect_sample(audio, label, sample_rate, speaker_id="live")

        except Exception as e:
            print(f"[COLLECTOR] Recording error: {e}")
            return False

    # ── Augmentation ───────────────────────────────────────────────────────────

    def augment_sample(self, sample: WakeWordSample) -> List[WakeWordSample]:
        """
        Generate augmented versions of a sample.
        Returns list of augmented samples.
        """
        augmented = []

        # Original
        augmented.append(sample)

        pcm = np.frombuffer(sample.audio, dtype=np.int16).astype(np.float32) / 32768.0

        # 1. Time stretch (speed variation)
        for speed_factor in [0.9, 1.1]:
            # Resample
            n = int(len(pcm) / speed_factor)
            stretched = np.interp(np.linspace(0, len(pcm), n), np.arange(len(pcm)), pcm)
            stretched_pcm = (stretched * 32767).astype(np.int16).tobytes()
            augmented.append(WakeWordSample(
                audio=stretched_pcm,
                sample_rate=sample.sample_rate,
                label=sample.label,
                duration=len(stretched_pcm) / (sample.sample_rate * 2),
                speaker_id=sample.speaker_id + f"_speed{speed_factor}",
                timestamp=datetime.utcnow().isoformat(),
                energy_rms=float(np.sqrt(np.mean(stretched.astype(float) ** 2))),
                snr_db=sample.snr_db,
                background_env=sample.background_env,
            ))

        # 2. Pitch shift (via resampling)
        for pitch_factor in [0.95, 1.05]:
            n = int(len(pcm) * pitch_factor)
            pitched = np.interp(np.linspace(0, len(pcm), n), np.arange(len(pcm)) * pitch_factor, pcm)
            pitched_pcm = (np.clip(pitched, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            augmented.append(WakeWordSample(
                audio=pitched_pcm,
                sample_rate=sample.sample_rate,
                label=sample.label,
                duration=len(pitched_pcm) / (sample.sample_rate * 2),
                speaker_id=sample.speaker_id + f"_pitch{pitch_factor}",
                timestamp=datetime.utcnow().isoformat(),
                energy_rms=float(np.sqrt(np.mean(pitched.astype(float) ** 2))),
                snr_db=sample.snr_db,
                background_env=sample.background_env,
            ))

        # 3. Noise injection (Gaussian noise)
        noise_level = 0.01
        noise = np.random.normal(0, noise_level, len(pcm))
        noisy = np.clip(pcm + noise, -1.0, 1.0)
        noisy_pcm = (noisy * 32767).astype(np.int16).tobytes()
        augmented.append(WakeWordSample(
            audio=noisy_pcm,
            sample_rate=sample.sample_rate,
            label=sample.label,
            duration=len(noisy_pcm) / (sample.sample_rate * 2),
            speaker_id=sample.speaker_id + "_noise",
            timestamp=datetime.utcnow().isoformat(),
            energy_rms=float(np.sqrt(np.mean(noisy.astype(float) ** 2))),
            snr_db=sample.snr_db - 3.0,
            background_env="noisy",
        ))

        return augmented

    # ── Worker Thread ───────────────────────────────────────────────────────────

    def _worker(self):
        """Background thread: processes queue and saves samples."""
        while self._running:
            try:
                sample = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Augment and save
            augmented = self.augment_sample(sample)

            for aug_sample in augmented:
                self._save_sample(aug_sample)
                self._stats[aug_sample.label] += 1
                self._total_samples += 1

            print(f"[COLLECTOR] Saved {len(augmented)} samples for '{sample.label}'")

        self._save_manifest()

    def _save_sample(self, sample: WakeWordSample):
        """Save sample to disk."""
        # Create label directory
        label_dir = os.path.join(self.data_dir, sample.label)
        os.makedirs(label_dir, exist_ok=True)

        # Generate filename
        timestamp = sample.timestamp.replace(":", "-").replace(".", "-")
        filename = f"{sample.speaker_id}_{timestamp}.raw"
        filepath = os.path.join(label_dir, filename)

        # Save audio
        with open(filepath, "wb") as f:
            f.write(sample.audio)

        # Save metadata
        meta_file = filepath.replace(".raw", ".json")
        with open(meta_file, "w") as f:
            json.dump(sample.to_dict(), f, indent=2)

    def _save_manifest(self):
        """Save collection manifest."""
        manifest = {
            "total_samples": self._total_samples,
            "samples_by_label": self._stats,
            "wake_words": self.WAKE_WORDS,
            "last_updated": datetime.utcnow().isoformat(),
        }

        manifest_file = os.path.join(self.data_dir, "manifest.json")
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"[COLLECTOR] Manifest saved: {manifest_file}")

    # ── Statistics ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get collection statistics."""
        return {
            "total": self._total_samples,
            "by_label": self._stats.copy(),
            "running": self._running,
        }


# ── Standalone Tool ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Wake Word Data Collection Tool")
    print("=" * 50)

    collector = WakeWordDataCollector()
    collector.start()

    try:
        while True:
            print("\nOptions:")
            print("  1. Record sample")
            print("  2. Show stats")
            print("  3. Exit")
            choice = input("Choose: ").strip()

            if choice == "1":
                print("\nWake words:", collector.WAKE_WORDS)
                label = input("Enter label: ").strip().lower().replace(" ", "_")
                if label not in collector.WAKE_WORDS:
                    print(f"Unknown label. Use: {collector.WAKE_WORDS}")
                    continue

                success = collector.collect_live(label, duration=3.0)
                if success:
                    print("Sample queued for processing")
                else:
                    print("Recording failed")

            elif choice == "2":
                stats = collector.get_stats()
                print(f"\nTotal samples: {stats['total']}")
                for label, count in stats['by_label'].items():
                    print(f"  {label}: {count}")

            elif choice == "3":
                break

    finally:
        collector.stop()
        print("\nCollection stopped")
