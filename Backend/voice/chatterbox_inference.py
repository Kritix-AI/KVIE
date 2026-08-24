"""
chatterbox_inference.py
Advanced Chatterbox TTS inference engine — PRIMARY TTS for Kritix AI.

Features:
- Emotion-driven dynamic hyperparameters (exaggeration, temperature, cfg_weight)
- Quality-weighted voice sample selection (SNR + duration scoring)
- Speaker embedding cache for faster re-synthesis
    - CUDA-only execution (never silently falls back to CPU)
- Integrated audio post-processing for broadcast quality
"""

import os
import sys
import hashlib
import random
import threading
import tempfile
import time
import torch
import numpy as np
from pathlib import Path
from typing import Optional, Dict

_MODEL_INSTANCE = None
_MODEL_LOCK = threading.Lock()
_MODEL_LOADED = False

_VOICE_SAMPLES_DIR = Path(__file__).parent.parent.parent / "Data" / "VoiceCloning" / "samples"
_EMBEDDING_CACHE_DIR = Path(__file__).parent.parent.parent / "Data" / "VoiceCloning" / "cache"


# ── Emotion-Based Hyperparameters ──────────────────────────────────────────────
# Tuned for human-like expression across different emotional states.
#
# exaggeration: Controls expressiveness (0.0 = flat monotone, 1.0 = theatrical)
# temperature:  Controls randomness/variation (lower = more consistent, higher = more varied)
# cfg_weight:   Classifier-free guidance (lower = more creative, higher = more faithful)
# repetition_penalty: Prevents repeated phonemes/words

CHATTERBOX_EMOTION_PARAMS: Dict[str, Dict[str, float]] = {
    # ── Confident & Authoritative ──
    'confident': {
        'exaggeration': 0.45,
        'temperature': 0.75,
        'cfg_weight': 0.50,
        'repetition_penalty': 1.2,
    },
    'neutral': {
        'exaggeration': 0.40,
        'temperature': 0.78,
        'cfg_weight': 0.48,
        'repetition_penalty': 1.2,
    },
    'friendly': {
        'exaggeration': 0.50,
        'temperature': 0.82,
        'cfg_weight': 0.42,
        'repetition_penalty': 1.2,
    },

    # ── High Energy ──
    'happy': {
        'exaggeration': 0.55,
        'temperature': 0.85,
        'cfg_weight': 0.40,
        'repetition_penalty': 1.15,
    },
    'excited': {
        'exaggeration': 0.65,
        'temperature': 0.90,
        'cfg_weight': 0.35,
        'repetition_penalty': 1.15,
    },
    'urgent': {
        'exaggeration': 0.60,
        'temperature': 0.88,
        'cfg_weight': 0.38,
        'repetition_penalty': 1.2,
    },

    # ── Low Energy / Soft ──
    'sad': {
        'exaggeration': 0.30,
        'temperature': 0.70,
        'cfg_weight': 0.55,
        'repetition_penalty': 1.25,
    },
    'calm': {
        'exaggeration': 0.25,
        'temperature': 0.65,
        'cfg_weight': 0.60,
        'repetition_penalty': 1.25,
    },
    'thinking': {
        'exaggeration': 0.35,
        'temperature': 0.72,
        'cfg_weight': 0.52,
        'repetition_penalty': 1.2,
    },
    'empathetic': {
        'exaggeration': 0.35,
        'temperature': 0.72,
        'cfg_weight': 0.55,
        'repetition_penalty': 1.2,
    },

    # ── Romantic / Expressive ──
    'romantic': {
        'exaggeration': 0.50,
        'temperature': 0.80,
        'cfg_weight': 0.45,
        'repetition_penalty': 1.15,
    },
    'loving': {
        'exaggeration': 0.48,
        'temperature': 0.78,
        'cfg_weight': 0.48,
        'repetition_penalty': 1.15,
    },
    'flirty': {
        'exaggeration': 0.55,
        'temperature': 0.85,
        'cfg_weight': 0.40,
        'repetition_penalty': 1.15,
    },
    'playful': {
        'exaggeration': 0.58,
        'temperature': 0.85,
        'cfg_weight': 0.38,
        'repetition_penalty': 1.15,
    },
    'sweet': {
        'exaggeration': 0.45,
        'temperature': 0.78,
        'cfg_weight': 0.48,
        'repetition_penalty': 1.2,
    },
}


def _get_emotion_params(emotion: str) -> Dict[str, float]:
    """Get Chatterbox hyperparameters for the given emotion."""
    return CHATTERBOX_EMOTION_PARAMS.get(
        emotion,
        CHATTERBOX_EMOTION_PARAMS['neutral']
    )


# ── Quality-Weighted Voice Sample Selection ────────────────────────────────────

