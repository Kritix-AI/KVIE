"""
Voice/STT.py - Unified Speech-to-Text (offline, faster-whisper)
No cloud APIs. All processing is local.

Public API:
    transcribe(audio, duration, language) -> str
    transcribe_pcm(pcm, duration) -> (str, str)   # (text, lang)
    record_audio(timeout, silence_duration) -> (bytes, float)
    listen(timeout, silence_duration) -> str       # record + transcribe + post-process
    SpeechRecognition() -> str                     # legacy entry point
    correct_text(text) -> str
    query_modifier(text) -> str
    detect_language(text) -> str                   # "en" | "hi" | "hinglish"
    is_loaded() -> bool
    get_model() -> WhisperModel | None
    warmup(model_name) -> bool
    get_device_telemetry() -> Dict[str, Any]
    get_active_device() -> str | None
    get_active_compute_type() -> str | None
"""

import os
import re
import sys
import threading
from typing import Optional, Tuple, Dict, Any, Union
from dataclasses import dataclass

if sys.platform == "win32":
    import codecs
    try:
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
    except Exception:
        pass

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE        = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
_ROOT        = os.path.dirname(_BACKEND_DIR)
_DATA_DIR    = os.path.join(_ROOT, "Data")
os.makedirs(_DATA_DIR, exist_ok=True)


def _register_nvidia_dlls() -> None:
    """Make cuBLAS/cuDNN from nvidia pip wheels loadable for CTranslate2 GPU inference.

    Supports:
      - Windows (.dll via os.add_dll_directory and PATH)
      - Linux (.so via LD_LIBRARY_PATH and ctypes.CDLL preloading with RTLD_GLOBAL)
        for Docker and GConnect containers.
    """
    try:
        import site
        import ctypes
        seen = set()
        search_paths = []
        try:
            search_paths.extend(site.getsitepackages())
        except Exception:
            pass
        try:
            search_paths.append(site.getusersitepackages())
        except Exception:
            pass

        is_windows = sys.platform == "win32"
        rtld_mode = getattr(ctypes, "RTLD_GLOBAL", 0)

        for sp in search_paths:
            nvidia_dir = os.path.join(sp, "nvidia")
            if not os.path.isdir(nvidia_dir) or nvidia_dir in seen:
                continue
            seen.add(nvidia_dir)
            for root, _dirs, files in os.walk(nvidia_dir):
                dll_files = [f for f in files if f.lower().endswith(".dll")]
                so_files = [f for f in files if f.lower().endswith(".so") or ".so." in f.lower()]

                if is_windows and dll_files:
                    try:
                        os.add_dll_directory(root)
                    except OSError:
                        pass
                    # CTranslate2 loads CUDA libraries with plain LoadLibrary
                    # semantics, which search PATH but not add_dll_directory.
                    os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                elif not is_windows and so_files:
                    ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                    if root not in ld_path.split(os.pathsep):
                        os.environ["LD_LIBRARY_PATH"] = (root + os.pathsep + ld_path) if ld_path else root
                    for f in sorted(so_files):
                        so_path = os.path.join(root, f)
                        try:
                            ctypes.CDLL(so_path, mode=rtld_mode)
                        except Exception:
                            pass
    except Exception:
        pass


_register_nvidia_dlls()


# ── Config ────────────────────────────────────────────────────────────────────

