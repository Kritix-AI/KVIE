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
"""

import os
import re
import sys
import threading
from typing import Optional, Tuple
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


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class STTConfig:
    model_name: str = "large-v3-turbo"
    sample_rate: int = 16000
    device: str = "cuda"

    @classmethod
    def from_env(cls):
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_ROOT, ".env"))
        return cls(
            model_name=(
                env.get("ASRModel")
                or env.get("WhisperModel")
                or env.get("WhisperModelSize")
                or "large-v3-turbo"
            ),
            sample_rate=int(env.get("STTSampleRate") or "16000"),
            device=env.get("ASRDevice") or env.get("WhisperDevice") or "cuda",
        )


# ── Model ─────────────────────────────────────────────────────────────────────

_asr_model = None
_asr_engine_type = None  # "faster_whisper" or "openai_whisper"
_stt_lock  = threading.Lock()


def get_model(config: Optional[STTConfig] = None):
    global _asr_model, _asr_engine_type
    if _asr_model is not None:
        return _asr_model

    cfg = config or STTConfig.from_env()
    print(f"[STT] Loading Whisper model: {cfg.model_name} on {cfg.device}", flush=True)

    # 1. Try faster-whisper CTranslate2 Engine (Ultra Fast)
    try:
        from faster_whisper import WhisperModel
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_ROOT, ".env"))
        compute_type = env.get("WhisperComputeType") or ("float16" if cfg.device == "cuda" else "int8")
        
        target_model = cfg.model_name
        try:
            _asr_model = WhisperModel(target_model, device=cfg.device, compute_type=compute_type)
        except Exception:
            if target_model in ["large-v3-turbo", "turbo", "large-v3-turbo-ct2"]:
                target_model = "deepdml/faster-whisper-large-v3-turbo-ct2"
                _asr_model = WhisperModel(target_model, device=cfg.device, compute_type=compute_type)
            else:
                raise

        _asr_engine_type = "faster_whisper"
        print(f"[STT] Loaded faster-whisper CTranslate2 model ({target_model}, compute_type={compute_type})", flush=True)
        return _asr_model
    except Exception as e:
        print(f"[STT] faster-whisper load notice: {e}", flush=True)

    # 2. Fallback to OpenAI PyTorch Whisper (openai-whisper)
    try:
        import whisper
        try:
            _asr_model = whisper.load_model(cfg.model_name, device=cfg.device)
        except Exception as device_err:
            if cfg.device != "cpu":
                print(f"[STT] whisper load on {cfg.device} notice: {device_err}. Falling back to CPU...", flush=True)
                _asr_model = whisper.load_model(cfg.model_name, device="cpu")
            else:
                raise device_err
        _asr_engine_type = "openai_whisper"
        print(f"[STT] Loaded openai-whisper (PyTorch) model ({cfg.model_name})", flush=True)
        return _asr_model
    except Exception as e:
        print(f"[STT] openai-whisper load notice: {e}", flush=True)

    return None


def is_loaded() -> bool:
    return get_model() is not None


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
    This dramatically improves Whisper accuracy by removing junk input.

    Args:
        audio_float32: numpy float32 array in [-1, 1]
        sr: sample rate (must be 16000 for Silero VAD)

    Returns:
        numpy float32 array containing only speech segments
    """
    if not _load_silero_vad():
        return audio_float32  # Fallback: return unfiltered

    try:
        import torch
        get_speech_timestamps = _vad_utils[0]

        # Silero VAD requires torch tensor
        audio_tensor = torch.from_numpy(audio_float32).float()
        if audio_tensor.ndim > 1:
            audio_tensor = audio_tensor.mean(dim=0)

        # Get speech timestamps
        speech_timestamps = get_speech_timestamps(
            audio_tensor, _vad_model,
            sampling_rate=sr,
            threshold=0.4,         # Speech probability threshold
            min_speech_duration_ms=100,  # Min speech segment
            min_silence_duration_ms=200, # Min silence to split
        )

        if not speech_timestamps:
            print("[STT] VAD: No speech detected in audio", flush=True)
            return audio_float32

        # Concatenate only speech segments with 50ms padding
        pad_samples = int(0.050 * sr)  # 50ms padding
        segments = []
        for ts in speech_timestamps:
            start = max(0, ts['start'] - pad_samples)
            end = min(len(audio_float32), ts['end'] + pad_samples)
            segments.append(audio_float32[start:end])

        import numpy as np
        speech_only = np.concatenate(segments)
        ratio = len(speech_only) / max(len(audio_float32), 1)
        print(f"[STT] VAD: Extracted {len(speech_timestamps)} speech segments "
              f"({ratio:.0%} of audio)", flush=True)
        return speech_only

    except Exception as e:
        print(f"[STT] VAD filter error: {e}", flush=True)
        return audio_float32


# ── Hot-Word Boosting ─────────────────────────────────────────────────────────