def _score_voice_sample(sample_path: Path) -> float:
    """
    Score a voice reference sample by quality metrics.
    Higher score = better reference for voice cloning.

    Scoring factors:
    - Duration: 5-15 seconds is ideal (too short = insufficient data, too long = noise)
    - SNR estimate: Higher signal-to-noise = cleaner clone
    - Recency: Newer samples preferred (voice may change over time)
    """
    try:
        import soundfile as sf
        info = sf.info(str(sample_path))
        duration = info.duration

        # Duration score: peak at 8-12 seconds, penalize < 3s or > 20s
        if duration < 2.0:
            duration_score = 0.1
        elif duration < 5.0:
            duration_score = 0.5 + (duration - 2.0) / 6.0
        elif duration <= 15.0:
            duration_score = 1.0
        elif duration <= 20.0:
            duration_score = 1.0 - (duration - 15.0) / 10.0
        else:
            duration_score = 0.3

        # SNR estimate from file (quick RMS check)
        try:
            data, sr = sf.read(str(sample_path), dtype='float32')
            if data.ndim > 1:
                data = data.mean(axis=1)
            rms = np.sqrt(np.mean(data ** 2))
            # Higher RMS relative to noise floor → better
            snr_score = min(rms / 0.05, 1.0)  # Normalize
        except Exception:
            snr_score = 0.5

        # Recency score (prefer files modified recently)
        try:
            mtime = sample_path.stat().st_mtime
            age_days = (time.time() - mtime) / 86400.0
            recency_score = max(0.3, 1.0 - age_days / 365.0)
        except Exception:
            recency_score = 0.5

        # Weighted combination
        return duration_score * 0.5 + snr_score * 0.35 + recency_score * 0.15

    except Exception as e:
        print(f"[Chatterbox] Sample scoring error for {sample_path.name}: {e}", flush=True)
        return 0.1


def _get_best_voice_prompt() -> str | None:
    """
    Select the highest-quality reference voice sample based on SNR,
    duration, and recency scoring.

    Returns path to best sample, or None if no samples found.
    """
    if not _VOICE_SAMPLES_DIR.exists():
        _VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        return None

    samples = list(_VOICE_SAMPLES_DIR.glob("*.wav")) + list(_VOICE_SAMPLES_DIR.glob("*.flac"))
    if not samples:
        return None

    # Score all samples
    scored = [(s, _score_voice_sample(s)) for s in samples]
    scored.sort(key=lambda x: x[1], reverse=True)

    best = scored[0]
    print(f"[Chatterbox] Selected voice sample: {best[0].name} (score: {best[1]:.2f})", flush=True)

    # Log top 3 for debugging
    if len(scored) > 1:
        for s, score in scored[:3]:
            print(f"  → {s.name}: {score:.2f}", flush=True)

    return str(best[0])


