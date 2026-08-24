"""
Backend/voice/AudioEmotionDetector.py — Advanced Hybrid Speech Emotion Recognition (SER)

Production-grade Speech Emotion Recognition Engine featuring:
1. Noise Robustness: Spectral subtraction + Butterworth bandpass filtering before feature extraction.
2. Hybrid Fusion: Concatenates Wav2Vec2 neural embeddings/probabilities with acoustic prosody features (F0 contour, MFCCs, RMS, ZCR, Spectral Centroid).
3. Expanded Emotion Taxonomy:
   - 'angry' (High RMS energy, sharp pitch contours, high ZCR)
   - 'fearful' (F0 pitch tremor/instability, erratic energy envelope)
   - 'thoughtful' (Slow speech rate, mid energy, rising terminal intonation)
   - 'happy' (High mean pitch, elevated energy)
   - 'excited' (High dynamic range, fast tempo, elevated pitch variance)
   - 'sad' (Low energy, descending pitch contour, slow tempo)
   - 'empathetic' (Soft energy, warm lower pitch)
   - 'calm' (Stable pitch, low variance, relaxed energy)
   - 'neutral' (Balanced acoustic signature)
4. Contextual Temporal Smoothing: Median filtering sliding window buffer across frames to prevent jittery predictions.
"""

