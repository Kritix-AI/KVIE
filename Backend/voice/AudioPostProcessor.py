"""
Backend/voice/AudioPostProcessor.py — Broadcast-Quality Audio Post-Processing

Makes TTS output sound warm, confident, and human-like — matching ElevenLabs quality.
Applied as the final step after any TTS engine (Chatterbox, Edge TTS fallback).

Pipeline: Warmth EQ → Presence Boost → De-esser → Dynamic Compression
          → Loudness Normalization → Soft Limiter

Dependencies: numpy, scipy (already in project)
"""

import numpy as np
from scipy.signal import butter, sosfilt, lfilter
from typing import Optional


class AudioPostProcessor:
    """
    Broadcast-quality audio post-processing for TTS output.
    Transforms raw synthesized audio into warm, confident, human-sounding speech.
    """

    def __init__(
        self,
        sample_rate: int = 24000,
        target_lufs: float = -16.0,
        warmth_gain_db: float = 3.0,
        presence_gain_db: float = 2.5,
        compression_threshold_db: float = -18.0,
        compression_ratio: float = 3.0,
    ):
        self.sample_rate = sample_rate
        self.target_lufs = target_lufs
        self.warmth_gain_db = warmth_gain_db
        self.presence_gain_db = presence_gain_db
        self.compression_threshold_db = compression_threshold_db
        self.compression_ratio = compression_ratio

    # ── Full Pipeline ──────────────────────────────────────────────────────────

    def process(self, audio: np.ndarray, sr: int = None) -> np.ndarray:
        """
        Full post-processing pipeline for broadcast-quality output.

        Args:
            audio: Float32 audio array in [-1.0, 1.0]
            sr: Sample rate (uses self.sample_rate if None)

        Returns:
            Processed float32 audio array
        """
        sr = sr or self.sample_rate

        if len(audio) == 0:
            return audio

        # Ensure float32
        audio = audio.astype(np.float32)

        # 1. DC offset removal
        audio = audio - np.mean(audio)

        # 2. Warmth EQ — boost low-mids (200-500Hz) for vocal body
        audio = self.apply_warmth_eq(audio, sr)

        # 3. Presence boost — gentle 2-4kHz lift for clarity & confidence
        audio = self.apply_presence_boost(audio, sr)

        # 4. De-esser — reduce harsh sibilance that makes synthesis sound digital
        audio = self.apply_deesser(audio, sr)

        # 5. Dynamic compression — consistent, confident volume
        audio = self.apply_dynamic_compression(audio, sr)

        # 6. Loudness normalization — broadcast standard (-16 LUFS)
        audio = self.normalize_loudness(audio, sr)

        # 7. Soft limiter — prevent clipping while preserving dynamics
        audio = self.soft_limit(audio)

        return audio

    # ── Warmth EQ ──────────────────────────────────────────────────────────────

    def apply_warmth_eq(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Boost 200-500Hz low-mids for vocal warmth and body.
        This is the "radio announcer" frequency range that makes voices
        sound rich and authoritative.
        """
        nyquist = sr / 2.0
        low_freq = 200.0 / nyquist
        high_freq = min(500.0 / nyquist, 0.99)

        if low_freq >= 0.99 or high_freq <= low_freq:
            return audio

        # Extract the warmth band
        sos = butter(2, [low_freq, high_freq], btype='bandpass', output='sos')
        warmth_band = sosfilt(sos, audio)

        # Add boosted warmth band back to original
        gain = 10.0 ** (self.warmth_gain_db / 20.0) - 1.0
        return audio + warmth_band * gain

    # ── Presence Boost ─────────────────────────────────────────────────────────

    def apply_presence_boost(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Boost 2-4kHz for speech intelligibility and confident presence.
        This frequency range is where human hearing is most sensitive,
        making the voice cut through and sound assertive.
        """
        nyquist = sr / 2.0
        low_freq = 2000.0 / nyquist
        high_freq = min(4000.0 / nyquist, 0.99)

        if low_freq >= 0.99 or high_freq <= low_freq:
            return audio

        sos = butter(2, [low_freq, high_freq], btype='bandpass', output='sos')
        presence_band = sosfilt(sos, audio)

        gain = 10.0 ** (self.presence_gain_db / 20.0) - 1.0
        return audio + presence_band * gain

    # ── De-esser ───────────────────────────────────────────────────────────────

    def apply_deesser(
        self,
        audio: np.ndarray,
        sr: int,
        threshold_db: float = -20.0,
        reduction_db: float = -6.0,
    ) -> np.ndarray:
        """
        Reduce harsh sibilance (5-9kHz) that makes synthesized speech sound
        digital and artificial. Uses frequency-selective compression.
        """
        nyquist = sr / 2.0
        low_freq = 5000.0 / nyquist
        high_freq = min(9000.0 / nyquist, 0.99)

        if low_freq >= 0.99 or high_freq <= low_freq:
            return audio

        # Extract sibilance band
        sos = butter(3, [low_freq, high_freq], btype='bandpass', output='sos')
        sibilance = sosfilt(sos, audio)

        # Detect when sibilance exceeds threshold
        threshold = 10.0 ** (threshold_db / 20.0)
        reduction = 10.0 ** (reduction_db / 20.0)

        # Frame-based sibilance detection (5ms frames)
        frame_len = max(int(0.005 * sr), 1)
        result = audio.copy()

        for i in range(0, len(audio) - frame_len, frame_len):
            frame = sibilance[i:i + frame_len]
            rms = np.sqrt(np.mean(frame ** 2))

            if rms > threshold:
                # Attenuate sibilance in this frame
                gain = reduction
                # Smooth transition
                envelope = np.linspace(1.0, gain, frame_len // 2)
                envelope = np.concatenate([envelope, np.linspace(gain, 1.0, frame_len - frame_len // 2)])
                result[i:i + frame_len] -= sibilance[i:i + frame_len] * (1.0 - envelope)

        return result

    # ── Dynamic Compression ────────────────────────────────────────────────────

    def apply_dynamic_compression(self, audio: np.ndarray, sr: int = None) -> np.ndarray:
        """
        Apply dynamic range compression for consistent, confident volume.

        This is what makes podcast/radio voices sound professional —
        quiet parts are boosted, loud parts are tamed, creating an
        even, authoritative delivery.

        Uses envelope-following compression with attack/release smoothing.
        """
        sr = sr or self.sample_rate
        threshold = 10.0 ** (self.compression_threshold_db / 20.0)
        ratio = self.compression_ratio

        # Envelope follower (attack: 5ms, release: 50ms)
        attack_samples = max(int(0.005 * sr), 1)
        release_samples = max(int(0.050 * sr), 1)

        envelope = np.zeros(len(audio), dtype=np.float32)
        envelope[0] = abs(audio[0])

        for i in range(1, len(audio)):
            sample_abs = abs(audio[i])
            if sample_abs > envelope[i - 1]:
                # Attack — fast follow
                coeff = 1.0 - np.exp(-1.0 / attack_samples)
                envelope[i] = envelope[i - 1] + coeff * (sample_abs - envelope[i - 1])
            else:
                # Release — slow decay
                coeff = 1.0 - np.exp(-1.0 / release_samples)
                envelope[i] = envelope[i - 1] + coeff * (sample_abs - envelope[i - 1])

        # Compute gain reduction
        gain = np.ones(len(audio), dtype=np.float32)
        above_threshold = envelope > threshold

        if np.any(above_threshold):
            # dB domain compression
            env_db = 20.0 * np.log10(np.maximum(envelope[above_threshold], 1e-10))
            threshold_db = 20.0 * np.log10(threshold)
            overshoot_db = env_db - threshold_db
            gain_reduction_db = overshoot_db * (1.0 - 1.0 / ratio)
            gain[above_threshold] = 10.0 ** (-gain_reduction_db / 20.0)

        # Apply makeup gain (compensate for compression)
        compressed = audio * gain
        makeup_gain = 1.0 / max(np.max(np.abs(compressed)), 1e-10) * 0.9
        makeup_gain = min(makeup_gain, 3.0)  # Cap at +9.5dB makeup

        return compressed * makeup_gain

    # ── Loudness Normalization ─────────────────────────────────────────────────

    def normalize_loudness(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Normalize to target LUFS (Loudness Units Full Scale).
        Broadcast standard is -16 LUFS (YouTube, podcasts).

        This ensures the voice always sounds at a consistent,
        confident volume level regardless of input.
        """
        # Simplified LUFS measurement using RMS with K-weighting approximation
        # K-weighting: high-shelf at 1681Hz (+4dB) + high-pass at 38Hz
        nyquist = sr / 2.0

        # High-shelf boost (approximation)
        if 1681.0 / nyquist < 0.99:
            sos_shelf = butter(1, 1681.0 / nyquist, btype='high', output='sos')
            k_weighted = audio + sosfilt(sos_shelf, audio) * 0.585  # +4dB boost
        else:
            k_weighted = audio

        # High-pass at 38Hz
        if 38.0 / nyquist < 0.99:
            sos_hp = butter(2, 38.0 / nyquist, btype='high', output='sos')
            k_weighted = sosfilt(sos_hp, k_weighted)

        # Gated LUFS measurement (simplified)
        rms = np.sqrt(np.mean(k_weighted ** 2))
        if rms < 1e-10:
            return audio

        current_lufs = 20.0 * np.log10(rms) - 0.691
        gain_db = self.target_lufs - current_lufs
        gain_db = np.clip(gain_db, -20.0, 20.0)  # Safety clamp
        gain = 10.0 ** (gain_db / 20.0)

        return audio * gain

    # ── Soft Limiter ───────────────────────────────────────────────────────────

    @staticmethod
    def soft_limit(audio: np.ndarray, ceiling: float = 0.95) -> np.ndarray:
        """
        Soft limiter using tanh curve to prevent harsh digital clipping.
        Preserves transients while ensuring output stays within bounds.
        """
        # Scale so ceiling maps to tanh(1.0) ≈ 0.76
        scale = 1.0 / ceiling
        limited = np.tanh(audio * scale) * ceiling
        return limited.astype(np.float32)

    # ── Breath Insertion ───────────────────────────────────────────────────────

    @staticmethod
    def insert_breath_pauses(
        audio: np.ndarray,
        sr: int,
        min_silence_ms: int = 150,
        breath_duration_ms: int = 80,
    ) -> np.ndarray:
        """
        Find natural pauses in speech and extend them slightly with
        a gentle fade, simulating breath pauses. This makes the speech
        feel more organic and less machine-gun-like.
        """
        frame_len = int(0.010 * sr)  # 10ms frames
        breath_samples = int(breath_duration_ms / 1000.0 * sr)
        min_silence_frames = int(min_silence_ms / 10)

        # Detect silence regions using RMS energy
        rms_threshold = 0.01
        silence_run = 0
        result_parts = []
        i = 0

        while i < len(audio) - frame_len:
            frame = audio[i:i + frame_len]
            rms = np.sqrt(np.mean(frame ** 2))

            if rms < rms_threshold:
                silence_run += 1
            else:
                if silence_run >= min_silence_frames:
                    # Found a natural pause — extend it with gentle breath silence
                    breath = np.zeros(breath_samples, dtype=np.float32)
                    # Gentle fade-in from silence
                    fade_len = min(breath_samples // 4, 100)
                    if fade_len > 0:
                        breath[-fade_len:] = np.linspace(0, 0.001, fade_len)
                    result_parts.append(breath)
                silence_run = 0

            result_parts.append(frame)
            i += frame_len

        # Append remaining samples
        if i < len(audio):
            result_parts.append(audio[i:])

        return np.concatenate(result_parts) if result_parts else audio

    # ── Emotion-Specific Processing ────────────────────────────────────────────

    def process_with_emotion(
        self,
        audio: np.ndarray,
        sr: int,
        emotion: str = "neutral",
    ) -> np.ndarray:
        """
        Apply emotion-specific post-processing before the standard pipeline.

        - 'confident'/'authoritative': Extra presence boost, tighter compression
        - 'calm'/'thinking': Less compression, more breath pauses
        - 'excited'/'happy': Wider dynamics, brighter EQ
        - 'sad'/'empathetic': Warmer EQ, gentler processing
        """
        # Emotion-specific parameter overrides
        emotion_profiles = {
            'happy': {
                'warmth_db': 2.0,
                'presence_db': 3.0,
                'compression_threshold_db': -16.0,
                'add_breaths': False,
            },
            'excited': {
                'warmth_db': 1.5,
                'presence_db': 3.5,
                'compression_threshold_db': -14.0,
                'add_breaths': False,
            },
            'sad': {
                'warmth_db': 4.0,
                'presence_db': 1.5,
                'compression_threshold_db': -22.0,
                'add_breaths': True,
            },
            'calm': {
                'warmth_db': 3.5,
                'presence_db': 2.0,
                'compression_threshold_db': -22.0,
                'add_breaths': True,
            },
            'thinking': {
                'warmth_db': 3.0,
                'presence_db': 2.0,
                'compression_threshold_db': -20.0,
                'add_breaths': True,
            },
            'empathetic': {
                'warmth_db': 4.0,
                'presence_db': 1.5,
                'compression_threshold_db': -22.0,
                'add_breaths': True,
            },
            'urgent': {
                'warmth_db': 1.5,
                'presence_db': 3.5,
                'compression_threshold_db': -14.0,
                'add_breaths': False,
            },
            'confident': {
                'warmth_db': 2.5,
                'presence_db': 3.5,
                'compression_threshold_db': -16.0,
                'add_breaths': False,
            },
            'friendly': {
                'warmth_db': 3.0,
                'presence_db': 2.5,
                'compression_threshold_db': -18.0,
                'add_breaths': False,
            },
        }

        profile = emotion_profiles.get(emotion, {})

        # Override parameters for this emotion
        original_warmth = self.warmth_gain_db
        original_presence = self.presence_gain_db
        original_threshold = self.compression_threshold_db

        self.warmth_gain_db = profile.get('warmth_db', self.warmth_gain_db)
        self.presence_gain_db = profile.get('presence_db', self.presence_gain_db)
        self.compression_threshold_db = profile.get('compression_threshold_db', self.compression_threshold_db)

        # Run standard pipeline
        audio = self.process(audio, sr)

        # Add breath pauses for certain emotions
        if profile.get('add_breaths', False):
            audio = self.insert_breath_pauses(audio, sr)

        # Restore original parameters
        self.warmth_gain_db = original_warmth
        self.presence_gain_db = original_presence
        self.compression_threshold_db = original_threshold

        return audio

    # ── Utility ────────────────────────────────────────────────────────────────

    @staticmethod
    def audio_from_file(path: str) -> tuple:
        """Load audio file and return (audio_float32, sample_rate)."""
        import soundfile as sf
        audio, sr = sf.read(path, dtype='float32')
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio, sr

    @staticmethod
    def save_audio(audio: np.ndarray, sr: int, path: str):
        """Save processed audio to file."""
        import soundfile as sf
        sf.write(path, audio, sr)

    def process_file(self, input_path: str, output_path: str, emotion: str = "neutral"):
        """Process an audio file end-to-end."""
        audio, sr = self.audio_from_file(input_path)
        processed = self.process_with_emotion(audio, sr, emotion)
        self.save_audio(processed, sr, output_path)
        return output_path


# ── Singleton ──────────────────────────────────────────────────────────────────

_processor_instance = None


def get_post_processor(sample_rate: int = 24000) -> AudioPostProcessor:
    """Get singleton AudioPostProcessor instance."""
    global _processor_instance
    if _processor_instance is None or _processor_instance.sample_rate != sample_rate:
        _processor_instance = AudioPostProcessor(sample_rate=sample_rate)
    return _processor_instance


# ── Self Test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("AudioPostProcessor Self-Test")
    print("=" * 50)

    # Generate test signal (synthetic speech-like)
    sr = 24000
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration))

    # Simulate speech: fundamental + harmonics + noise
    f0 = 150.0  # Female fundamental
    signal = (
        0.3 * np.sin(2 * np.pi * f0 * t)
        + 0.15 * np.sin(2 * np.pi * f0 * 2 * t)
        + 0.08 * np.sin(2 * np.pi * f0 * 3 * t)
        + 0.02 * np.random.randn(len(t))
    ).astype(np.float32)

    processor = AudioPostProcessor(sample_rate=sr)

    print(f"Input  RMS: {np.sqrt(np.mean(signal**2)):.4f}")
    processed = processor.process(signal, sr)
    print(f"Output RMS: {np.sqrt(np.mean(processed**2)):.4f}")

    # Test emotion-specific processing
    for emotion in ['neutral', 'confident', 'calm', 'excited', 'sad']:
        result = processor.process_with_emotion(signal.copy(), sr, emotion)
        rms = np.sqrt(np.mean(result ** 2))
        print(f"  {emotion:12s} → RMS: {rms:.4f}")

    print("\n[PASS] All post-processing stages executed successfully")