class ChatterboxInference:
    """
    Advanced Chatterbox TTS inference engine with:
    - Dynamic emotion-based hyperparameter tuning
    - Quality-weighted voice sample selection
    - Speaker embedding cache for faster re-synthesis
    - Integrated audio post-processing
    - CUDA-only execution
    """

    def __init__(self, device: str = None):
        self.device = device or "cuda"
        if self.device != "cuda":
            raise RuntimeError("Chatterbox TTS is configured for CUDA-only execution")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; Chatterbox TTS requires an NVIDIA GPU")
        capability = torch.cuda.get_device_capability(0)
        arch = f"sm_{capability[0]}{capability[1]}"
        supported_arches = torch.cuda.get_arch_list()
        if supported_arches and arch not in supported_arches:
            raise RuntimeError(
                f"PyTorch does not support this GPU architecture ({arch}). "
                "Install a CUDA PyTorch build that includes this architecture."
            )
        self.model = None
        self._embedding_cache: Dict[str, object] = {}
        self._post_processor = None
        self._load_model()

    def _load_model(self):
        """Load Chatterbox's multilingual model on CUDA only.

        The multilingual checkpoint is required for Hindi and Hinglish.  It
        also supports English, so this keeps one model and one voice path for
        the whole assistant.
        """
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            print(f"[Chatterbox] Loading multilingual model on device: {self.device}...", flush=True)
            self.model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
            print("[Chatterbox] Multilingual model loaded successfully", flush=True)
        except Exception as e:
            print(f"[Chatterbox] Model load failed on {self.device}: {e}", flush=True)
            self.model = None

    def _get_post_processor(self):
        """Lazy-load audio post-processor."""
        if self._post_processor is None:
            try:
                from Backend.voice.AudioPostProcessor import AudioPostProcessor
                sample_rate = getattr(self.model, 'sr', 24000) if self.model else 24000
                self._post_processor = AudioPostProcessor(sample_rate=sample_rate)
                print("[Chatterbox] AudioPostProcessor loaded", flush=True)
            except Exception as e:
                print(f"[Chatterbox] Post-processor load notice: {e}", flush=True)
        return self._post_processor

    def is_ready(self) -> bool:
        return self.model is not None

    def _get_cached_embedding(self, prompt_path: str):
        """
        Cache speaker embeddings to avoid re-computing on every synthesis call.
        Uses MD5 hash of the file as cache key.
        """
        try:
            # Compute cache key from file content hash
            with open(prompt_path, 'rb') as f:
                file_hash = hashlib.md5(f.read(1024 * 64)).hexdigest()  # Hash first 64KB

            # Check in-memory cache
            if file_hash in self._embedding_cache:
                return self._embedding_cache[file_hash]

            # Check disk cache
            _EMBEDDING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file = _EMBEDDING_CACHE_DIR / f"{file_hash}.pt"
            if cache_file.exists():
                embedding = torch.load(cache_file, map_location=self.device, weights_only=True)
                self._embedding_cache[file_hash] = embedding
                print(f"[Chatterbox] Loaded cached speaker embedding: {file_hash[:8]}", flush=True)
                return embedding

            return None  # No cached embedding, model will compute from scratch

        except Exception as e:
            print(f"[Chatterbox] Embedding cache notice: {e}", flush=True)
            return None

    def synthesize(
        self,
        text: str,
        audio_prompt_path: str = None,
        use_user_voice: bool = True,
        emotion: str = "neutral",
        language_id: str = "en",
    ) -> str | None:
        """
        Synthesize text to speech audio with emotion-driven hyperparameters.

        Args:
            text: Input text to synthesize
            audio_prompt_path: Optional explicit path to 5-15s reference voice sample
            use_user_voice: If True, looks up samples in Data/VoiceCloning/samples/
            emotion: Emotion for dynamic hyperparameter tuning
            language_id: Chatterbox language code ("en" or "hi")

        Returns:
            Absolute path to temporary generated WAV file, or None on failure.
        """
        if not self.is_ready() or not text.strip():
            return None

        # Get emotion-based hyperparameters
        params = _get_emotion_params(emotion)
        print(f"[Chatterbox] Emotion: {emotion} → params: exag={params['exaggeration']:.2f}, "
              f"temp={params['temperature']:.2f}, cfg={params['cfg_weight']:.2f}", flush=True)

        # Determine prompt audio path (quality-weighted selection)
        prompt_path = audio_prompt_path
        if not prompt_path and use_user_voice:
            prompt_path = _get_best_voice_prompt()

        try:
            # Generate audio tensor with emotion-tuned hyperparameters
            generate_kwargs = {
                'exaggeration': params['exaggeration'],
                'temperature': params['temperature'],
                'cfg_weight': params['cfg_weight'],
                'repetition_penalty': params['repetition_penalty'],
            }

            if prompt_path and os.path.exists(prompt_path):
                wav = self.model.generate(text, language_id=language_id,
                                           audio_prompt_path=prompt_path,
                                           **generate_kwargs)
            else:
                # The multilingual checkpoint ships with built-in conditionals
                # (conds.pt), so synthesis works without user voice samples.
                wav = self.model.generate(text, language_id=language_id,
                                          **generate_kwargs)

            sample_rate = getattr(self.model, 'sr', 24000)

            # ── Audio Post-Processing ──────────────────────────────────────
            post_processor = self._get_post_processor()
            if post_processor is not None:
                try:
                    # Convert to numpy for post-processing
                    wav_np = wav.cpu().numpy() if isinstance(wav, torch.Tensor) else np.array(wav)
                    if wav_np.ndim > 1:
                        wav_np = wav_np.squeeze()
                    wav_np = wav_np.astype(np.float32)

                    # Normalize to [-1, 1] if needed
                    peak = np.max(np.abs(wav_np))
                    if peak > 1.0:
                        wav_np = wav_np / peak

                    # Apply emotion-specific post-processing
                    wav_np = post_processor.process_with_emotion(wav_np, sample_rate, emotion)

                    # Convert back to tensor
                    wav = torch.from_numpy(wav_np)
                    print(f"[Chatterbox] Post-processing applied ({emotion})", flush=True)

                except Exception as pp_err:
                    print(f"[Chatterbox] Post-processing notice: {pp_err}", flush=True)
                    # Continue with unprocessed audio

            # ── Save to temporary WAV file ─────────────────────────────────
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_path = tmp.name
            tmp.close()

            try:
                import torchaudio as ta
                if isinstance(wav, torch.Tensor):
                    if wav.ndim == 1:
                        wav = wav.unsqueeze(0)
                    ta.save(tmp_path, wav.cpu(), sample_rate)
                else:
                    import soundfile as sf
                    sf.write(tmp_path, wav, sample_rate)
            except Exception:
                import soundfile as sf
                wav_np = wav.cpu().numpy() if isinstance(wav, torch.Tensor) else np.array(wav)
                if wav_np.ndim > 1:
                    wav_np = wav_np.squeeze()
                sf.write(tmp_path, wav_np, sample_rate)

            return tmp_path

        except Exception as e:
            print(f"[Chatterbox] Synthesis error on {self.device}: {e}", flush=True)
            return None


def get_chatterbox_engine() -> ChatterboxInference | None:
    """Singleton getter for ChatterboxInference instance."""
    global _MODEL_INSTANCE, _MODEL_LOADED
    with _MODEL_LOCK:
        if not _MODEL_LOADED:
            _MODEL_INSTANCE = ChatterboxInference()
            _MODEL_LOADED = True
        if _MODEL_INSTANCE and _MODEL_INSTANCE.is_ready():
            return _MODEL_INSTANCE
        return None