# Domain vocabulary that Whisper frequently misrecognizes
_HOTWORD_PROMPT = (
    "Transcribe Hindi and English spoken together in Hinglish using Roman script. Do NOT translate into English. "
    "Examples of Hinglish sentences: Aaj ka kya plan hai, Main bilkul thik hu, Khaana kha liya kya, "
    "Kaam ho gaya bhai, Kitne baje milna hai, Kya kar rahe ho, Please send me the file, "
    "Kritix, YouTube, WhatsApp, Spotify, Chrome, Google, Instagram, Facebook."
)


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

SAFE_CORRECTIONS = {
    "your duped": "youtube", "you duped": "youtube",
    "your tube": "youtube",  "you tube": "youtube", "dupe": "youtube",
    "critics": "kritix",     "critix": "kritix",    "kritics": "kritix",
    "critick": "kritix",     "kritex": "kritix",    "kreetix": "kritix",
    "courtiers": "kritix",   "critters": "kritix",  "christian": "kritix",
    "critiques": "kritix",   "critique": "kritix",  "predicts": "kritix",
    "credits": "kritix",     "creatives": "kritix", "creedits": "kritix",
    "crittix": "kritix",    "cretix": "kritix",   "kriktix": "kritix",
    "criticks": "kritix",   "critx": "kritix",    "krdicks": "kritix",
    "kriticks": "kritix",   "kridicks": "kritix", "kutrix": "kritix",
    "krytix": "kritix",     "kratix": "kritix",   "kriotix": "kritix",
    "krityx": "kritix",     "krytic": "kritix",   "kratic": "kritix",
    "no critiques": "hello kritix", "so critics": "hello kritix",
    "hey critics": "hey kritix",    "hey critiques": "hey kritix",
    "what sap": "whatsapp",  "watts app": "whatsapp",
    "whats app": "whatsapp", "watsapp": "whatsapp", "watsup": "whatsapp",
    "crome": "chrome",       "chrom": "chrome",
    "spot if i": "spotify",  "spot if y": "spotify",
    "spoti fi": "spotify",   "spotifyy": "spotify",
    "goggle": "google",      "gogle": "google",
    "how are u": "how are you", "how r u": "how are you",
    "thank u": "thank you",  "thx": "thanks", "ty": "thank you",
}


def correct_text(text: str) -> str:
    t = re.sub(r"\s+", " ", text.lower()).strip()
    for wrong, right in SAFE_CORRECTIONS.items():
        t = re.sub(rf"\b{re.escape(wrong)}\b", right, t)
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
    try:
        from Backend.WakeWordDetection import WAKE_WORDS, _WAKE_VARIANTS
    except Exception:
        WAKE_WORDS = ["hey kritix", "hello kritix", "listen kritix"]
        _WAKE_VARIANTS = set()

    t = re.sub(r"\s+", " ", text.lower()).strip()
    if not t:
        return ""
    for ww in sorted((w.strip().lower() for w in WAKE_WORDS if w.strip()), key=len, reverse=True):
        if t == ww:
            return ""
        if t.startswith(ww + " "):
            return t[len(ww):].strip()
    tokens = t.split()
    for i, token in enumerate(tokens[:4]):
        if token in _WAKE_VARIANTS or token in {"kritix", "critix", "kritics", "kritex", "kreetix"}:
            return " ".join(tokens[i + 1:]).strip()
    return t


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

        lang_arg = None if language == "auto" else language

        if _asr_engine_type == "faster_whisper":
            # First pass: fast beam_size=1
            text, confidence = _transcribe_faster_whisper(
                model, arr, lang_arg, beam_size=1
            )

            # Confidence-based retry: if low confidence and enough audio, retry with larger beam
            if confidence < 0.65 and duration > 1.0 and len(arr) > 16000:
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
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=100),
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        initial_prompt=_HOTWORD_PROMPT,
    )

    all_segments = list(segments)
    text = " ".join(s.text.strip() for s in all_segments if s.text and s.text.strip())
    text = re.sub(r"\s+", " ", text).strip()

    # Calculate confidence from average log probability
    if all_segments:
        avg_log_prob = sum(s.avg_log_prob for s in all_segments) / len(all_segments)
        # Convert log probability to 0-1 confidence score
        confidence = min(1.0, max(0.0, 1.0 + avg_log_prob / 2.0))
    else:
        confidence = 0.0

    if info.language_probability < 0.5 and not text:
        return "", 0.0

    return text, confidence


def transcribe_with_confidence(
    audio: bytes, duration: float = 0.0, language: str = "auto"
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

        lang_arg = None if language == "auto" else language
        if _asr_engine_type == "faster_whisper":
            text, confidence = _transcribe_faster_whisper(model, arr, lang_arg, 1)
            if confidence < 0.65 and duration > 1.0 and len(arr) > 16000:
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


# alias used by WakeWord files
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

    wake_detector = None
    try:
        from Backend.WakeWordDetection import get_active_detector
        wake_detector = get_active_detector()
        if wake_detector:
            wake_detector.pause()
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
        try:
            if wake_detector:
                wake_detector.resume()
        except Exception:
            pass


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