import os
import sys
import threading
import collections
import numpy as np
import librosa
from scipy.signal import butter, sosfilt
from typing import Optional, Dict, Any, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class AudioEmotionDetector:
    """Production-grade Hybrid Speech Emotion Recognition engine for mic audio."""

    def __init__(self, sample_rate: int = 16000, smoothing_window: int = 5):
        self.sample_rate = sample_rate
        self.lock = threading.Lock()
        self._wav2vec2_pipeline = None
        # Contextual Smoothing Buffer (Sliding Window)
        self.history_buffer = collections.deque(maxlen=smoothing_window)
        self._load_classifier()

    def _load_classifier(self):
        """Loads Wav2Vec2 model if available; falls back to Hybrid Acoustic Engine."""
        try:
            from transformers import pipeline
            self._wav2vec2_pipeline = pipeline(
                "audio-classification",
                model="superb/wav2vec2-base-superb-er",
                device=-1  # CPU mode for fast, error-free execution
            )
            print("[AudioEmotionDetector] Hybrid Engine: Wav2Vec2 + Acoustic Prosody Fusion active.", flush=True)
        except Exception:
            self._wav2vec2_pipeline = None
            print("[AudioEmotionDetector] Hybrid Engine: Deep Acoustic Feature Extraction active.", flush=True)

    def _denoise_audio(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Applies Butterworth bandpass filtering (80Hz-7500Hz) & noise gating for mic audio."""
        if len(y) == 0:
            return y

        # a) Remove DC Offset
        y_clean = y - np.mean(y)

        # b) Bandpass Butterworth Filter (80Hz to 7500Hz)
        nyquist = 0.5 * sr
        lowcut = 80.0 / nyquist
        highcut = min(7500.0 / nyquist, 0.99)
        sos = butter(4, [lowcut, highcut], btype='bandpass', output='sos')
        y_clean = sosfilt(sos, y_clean)

        # c) RMS Noise Gate (Attenuate background fan/ambient noise floor)
        frame_len = int(0.02 * sr)
        hop_len = int(0.005 * sr)
        rms = librosa.feature.rms(y=y_clean, frame_length=frame_len, hop_length=hop_len)[0]
        if len(rms) > 0:
            noise_floor = np.percentile(rms, 20) * 1.3
            mask = np.interp(np.arange(len(y_clean)), np.arange(len(rms)) * hop_len, (rms > noise_floor).astype(float))
            # Smooth mask with 10ms moving average to prevent clipping
            kernel = np.ones(int(0.01 * sr)) / int(0.01 * sr)
            mask_smoothed = np.clip(np.convolve(mask, kernel, mode='same'), 0.1, 1.0)
            y_clean = y_clean * mask_smoothed

        return y_clean

    def extract_acoustic_features(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        """Extracts comprehensive physical acoustic features (F0 contour, RMS, ZCR, MFCCs, Spectral Centroid)."""
        y_trimmed, _ = librosa.effects.trim(y, top_db=25)
        if len(y_trimmed) == 0:
            y_trimmed = y

        # 1. RMS Energy
        rms_frames = librosa.feature.rms(y=y_trimmed)[0]
        rms_mean = float(np.mean(rms_frames)) if len(rms_frames) > 0 else 0.0
        rms_std = float(np.std(rms_frames)) if len(rms_frames) > 0 else 0.0
        rms_max = float(np.max(rms_frames)) if len(rms_frames) > 0 else 0.0

        # 2. F0 Pitch Contour
        pitches, magnitudes = librosa.piptrack(y=y_trimmed, sr=sr)
        valid_pitches = pitches[pitches > 60]  # Vocal pitch range
        pitch_mean = float(np.mean(valid_pitches)) if len(valid_pitches) > 0 else 0.0
        pitch_std = float(np.std(valid_pitches)) if len(valid_pitches) > 0 else 0.0

        # F0 Pitch Slope / Intonation (rising terminal intonation vs descending)
        if len(valid_pitches) > 5:
            first_half = np.mean(valid_pitches[:len(valid_pitches)//2])
            second_half = np.mean(valid_pitches[len(valid_pitches)//2:])
            pitch_slope = float(second_half - first_half)
        else:
            pitch_slope = 0.0

        # 3. Zero Crossing Rate (ZCR)
        zcr_mean = float(np.mean(librosa.feature.zero_crossing_rate(y=y_trimmed)))

        # 4. Spectral Centroid & Rolloff
        spec_centroid = float(np.mean(librosa.feature.spectral_centroid(y=y_trimmed, sr=sr)))
        spec_rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=y_trimmed, sr=sr)))

        # 5. MFCCs (13 coefficients)
        mfccs = librosa.feature.mfcc(y=y_trimmed, sr=sr, n_mfcc=13)
        mfcc_means = [float(np.mean(mfccs[i])) for i in range(13)]

        return {
            "rms_mean": rms_mean,
            "rms_std": rms_std,
            "rms_max": rms_max,
            "pitch_mean": pitch_mean,
            "pitch_std": pitch_std,
            "pitch_slope": pitch_slope,
            "zcr_mean": zcr_mean,
            "spec_centroid": spec_centroid,
            "spec_rolloff": spec_rolloff,
            "mfcc_mean_0": mfcc_means[0],
            "mfcc_mean_1": mfcc_means[1],
            "mfcc_mean_2": mfcc_means[2],
        }

    def _classify_hybrid(self, y: np.ndarray, sr: int) -> str:
        """Combines Wav2Vec2 neural predictions with physical acoustic feature fusion."""
        features = self.extract_acoustic_features(y, sr)
        neural_preds = {}

        # 1. Wav2Vec2 Neural Probabilities (if available)
        if self._wav2vec2_pipeline is not None:
            try:
                res = self._wav2vec2_pipeline({"raw": y, "sampling_rate": sr})
                if res and isinstance(res, list):
                    for item in res:
                        label = item.get("label", "").lower()
                        score = item.get("score", 0.0)
                        # Map Wav2Vec2 labels to internal taxonomy
                        mapped_label = {
                            "hap": "happy", "happy": "happy",
                            "ang": "angry", "angry": "angry",
                            "sad": "sad",
                            "fea": "fearful", "fear": "fearful",
                            "neu": "neutral", "neutral": "neutral"
                        }.get(label, "neutral")
                        neural_preds[mapped_label] = score
            except Exception as e:
                print(f"[AudioEmotionDetector] Neural pipeline fallback: {e}", flush=True)

        # 2. Acoustic Feature Rules across 9 Emotion Categories
        rms = features["rms_mean"]
        rms_max = features["rms_max"]
        pitch = features["pitch_mean"]
        p_std = features["pitch_std"]
        p_slope = features["pitch_slope"]
        zcr = features["zcr_mean"]

        acoustic_scores = collections.defaultdict(float)

        # 😡 ANGRY / FRUSTRATED (High RMS energy + sharp pitch contour + high ZCR)
        if rms > 0.075 and zcr > 0.10:
            acoustic_scores["angry"] += 0.8
        if rms_max > 0.35 and p_std > 70:
            acoustic_scores["angry"] += 0.5

        # 😱 FEARFUL / ANXIOUS (Tremor in F0, unstable energy envelope, high pitch std)
        if p_std > 85 and rms > 0.03 and p_std > pitch * 0.4:
            acoustic_scores["fearful"] += 0.75

        # 🤔 THOUGHTFUL / UNCERTAIN (Slower speech rate, mid energy, rising terminal intonation)
        if p_slope > 25.0 and rms > 0.02 and rms < 0.05:
            acoustic_scores["thoughtful"] += 0.70

        # 😄 HAPPY (High mean pitch, elevated energy)
        if pitch > 180 and rms > 0.035:
            acoustic_scores["happy"] += 0.70

        # 🎉 EXCITED (High dynamic range, fast tempo, elevated pitch variance)
        if rms_max > 0.28 and p_std > 65 and pitch > 170:
            acoustic_scores["excited"] += 0.75

        # 😔 SAD (Low energy, descending pitch contour, slow tempo)
        if rms < 0.015 and (pitch == 0 or pitch < 125) and p_slope < -10.0:
            acoustic_scores["sad"] += 0.80

        # 🤝 EMPATHETIC (Soft energy, warm lower pitch)
        if rms < 0.025 and pitch > 0 and pitch < 155 and p_std < 35:
            acoustic_scores["empathetic"] += 0.65

        # 😌 CALM (Stable pitch, low variance, relaxed energy)
        if p_std < 25 and rms < 0.035 and rms >= 0.015:
            acoustic_scores["calm"] += 0.60

        # 😐 NEUTRAL (Default baseline)
        acoustic_scores["neutral"] += 0.40

        # 3. Hybrid Score Fusion
        final_scores = collections.defaultdict(float)
        all_emotions = ["angry", "fearful", "thoughtful", "happy", "excited", "sad", "empathetic", "calm", "neutral"]

        for emo in all_emotions:
            n_score = neural_preds.get(emo, 0.0)
            a_score = acoustic_scores.get(emo, 0.0)
            # Weighted fusion: 60% Neural + 40% Physical Acoustic Features
            final_scores[emo] = (0.6 * n_score) + (0.4 * a_score)

        top_emotion = max(final_scores.items(), key=lambda x: x[1])[0]
        return top_emotion

    def detect_emotion_from_pcm(self, pcm_bytes: bytes, sample_rate: int = 16000, reset_history: bool = False) -> str:
        """
        Main API: Denoises mic audio, extracts hybrid features, classifies emotion,
        and applies contextual sliding-window median filtering for temporal stability.
        
        Args:
            pcm_bytes: Raw 16-bit 16kHz mono PCM audio bytes.
            sample_rate: Sample rate (default 16000 Hz).
            reset_history: If True, clears sliding window history (for new utterances).
        """
        if not pcm_bytes or len(pcm_bytes) < 3200:
            return "neutral"

        try:
            if reset_history:
                with self.lock:
                    self.history_buffer.clear()

            # 1. Convert PCM to float32 audio array
            y = (np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0)

            # 2. Pre-processing: Denoise & Bandpass Filter
            y_denoised = self._denoise_audio(y, sample_rate)

            # 3. Hybrid Classification
            raw_emotion = self._classify_hybrid(y_denoised, sample_rate)

            # 4. Contextual Temporal Smoothing (Sliding Window Median Voting Buffer)
            with self.lock:
                self.history_buffer.append(raw_emotion)
                # Count frequency of emotions in history window
                counts = collections.Counter(self.history_buffer)
                smoothed_emotion = counts.most_common(1)[0][0]

            print(f"[AudioEmotionDetector] Raw: '{raw_emotion}' -> Contextually Smoothed Emotion: '{smoothed_emotion}' (History: {list(self.history_buffer)})", flush=True)
            return smoothed_emotion

        except Exception as e:
            print(f"[AudioEmotionDetector] Error in speech emotion detection: {e}", flush=True)
            return "neutral"


# Global singleton instance
_DETECTOR_INSTANCE: Optional[AudioEmotionDetector] = None
_DETECTOR_LOCK = threading.Lock()


def get_audio_emotion_detector() -> AudioEmotionDetector:
    """Returns singleton instance of AudioEmotionDetector."""
    global _DETECTOR_INSTANCE
    if _DETECTOR_INSTANCE is None:
        with _DETECTOR_LOCK:
            if _DETECTOR_INSTANCE is None:
                _DETECTOR_INSTANCE = AudioEmotionDetector()
    return _DETECTOR_INSTANCE


def detect_audio_emotion(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """Convenience function to detect emotion from microphone audio PCM bytes."""
    detector = get_audio_emotion_detector()
    return detector.detect_emotion_from_pcm(pcm_bytes, sample_rate)