def _cuda_available() -> bool:
    """True when a usable CUDA device is present (GPU acceleration is optional;
    everything runs on CPU otherwise)."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


@dataclass
class STTConfig:
    model_name: str = "Systran/faster-whisper-large-v3-turbo"
    sample_rate: int = 16000
    device: str = "cuda"
    skip_vad: bool = True  # faster-whisper has built-in VAD, skip Silero double-filter

    @classmethod
    def from_env(cls):
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_ROOT, ".env"))
        configured_model = (
            env.get("ASRModel")
            or env.get("WhisperModel")
            or env.get("WhisperModelSize")
            or "Systran/faster-whisper-large-v3-turbo"
        )
        # An explicit ASRDevice wins; otherwise auto-detect so the GPU is used
        # when present and CPU works out of the box when it is not.
        device = env.get("ASRDevice") or env.get("WhisperDevice") or ("cuda" if _cuda_available() else "cpu")
        return cls(
            model_name=configured_model,
            sample_rate=int(env.get("STTSampleRate") or "16000"),
            device=device,
        )


# ── Model ─────────────────────────────────────────────────────────────────────

_asr_model = None
_asr_engine_type = None  # "faster_whisper" or "openai_whisper"
_loaded_device: Optional[str] = None  # device the active model actually runs on
_loaded_compute_type: Optional[str] = None  # compute type of the active model
_stt_lock  = threading.Lock()


def get_active_device() -> Optional[str]:
    """Device of the currently loaded model ('cuda'/'cpu'), or None if unloaded."""
    return _loaded_device if _asr_model is not None else None


def get_active_compute_type() -> Optional[str]:
    """Compute type of the currently loaded model, or None if unloaded."""
    return _loaded_compute_type if _asr_model is not None else None


def get_model(config: Optional[STTConfig] = None):
    global _asr_model, _asr_engine_type
    if _asr_model is not None:
        return _asr_model

    # Double-checked locking: two concurrent sessions must not both construct
    # a WhisperModel (the loser leaked its model and the last write won).
    with _stt_lock:
        if _asr_model is not None:
            return _asr_model
        return _load_model_locked(config)


def _load_model_locked(config: Optional[Union[STTConfig, str]] = None):
    global _asr_model, _asr_engine_type, _loaded_device, _loaded_compute_type
    if isinstance(config, str):
        cfg = STTConfig.from_env()
        cfg.model_name = config
    else:
        cfg = config or STTConfig.from_env()
    used_device = cfg.device
    print(f"[STT] Loading Whisper model: {cfg.model_name} on {cfg.device}", flush=True)

    # 1. Try faster-whisper CTranslate2 Engine (Ultra Fast)
    try:
        from faster_whisper import WhisperModel
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_ROOT, ".env"))
        compute_type = env.get("WhisperComputeType") or ("float16" if cfg.device == "cuda" else "int8")
        
        from Backend.voice.ModelManager import get_model_snapshot_path
        raw_name = cfg.model_name
        target_model = get_model_snapshot_path(raw_name)
        if target_model is None and raw_name in {"Systran/faster-whisper-large-v3-turbo", "large-v3-turbo"}:
            # Graceful local fallback to kritix-stt snapshot if turbo is not yet installed
            fallback_snapshot = get_model_snapshot_path("kritix-stt")
            if fallback_snapshot is not None:
                print(f"[STT] Model snapshot for '{raw_name}' not found locally; falling back to installed 'kritix-stt'", flush=True)
                target_model = fallback_snapshot
        if target_model is None:
            raise FileNotFoundError(
                f"The selected speech model '{raw_name}' has no complete local model.bin snapshot. "
                "Download it from the Models page, then retry."
            )

        try:
            _asr_model = WhisperModel(
                target_model,
                device=cfg.device,
                compute_type=compute_type,
                local_files_only=True,
            )
        except Exception as device_error:
            if cfg.device == "cpu":
                raise device_error
            # Windows PCs without a usable CUDA/cuDNN stack can still run the
            # selected cached model on CPU. Loading stays local-only so model
            # downloads always go through the visible model manager.
            _asr_model = WhisperModel(
                target_model,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(4, os.cpu_count() or 4),
                local_files_only=True,
            )
            used_device = "cpu"

        # CTranslate2 can accept a CUDA model even when its CUDA libraries
        # (for example cuBLAS) are unavailable; the error then appears only
        # on the first transcription. Probe one tiny silent sample at load
        # time so that this machine reliably falls back to CPU before audio
        # capture starts.
        if cfg.device != "cpu":
            try:
                import numpy as np
                probe_segments, _ = _asr_model.transcribe(
                    np.zeros(16000, dtype=np.float32),
                    language="en",
                    beam_size=1,
                    vad_filter=False,
                )
                next(iter(probe_segments), None)
            except Exception as device_error:
                print(
                    f"[STT] CUDA inference unavailable ({type(device_error).__name__}); "
                    "reloading the selected model on CPU",
                    flush=True,
                )
                _asr_model = WhisperModel(
                    target_model,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=max(4, os.cpu_count() or 4),
                    local_files_only=True,
                )
                used_device = "cpu"
                compute_type = "int8 (CPU fallback)"

        _asr_engine_type = "faster_whisper"
        _loaded_device = used_device
        _loaded_compute_type = compute_type
        print(f"[STT] Loaded faster-whisper CTranslate2 model ({target_model}, device={_loaded_device}, compute_type={compute_type})", flush=True)
        return _asr_model
    except Exception as e:
        print(f"[STT] faster-whisper load notice: {e}", flush=True)
        _loaded_compute_type = None

    # Do not let a missing CTranslate2 model trigger an untracked PyTorch model
    # download. ModelManager is the sole download path and reports progress.
    return None


def is_loaded() -> bool:
    """Return current load state without triggering model loading or network IO."""
    return _asr_model is not None


def warmup(model_name: Optional[str] = None) -> bool:
    """Execute a 0.5s silent audio inference to pre-initialize model kernels and memory.

    Returns True if warmup inference succeeded, False if model is unavailable
    or inference could not be completed. Non-blocking and exception-safe.
    """
    try:
        with _stt_lock:
            global _asr_model
            model = _asr_model
            if model is None:
                cfg = None
                if model_name:
                    cfg = STTConfig.from_env()
                    cfg.model_name = model_name
                model = _load_model_locked(cfg)

            if model is None:
                target = model_name or "default"
                print(f"[STT] Warmup notice: model '{target}' not loaded (snapshot missing)", flush=True)
                return False

            import numpy as np
            # 0.5s of silent audio at 16000Hz = 8000 samples
            silent_audio = np.zeros(8000, dtype=np.float32)

            if hasattr(model, "transcribe"):
                result = model.transcribe(
                    silent_audio,
                    language="en",
                    beam_size=1,
                    vad_filter=False,
                )
                if isinstance(result, tuple):
                    segments, _ = result
                    # Drain generator to ensure execution through CTranslate2/PyTorch kernels
                    next(iter(segments), None)

            print(
                f"[STT] Warmup completed successfully (model={model_name or getattr(_asr_model, 'model_name', 'default')}, "
                f"device={_loaded_device}, compute={_loaded_compute_type})",
                flush=True,
            )
            return True
    except Exception as exc:
        print(f"[STT] Warmup warning (non-fatal): {exc}", flush=True)
        return False


def get_device_telemetry() -> Dict[str, Any]:
    """Return structured device, compute type, and VRAM telemetry via PyTorch/NVML.

    Returns a structured dictionary:
        gpu_name: string or None
        compute_type: string or None (e.g., "float16", "int8_float16", "int8")
        vram_allocated_mb: int or None
        vram_reserved_mb: int or None
        vram_total_mb: int or None
        vram_free_mb: int or None
        device: string ("cuda" or "cpu")
        gpu_available: bool
    """
    active_device = get_active_device()
    active_compute = get_active_compute_type()
    gpu_avail = _cuda_available()

    if active_device is not None:
        device = active_device
        compute_type = active_compute or ("float16" if device == "cuda" else "int8")
    else:
        try:
            cfg = STTConfig.from_env()
            device = cfg.device
            from dotenv import dotenv_values
            env = dotenv_values(os.path.join(_ROOT, ".env"))
            compute_type = env.get("WhisperComputeType") or ("float16" if device == "cuda" else "int8")
        except Exception:
            device = "cuda" if gpu_avail else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"

    telemetry: Dict[str, Any] = {
        "gpu_name": None,
        "compute_type": compute_type,
        "vram_allocated_mb": None,
        "vram_reserved_mb": None,
        "vram_total_mb": None,
        "vram_free_mb": None,
        "device": device,
        "gpu_available": gpu_avail,
    }

    # 1. Query PyTorch CUDA telemetry
    try:
        import torch
        if torch.cuda.is_available():
            telemetry["gpu_available"] = True
            telemetry["gpu_name"] = str(torch.cuda.get_device_name(0))
            telemetry["vram_allocated_mb"] = int(torch.cuda.memory_allocated(0) // (1024 * 1024))
            telemetry["vram_reserved_mb"] = int(torch.cuda.memory_reserved(0) // (1024 * 1024))
            try:
                free_bytes, total_bytes = torch.cuda.mem_get_info(0)
                telemetry["vram_free_mb"] = int(free_bytes // (1024 * 1024))
                telemetry["vram_total_mb"] = int(total_bytes // (1024 * 1024))
            except Exception:
                pass
    except Exception:
        pass

    # 2. Query NVML fallback if PyTorch did not yield GPU name or total VRAM
    if telemetry["gpu_name"] is None or telemetry["vram_total_mb"] is None:
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            telemetry["gpu_available"] = True
            if telemetry["gpu_name"] is None:
                name = pynvml.nvmlDeviceGetName(handle)
                telemetry["gpu_name"] = name.decode("utf-8") if isinstance(name, bytes) else str(name)
            if telemetry["vram_total_mb"] is None:
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                telemetry["vram_total_mb"] = int(mem_info.total // (1024 * 1024))
                telemetry["vram_free_mb"] = int(mem_info.free // (1024 * 1024))
                if telemetry["vram_allocated_mb"] is None:
                    telemetry["vram_allocated_mb"] = int(mem_info.used // (1024 * 1024))
            pynvml.nvmlShutdown()
        except Exception:
            pass

    # If no GPU is available and model is not loaded, normalize device to "cpu"
    if not telemetry["gpu_available"] and active_device is None:
        telemetry["device"] = "cpu"
        if telemetry["compute_type"] == "float16":
            telemetry["compute_type"] = "int8"

    return telemetry


# ── Silero VAD Pre-filter ─────────────────────────────────────────────────────

_vad_model = None
_vad_utils = None
_vad_lock = threading.Lock()


def _load_silero_vad():
    """Load Silero VAD model (lazy, once)."""
    global _vad_model, _vad_utils
    if _vad_model is not None:
        return True
    with _vad_lock:
        if _vad_model is not None:
            return True
        try:
            import torch
            _vad_model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                trust_repo=True,
            )
            _vad_utils = utils
            print("[STT] Silero VAD loaded successfully", flush=True)
            return True
        except Exception as e:
            print(f"[STT] Silero VAD load notice: {e}", flush=True)
            return False


def _vad_filter(audio_float32, sr: int = 16000):
    """
    Use Silero VAD to extract only speech segments from audio,
    removing silence, background noise, and non-speech segments.

    IMPORTANT: When streaming (sliding windows), skip VAD to avoid
    chopping speech into fragments. Only use VAD for full-utterance
    recordings.
    """
    return audio_float32  # Disabled: faster-whisper has built-in VAD that's sufficient


# ── Hot-Word Boosting ─────────────────────────────────────────────────────────

# Domain vocabulary that Whisper frequently misrecognizes
_HOTWORD_PROMPT = "KVIE, Kritix, Python, TypeScript, React, Vite, FastAPI, WebSocket, API, GitHub"


# ── Language Detection ────────────────────────────────────────────────────────

_HINDI_CHARS = set(range(0x0900, 0x0980))

_HINDI_WORDS = {
    "kya", "kaise", "kahan", "kaun", "kab", "kyun", "kyu",
    "sun", "suno", "suniye", "dekh", "dekho", "bolo",
    "accha", "acha", "bahut", "bohot", "theek",
    "nahi", "nahee", "haan", "han", "ji", "haanji",
    "matlab", "toh", "yaani", "arey", "yaar", "bhai", "behen",
    "namaste", "namaskar", "pranaam", "dhanyavaad", "shukriya",
    "ke", "ka", "ki", "ko", "se", "pe", "par",
    "main", "mera", "meri", "tum", "tera", "teri", "aap",
    "yeh", "woh", "yah", "vah", "idhar", "udhar", "wahan",
    "abhi", "tab", "phir", "ab", "fir", "jab",
    "bilkul", "sahi", "galat", "ekdum", "saaf", "ek", "do", "teen",
}


def detect_language(text: str) -> str:
    """Returns 'en', 'hi', or 'hinglish'."""
    if not text:
        return "en"
    has_hindi_chars = any(ord(c) in _HINDI_CHARS for c in text)
    if has_hindi_chars:
        return "hi"
    words = set(re.findall(r"\b\w+\b", text.lower()))
    ratio = len(words & _HINDI_WORDS) / max(len(words), 1)
    if ratio > 0.6:
        return "hi"
    if ratio >= 0.2:
        return "hinglish"
    return "en"


def _save_language(lang: str):
    try:
        with open(os.path.join(_DATA_DIR, "Language.data"), "w", encoding="utf-8") as f:
            f.write(lang)
    except Exception:
        pass


# ── Text Post-Processing ──────────────────────────────────────────────────────

HALLUCINATION_BLACKLIST_REGEX = re.compile(
    r"(?i)^(\s*(thank you for watching|thanks for watching|please subscribe|"
    r"subtitles by|translated by|like and subscribe|watching!|see you next time|"
    r"hello\?|amara\.org|transcript by|captioning by)\s*[.?!]*\s*)+$"
)

SAFE_CORRECTIONS = {
    "your duped": "youtube", "you duped": "youtube",
    "your tube": "youtube",  "you tube": "youtube", "dupe": "youtube",
    "crome": "chrome",       "chrom": "chrome",
    "spot if i": "spotify",  "spot if y": "spotify",
    "spoti fi": "spotify",   "spotifyy": "spotify",
    "goggle": "google",      "gogle": "google",
    "how are u": "how are you", "how r u": "how are you",
    "thank u": "thank you",  "thx": "thanks", "ty": "thank you",
}


def correct_text(text: str) -> str:
    # Apply brand/typo corrections WITHOUT flattening case — the old
    # text.lower() destroyed capitalization for every HTTP-transcribed final.
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    if HALLUCINATION_BLACKLIST_REGEX.match(t):
        return ""
    for wrong, right in SAFE_CORRECTIONS.items():
        t = re.sub(rf"\b{re.escape(wrong)}\b", right, t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def query_modifier(text: str) -> str:
    q = text.strip()
    if not q:
        return q
    words = q.split()
    question_starters = {
        "what", "when", "where", "who", "how", "why", "which", "whom", "whose",
        "is", "are", "do", "does", "did", "can", "could", "will", "would",
        "should", "may", "might",
        "kya", "kab", "kahan", "kaun", "kaise", "kyun", "kyu",
        "kitna", "kitne", "kitni", "kese", "kaisi", "kaisa",
    }
    if words[0].lower() in question_starters:
        q = q.rstrip(".!?") + "?"
    elif q[-1] not in ".!?":
        q += "."
    return q[0].upper() + q[1:]


def _strip_wake_phrase(text: str) -> str:
    """Return text as-is — wake word stripping removed with wake word system."""
    return text.strip()


# ── Status Helpers ────────────────────────────────────────────────────────────

def _set_status(status: str):
    try:
        with open(os.path.join(_DATA_DIR, "Status.data"), "w", encoding="utf-8") as f:
            f.write(status)
    except Exception:
        pass


def _set_mic(status: str):
    try:
        with open(os.path.join(_DATA_DIR, "Mic.data"), "w", encoding="utf-8") as f:
            f.write(status)
    except Exception:
        pass


# ── Core Transcription ────────────────────────────────────────────────────────

def transcribe(audio: bytes, duration: float = 0.0, language: str = "auto") -> str:
    """
    Transcribe raw 16kHz mono 16-bit PCM bytes using Whisper.
    Returns plain text (no post-processing).

    Features:
    - Silero VAD pre-filtering (strips silence/noise)
    - Hot-word boosting via initial_prompt
    - Confidence-based retry with larger beam size
    """
    if not audio or duration < 0.3:
        return ""
    model = get_model()
    if model is None:
        return ""
    try:
        import numpy as np
        arr = (np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0)

        # Pre-filter with Silero VAD to remove silence/noise
        arr = _vad_filter(arr, sr=16000)
        if len(arr) < int(0.3 * 16000):  # Less than 0.3s of speech
            return ""

        # "hinglish" is a KVIE-level pseudo-language (Roman-script Hindi+English);
        # faster-whisper would reject it, so it maps to auto-detect with the
        # Hinglish-biased initial prompt.
        lang_arg = None if language in ("auto", "hinglish") else language

        if _asr_engine_type == "faster_whisper":
            # First pass: fast beam_size=1
            text, confidence = _transcribe_faster_whisper(
                model, arr, lang_arg, beam_size=1
            )

            # Confidence-based retry: if low confidence and enough audio, retry with larger beam
            if confidence < 0.5 and duration > 1.5 and len(arr) > 24000:
                print(f"[STT] Low confidence ({confidence:.2f}), retrying with beam_size=5", flush=True)
                text2, confidence2 = _transcribe_faster_whisper(
                    model, arr, lang_arg, beam_size=5
                )
                if confidence2 > confidence:
                    text = text2
                    confidence = confidence2
                    print(f"[STT] Retry improved confidence to {confidence:.2f}", flush=True)

        else:
            # OpenAI Whisper
            kwargs = {'initial_prompt': _HOTWORD_PROMPT}
            if lang_arg:
                kwargs["language"] = lang_arg
            res = model.transcribe(arr, **kwargs)
            text = res.get("text", "").strip() if isinstance(res, dict) else ""
            text = re.sub(r"\s+", " ", text).strip()

        if text:
            print(f"[STT] Whisper ({_asr_engine_type}): '{text}'", flush=True)
        return text
    except Exception as e:
        print(f"[STT] Transcription error: {e}", flush=True)
        return ""


def _transcribe_faster_whisper(model, arr, lang_arg, beam_size: int = 1):
    """
    Internal faster-whisper transcription with configurable beam size.
    Returns (text, confidence_score).
    """
    segments, info = model.transcribe(
        arr,
        language=lang_arg,
        task="transcribe",
        beam_size=beam_size,
        temperature=0.0,
        repetition_penalty=1.15,
        compression_ratio_threshold=2.4,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        condition_on_previous_text=False,
        without_timestamps=False,
        hallucination_silence_threshold=1.5,
        initial_prompt=_HOTWORD_PROMPT,
    )

    all_segments = list(segments)
    text = " ".join(s.text.strip() for s in all_segments if s.text and s.text.strip())
    text = re.sub(r"\s+", " ", text).strip()

    # Discard hallucinated subtitle artifacts immediately at transcription level
    if HALLUCINATION_BLACKLIST_REGEX.match(text):
        return "", 0.0

    # Calculate confidence from average log probability
    # NOTE: faster-whisper's Segment attribute is `avg_logprob` (no underscore) —
    # the old `avg_log_prob` raised AttributeError inside the caller's try/except,
    # which silently returned empty text for EVERY transcription.
    if all_segments:
        avg_log_prob = sum(s.avg_logprob for s in all_segments) / len(all_segments)
        # Convert log probability to 0-1 confidence score
        confidence = min(1.0, max(0.0, 1.0 + avg_log_prob / 2.0))
    else:
        confidence = 0.0

    if info.language_probability < 0.5 and not text:
        return "", 0.0

    return text, confidence


def transcribe_with_confidence(
    audio: bytes, duration: float = 0.0, language: str = "auto", retry: bool = True
) -> Tuple[str, float]:
    """Transcribe PCM and return ``(text, confidence)``.

    This is the confidence-aware public counterpart to :func:`transcribe`.
    It uses a fast greedy pass and retries with beam search when the first
    result is uncertain.  The confidence is derived from Whisper's segment
    log-probabilities, so callers can decide whether to ask the user to repeat.
    """
    if not audio or duration < 0.3:
        return "", 0.0
    model = get_model()
    if model is None:
        return "", 0.0
    try:
        import numpy as np
        arr = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        arr = _vad_filter(arr, sr=16000)
        if len(arr) < int(0.3 * 16000):
            return "", 0.0

        lang_arg = None if language in ("auto", "hinglish") else language
        if _asr_engine_type == "faster_whisper":
            text, confidence = _transcribe_faster_whisper(model, arr, lang_arg, 1)
            # The beam-5 retry is for one-shot HTTP transcribes only: on the
            # CPU fallback it can run for tens of seconds, and in the streaming
            # path it blocks the worker so the flush never completes.
            if retry and confidence < 0.65 and duration > 1.0 and len(arr) > 16000:
                retry_text, retry_confidence = _transcribe_faster_whisper(model, arr, lang_arg, 5)
                if retry_confidence > confidence:
                    text, confidence = retry_text, retry_confidence
            return text, confidence

        kwargs = {"initial_prompt": _HOTWORD_PROMPT}
        if lang_arg:
            kwargs["language"] = lang_arg
        result = model.transcribe(arr, **kwargs)
        text = re.sub(r"\s+", " ", result.get("text", "")).strip()
        segments = result.get("segments", [])
        log_probs = [s.get("avg_logprob") for s in segments if s.get("avg_logprob") is not None]
        confidence = min(1.0, max(0.0, 1.0 + (sum(log_probs) / len(log_probs)) / 2.0)) if log_probs else (1.0 if text else 0.0)
        return text, confidence
    except Exception as e:
        print(f"[STT] Confidence transcription error: {e}", flush=True)
        return "", 0.0


# alias for compatibility
transcribe_blocking = transcribe


def transcribe_pcm(pcm: bytes, duration: float, language: str = "auto", input_rate: int = 44100) -> Tuple[str, str]:
    """
    Transcribe PCM (any sample rate) with DSP preprocessing.
    Returns (text, language_code).
    """
    if not pcm or duration < 0.2:
        return "", "en"
    try:
        from Backend.voice.DSP import DSPPipeline
        dsp = DSPPipeline(input_rate=input_rate, target_rate=16000, boost_db=12.0)
        pcm_16k = dsp.process_to_int16_rate(pcm, target_rate=16000)
        dur_16k = len(pcm_16k) / (16000 * 2)
        text = transcribe(pcm_16k, dur_16k, language)
    except Exception:
        text = transcribe(pcm, duration, language)

    if not text:
        return "", "en"

    lang = detect_language(text)
    _save_language(lang)
    print(f"[STT] Language: {lang}")
    return text, lang


# ── Audio Recording ───────────────────────────────────────────────────────────

def _get_mic_device_index() -> int | None:
    """Read STTDeviceIndex from .env; return None to use system default."""
    try:
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_ROOT, ".env"))
        val = env.get("STTDeviceIndex")
        return int(val) if val else None
    except Exception:
        return None


def record_audio(
    timeout: float = 10.0,
    silence_duration: float = 1.5,
    sample_rate: int = 16000,
) -> Tuple[bytes, float]:
    """Record from mic until silence or timeout. Returns (pcm_bytes, duration)."""
    import pyaudio
    import numpy as np

    p = pyaudio.PyAudio()
    chunk = 1024
    stream = last_exc = None
    device_index = _get_mic_device_index()

    open_kwargs_list = []
    if device_index is not None:
        open_kwargs_list += [
            {"input_device_index": device_index, "channels": 1},
            {"input_device_index": device_index, "channels": 2},
        ]
    open_kwargs_list += [{"channels": 1}, {"channels": 2}]

    for kw in open_kwargs_list:
        try:
            stream = p.open(
                format=pyaudio.paInt16, rate=sample_rate,
                input=True, frames_per_buffer=chunk, **kw
            )
            break
        except Exception as exc:
            last_exc = exc

    if stream is None:
        raise last_exc or RuntimeError("Cannot open microphone")

    # Calibrate noise floor over 20 frames (~1.3s at 16kHz/1024)
    noise_samples = []
    for _ in range(20):
        try:
            data = stream.read(chunk, exception_on_overflow=False)
        except Exception:
            break
        a = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        noise_samples.append(float(np.sqrt(np.mean(a ** 2))))

    noise_floor = float(np.median(noise_samples)) if noise_samples else 200.0
    # Additive margin: threshold = noise_floor + 40% of noise_floor, min 150 above floor
    threshold = noise_floor + max(noise_floor * 0.4, 150)
    threshold = max(threshold, 300)
    print(f"[STT] Noise: {noise_floor:.0f}, Threshold: {threshold:.0f}", flush=True)

    frames = []
    silence_count  = 0
    silence_needed = int(silence_duration * sample_rate / chunk)
    max_frames     = int(timeout * sample_rate / chunk)
    speech_started = False

    try:
        for _ in range(max_frames):
            try:
                data = stream.read(chunk, exception_on_overflow=False)
            except OSError:
                break
            frames.append(data)
            energy = float(np.sqrt(np.mean(np.frombuffer(data, dtype=np.int16).astype(np.float32) ** 2)))
            if energy < threshold:
                silence_count += 1
                if silence_count >= silence_needed and speech_started:
                    break
            else:
                silence_count = 0
                speech_started = True
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    if not frames:
        return b"", 0.0
    audio_bytes = b"".join(frames)
    duration    = len(frames) * chunk / sample_rate
    return (audio_bytes, duration) if duration >= 0.3 else (b"", 0.0)


# ── High-Level listen() ───────────────────────────────────────────────────────

def listen(
    timeout: float = 10.0,
    silence_duration: float = 1.5,
    language: str = "auto",
) -> str:
    """Record + transcribe + post-process. Returns final cleaned text."""
    audio, duration = record_audio(timeout=timeout, silence_duration=silence_duration)
    if not audio:
        return ""
    text = transcribe(audio, duration, language)
    if not text:
        return ""
    lang = detect_language(text)
    _save_language(lang)
    return text


# ── Legacy SpeechRecognition() entry point ────────────────────────────────────

def SpeechRecognition(previous_text: str = "") -> str:
    """
    Full pipeline: mic gate → record → transcribe → correct → strip wake phrase
    → query_modifier. Drop-in replacement for Backend.SpeechToText.SpeechRecognition.
    """
    try:
        from Backend.TextToSpeech import is_currently_speaking
        if is_currently_speaking():
            return ""
    except Exception:
        pass

    _set_mic("ON")
    _set_status("Listening")
    text = ""

    try:
        audio, duration = record_audio(timeout=10.0, silence_duration=1.5)
        if not audio or duration < 0.3:
            print("[STT] No speech detected", flush=True)
            return ""

        print(f"[STT] Transcribing {duration:.1f}s...", flush=True)
        text = transcribe(audio, duration)

        if not text:
            return ""

        lang = detect_language(text)
        _save_language(lang)

        text = _strip_wake_phrase(correct_text(text))

        if len(text.split()) < 1 or len(text) < 2:
            return ""
        if len(set(text.lower())) < 4 and len(text) > 5:
            print("[STT] Rejected as gibberish", flush=True)
            return ""

        text = query_modifier(text)
        print(f"[STT] Final ({lang}): {text}", flush=True)
        return text

    except Exception as e:
        print(f"[STT] Error: {e}", flush=True)
        return ""
    finally:
        _set_mic("OFF")


def detect_voice_emotion(pcm: bytes, sample_rate: int = 16000) -> str:
    """
    Detect human emotion directly from spoken microphone PCM audio bytes.
    Returns: 'happy', 'excited', 'sad', 'calm', 'urgent', or 'neutral'.
    """
    try:
        from Backend.voice.AudioEmotionDetector import detect_audio_emotion
        return detect_audio_emotion(pcm, sample_rate)
    except Exception as e:
        print(f"[STT] Voice emotion detection notice: {e}", flush=True)
        return "neutral"


# ── Standalone Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("STT Test", flush=True)
    model = get_model()
    if not model:
        print("ERROR: model not loaded", flush=True)
        exit(1)
    print("Model ready. Recording 5s...", flush=True)
    audio, dur = record_audio(timeout=5.0, silence_duration=1.0)
    if audio:
        print(f"Recorded {dur:.1f}s", flush=True)
        result = SpeechRecognition.__wrapped__ if hasattr(SpeechRecognition, "__wrapped__") else None
        text = transcribe(audio, dur)
        print(f"Raw: '{text}'", flush=True)
        print(f"Processed: '{query_modifier(correct_text(text))}'", flush=True)
    else:
        print("No audio", flush=True)
