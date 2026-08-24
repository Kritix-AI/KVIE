"""
Voice/DSP.py - Digital Signal Processing Pipeline for Audio
Includes noise reduction, feature extraction, audio normalization.
"""

import numpy as np
from scipy.signal import resample, butter, sosfilt, lfilter
from typing import Tuple, Optional


class DSPPipeline:
    """Audio DSP pipeline for preprocessing before STT and wake word detection."""

    def __init__(
        self,
        input_rate: int = 44100,
        target_rate: int = 16000,
        noise_gate_db: float = -45.0,
        boost_db: float = 12.0,
    ):
        self.input_rate = input_rate
        self.target_rate = target_rate
        self.noise_gate_db = noise_gate_db
        self.boost_db = boost_db
        self.boost_factor = 10.0 ** (boost_db / 20.0)  # linear gain

    # ── Core Pipeline ─────────────────────────────────────────────────────────

    def process(self, pcm_bytes: bytes) -> np.ndarray:
        """
        Full DSP pipeline: resample → normalize → noise gate → boost → clamp.
        Returns float32 PCM in range [-1.0, 1.0].
        """
        audio = self._bytes_to_float(pcm_bytes)
        audio = self.resample(audio)
        audio = self.normalize(audio)
        audio = self.noise_gate(audio)
        audio = self.boost(audio)
        audio = self.clip(audio)
        return audio

    def process_to_int16(self, pcm_bytes: bytes) -> bytes:
        """Process and return as 16-bit PCM bytes."""
        audio = self.process(pcm_bytes)
        return (audio * 32767).astype(np.int16).tobytes()

    def process_to_int16_rate(self, pcm_bytes: bytes, target_rate: int) -> bytes:
        """Process 44.1kHz PCM bytes and resample to target rate (default 16kHz)."""
        audio = self._bytes_to_float(pcm_bytes)
        # Resample FIRST, then gate, then gentle boost — never normalize before gate
        audio = self.resample(audio, src_rate=self.input_rate, tgt_rate=target_rate)
        audio = self.noise_gate(audio)
        audio = self.clip(audio)
        return (audio * 32767).astype(np.int16).tobytes()

    # ── Steps ─────────────────────────────────────────────────────────────────

    @staticmethod
    def resample(audio: np.ndarray, src_rate: int = 44100, tgt_rate: int = 16000) -> np.ndarray:
        """Resample audio using scipy."""
        if src_rate == tgt_rate:
            return audio
        n = int(len(audio) * tgt_rate / src_rate)
        return resample(audio, n).astype(np.float32)

    @staticmethod
    def resample_to(audio: np.ndarray, target_rate: int) -> np.ndarray:
        """Resample from current audio rate to target rate."""
        # Assume input is at default rate; caller specifies target
        src_rate = 44100
        if src_rate == target_rate:
            return audio
        n = int(len(audio) * target_rate / src_rate)
        return resample(audio, n).astype(np.float32)

    @staticmethod
    def normalize(audio: np.ndarray) -> np.ndarray:
        """DC offset removal + peak normalization."""
        audio = audio - np.mean(audio)
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak
        return audio.astype(np.float32)

    def noise_gate(self, audio: np.ndarray) -> np.ndarray:
        """
        Noise gate: suppress samples below noise_gate_db.
        Uses RMS over short windows for smooth gating.
        """
        threshold = 10.0 ** (self.noise_gate_db / 20.0)
        window = int(0.01 * self.target_rate)  # 10ms window

        result = np.zeros_like(audio)
        for i in range(0, len(audio), window):
            chunk = audio[i:i + window]
            rms = np.sqrt(np.mean(chunk ** 2))
            if rms > threshold:
                result[i:i + window] = chunk
            # else: leave as silence (0.0)

        return result

    def boost(self, audio: np.ndarray) -> np.ndarray:
        """Apply gain boost."""
        return audio * self.boost_factor

    @staticmethod
    def clip(audio: np.ndarray) -> np.ndarray:
        """Soft clipping to prevent harsh distortion."""
        audio = np.clip(audio, -1.0, 1.0)
        # Soft clip
        mask = np.abs(audio) > 0.95
        audio[mask] = np.sign(audio[mask]) * (0.95 + 0.05 * np.tanh((np.abs(audio[mask]) - 0.95) / 0.05))
        return audio

    @staticmethod
    def _bytes_to_float(pcm_bytes: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to float32 array in [-1.0, 1.0]."""
        return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


# ── Feature Extraction ────────────────────────────────────────────────────────

def extract_mfcc(
    audio: np.ndarray,
    sample_rate: int = 16000,
    n_mfcc: int = 40,
    n_fft: int = 512,
    hop_length: int = 160,
    n_mels: int = 40,
) -> np.ndarray:
    """
    Extract MFCC features.
    Requires librosa: pip install librosa
    Falls back to simple energy bands if unavailable.
    """
    try:
        import librosa
        mfcc = librosa.feature.mfcc(
            y=audio,
            sr=sample_rate,
            n_mfcc=n_mfcc,
            n_fft=n_fft,
            hop_length=hop_length,
            n_mels=n_mels,
        )
        return mfcc.T  # (time, n_mfcc)
    except ImportError:
        # Simple fallback: log-scaled energy bands
        return _simple_mfcc(audio, sample_rate, n_mfcc, n_fft, hop_length)


def extract_mel_spectrogram(
    audio: np.ndarray,
    sample_rate: int = 16000,
    n_mels: int = 80,
    n_fft: int = 512,
    hop_length: int = 160,
) -> np.ndarray:
    """
    Extract log-mel spectrogram.
    Requires librosa. Falls back to simple spectrogram.
    """
    try:
        import librosa
        S = librosa.feature.melspectrogram(
            y=audio,
            sr=sample_rate,
            n_mels=n_mels,
            n_fft=n_fft,
            hop_length=hop_length,
        )
        return librosa.power_to_db(S, ref=np.max).T  # (time, n_mels)
    except ImportError:
        return _simple_spectrogram(audio, n_fft, hop_length, n_mels)


def _simple_mfcc(audio: np.ndarray, sr: int, n_mfcc: int, n_fft: int, hop: int) -> np.ndarray:
    """Fallback MFCC using FFT + manual mel filterbank."""
    n_frames = (len(audio) - n_fft) // hop + 1
    if n_frames <= 0:
        return np.zeros((1, n_mfcc), dtype=np.float32)

    # Compute power spectrogram
    frames = np.lib.stride_tricks.sliding_window_view(audio, n_fft)[::hop]
    spectrum = np.abs(np.fft.rfft(frames, n=n_fft)) ** 2
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)

    # Simple mel-like filterbank (triangular bands on log scale)
    mel_bands = np.zeros((n_mfcc, len(freqs)), dtype=np.float32)
    for i in range(n_mfcc):
        f_low = 20.0 * (sr / 2) ** (i / n_mfcc)
        f_mid = 20.0 * (sr / 2) ** ((i + 1) / n_mfcc)
        f_high = 20.0 * (sr / 2) ** ((i + 2) / n_mfcc)
        lo = (freqs >= f_low) & (freqs < f_mid)
        hi = (freqs >= f_mid) & (freqs < f_high)
        mel_bands[i, lo] = (freqs[lo] - f_low) / max(f_mid - f_low, 1e-9)
        mel_bands[i, hi] = (f_high - freqs[hi]) / max(f_high - f_mid, 1e-9)
        mel_bands[i, freqs >= f_high] = 0

    mel_energy = np.dot(mel_bands, spectrum.T).T  # (n_frames, n_mfcc)
    log_mel = np.log(np.maximum(mel_energy, 1e-10))

    # Simple DCT-like decorrelation
    mfcc = log_mel.copy()
    for i in range(1, min(13, n_mfcc)):
        for j in range(n_mfcc):
            mfcc[:, i] += log_mel[:, j] * np.cos(np.pi * i * j / n_mfcc)
    return mfcc.astype(np.float32)


def _simple_spectrogram(audio: np.ndarray, n_fft: int, hop: int, n_mels: int) -> np.ndarray:
    """Fallback log spectrogram."""
    n_frames = (len(audio) - n_fft) // hop + 1
    if n_frames <= 0:
        return np.zeros((1, n_mels), dtype=np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(audio, n_fft)[::hop]
    spectrum = np.abs(np.fft.rfft(frames, n=n_fft))
    # Log compress + downsample to n_mels
    log_spec = np.log(np.maximum(spectrum, 1e-10))
    step = log_spec.shape[1] // n_mels
    mel_spec = np.array([
        np.mean(log_spec[:, i * step:(i + 1) * step], axis=1)
        for i in range(n_mels)
    ]).T
    return mel_spec.astype(np.float32)


def compute_energy(audio: np.ndarray, frame_length: int = 512, hop: int = 256) -> np.ndarray:
    """Compute per-frame RMS energy."""
    n_frames = (len(audio) - frame_length) // hop + 1
    if n_frames <= 0:
        return np.array([0.0])
    frames = np.lib.stride_tricks.sliding_window_view(audio, frame_length)[::hop]
    return np.sqrt(np.mean(frames ** 2, axis=1))


def compute_zero_crossing_rate(audio: np.ndarray, frame_length: int = 512, hop: int = 256) -> np.ndarray:
    """Compute per-frame zero-crossing rate."""
    n_frames = (len(audio) - frame_length) // hop + 1
    if n_frames <= 0:
        return np.array([0.0])
    frames = np.lib.stride_tricks.sliding_window_view(audio, frame_length)[::hop]
    return np.mean(np.diff(np.sign(frames), axis=1) != 0, axis=1)


# ── Advanced DSP: Spectral Noise Subtraction ──────────────────────────────────

def spectral_subtraction(
    audio: np.ndarray,
    sr: int = 16000,
    noise_frames: int = 10,
    n_fft: int = 512,
    hop_length: int = 160,
    oversubtraction: float = 2.0,
    spectral_floor: float = 0.01,
) -> np.ndarray:
    """
    Frequency-domain noise reduction using spectral subtraction.

    Estimates the noise spectrum from the first N frames (assumed to be
    background noise / silence) and subtracts it from the signal spectrum.
    This is far more effective than simple noise gating for handling
    fan noise, AC hum, and ambient background.

    Args:
        audio: float32 audio array
        sr: sample rate
        noise_frames: number of initial frames to estimate noise from
        n_fft: FFT size
        hop_length: hop between frames
        oversubtraction: how aggressively to remove noise (2.0 = moderate)
        spectral_floor: minimum spectral value to prevent musical noise

    Returns:
        Noise-reduced float32 audio array
    """
    if len(audio) < n_fft * 2:
        return audio

    # Compute STFT
    n_frames_total = (len(audio) - n_fft) // hop_length + 1
    if n_frames_total <= noise_frames:
        return audio

    # Windowed STFT frames
    window = np.hanning(n_fft).astype(np.float32)
    frames_stft = []
    for i in range(n_frames_total):
        start = i * hop_length
        frame = audio[start:start + n_fft]
        if len(frame) < n_fft:
            frame = np.pad(frame, (0, n_fft - len(frame)))
        frames_stft.append(np.fft.rfft(frame * window))

    frames_stft = np.array(frames_stft)
    magnitudes = np.abs(frames_stft)
    phases = np.angle(frames_stft)

    # Estimate noise spectrum from first N frames
    noise_spectrum = np.mean(magnitudes[:noise_frames], axis=0)

    # Spectral subtraction with oversubtraction factor
    clean_magnitudes = np.maximum(
        magnitudes - oversubtraction * noise_spectrum[np.newaxis, :],
        spectral_floor * magnitudes,  # Spectral floor prevents musical noise
    )

    # Reconstruct with original phase
    clean_stft = clean_magnitudes * np.exp(1j * phases)

    # Inverse STFT with overlap-add
    output = np.zeros(len(audio), dtype=np.float32)
    window_sum = np.zeros(len(audio), dtype=np.float32)

    for i in range(n_frames_total):
        start = i * hop_length
        frame = np.fft.irfft(clean_stft[i]).real.astype(np.float32)[:n_fft]
        frame *= window
        end = min(start + n_fft, len(output))
        length = end - start
        output[start:end] += frame[:length]
        window_sum[start:end] += window[:length] ** 2

    # Normalize by window overlap
    nonzero = window_sum > 1e-8
    output[nonzero] /= window_sum[nonzero]

    return output


def auto_gain_control(
    audio: np.ndarray,
    target_rms: float = 0.10,
    max_gain_db: float = 30.0,
    frame_ms: float = 20.0,
    sr: int = 16000,
) -> np.ndarray:
    """
    Adaptive Automatic Gain Control (AGC).

    Normalizes different microphone volumes to a consistent level
    by applying frame-level gain adjustment. Loud inputs are attenuated,
    quiet inputs are boosted — all transparently.

    Args:
        audio: float32 audio array
        target_rms: desired RMS energy level
        max_gain_db: maximum gain to apply (safety limit)
        frame_ms: frame length for gain computation
        sr: sample rate

    Returns:
        Gain-normalized float32 audio array
    """
    if len(audio) == 0:
        return audio

    frame_len = max(int(frame_ms / 1000.0 * sr), 1)
    max_gain = 10.0 ** (max_gain_db / 20.0)
    output = np.zeros_like(audio)

    # Smoothing for gain transitions (attack: 5ms, release: 50ms)
    smooth_gain = 1.0
    attack_coeff = 1.0 - np.exp(-1.0 / max(int(0.005 * sr / frame_len), 1))
    release_coeff = 1.0 - np.exp(-1.0 / max(int(0.050 * sr / frame_len), 1))

    for i in range(0, len(audio), frame_len):
        frame = audio[i:i + frame_len]
        rms = np.sqrt(np.mean(frame ** 2))

        if rms > 1e-8:
            desired_gain = target_rms / rms
            desired_gain = min(desired_gain, max_gain)  # Safety clamp
        else:
            desired_gain = 1.0

        # Smooth gain transitions
        if desired_gain < smooth_gain:
            smooth_gain += attack_coeff * (desired_gain - smooth_gain)
        else:
            smooth_gain += release_coeff * (desired_gain - smooth_gain)

        output[i:i + frame_len] = frame * smooth_gain

    return np.clip(output, -1.0, 1.0).astype(np.float32)


def wiener_filter(
    audio: np.ndarray,
    sr: int = 16000,
    n_fft: int = 512,
    hop_length: int = 160,
    noise_frames: int = 10,
) -> np.ndarray:
    """
    Wiener filter for smoother noise reduction than spectral subtraction.

    Uses a statistical approach to estimate the clean signal from noisy input.
    Produces fewer artifacts (musical noise) than spectral subtraction
    but is slightly less aggressive.

    Args:
        audio: float32 audio array
        sr: sample rate
        n_fft: FFT window size
        hop_length: hop between frames
        noise_frames: frames to estimate noise from

    Returns:
        Wiener-filtered float32 audio array
    """
    if len(audio) < n_fft * 2:
        return audio

    n_frames_total = (len(audio) - n_fft) // hop_length + 1
    if n_frames_total <= noise_frames:
        return audio

    window = np.hanning(n_fft).astype(np.float32)

    # Compute STFT
    frames_stft = []
    for i in range(n_frames_total):
        start = i * hop_length
        frame = audio[start:start + n_fft]
        if len(frame) < n_fft:
            frame = np.pad(frame, (0, n_fft - len(frame)))
        frames_stft.append(np.fft.rfft(frame * window))

    frames_stft = np.array(frames_stft)
    power = np.abs(frames_stft) ** 2

    # Estimate noise power from initial frames
    noise_power = np.mean(power[:noise_frames], axis=0)

    # Wiener gain: H = max(1 - noise/signal, floor)
    wiener_gain = np.maximum(
        1.0 - noise_power[np.newaxis, :] / (power + 1e-10),
        0.05,  # Minimum gain to avoid complete suppression
    )

    # Apply Wiener gain
    clean_stft = frames_stft * wiener_gain

    # Inverse STFT
    output = np.zeros(len(audio), dtype=np.float32)
    window_sum = np.zeros(len(audio), dtype=np.float32)

    for i in range(n_frames_total):
        start = i * hop_length
        frame = np.fft.irfft(clean_stft[i]).real.astype(np.float32)[:n_fft]
        frame *= window
        end = min(start + n_fft, len(output))
        length = end - start
        output[start:end] += frame[:length]
        window_sum[start:end] += window[:length] ** 2

    nonzero = window_sum > 1e-8
    output[nonzero] /= window_sum[nonzero]

    return output

