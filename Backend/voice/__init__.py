"""
Voice Module - Modern Voice System for Kritix AI

Components:
- STT: Whisper-based speech-to-text
- TTS: Chatterbox multilingual text-to-speech
- WakeWord: Simple energy-based wake word detection
- VoiceManager: Orchestrates all voice components
- VoiceLearner: Learns from corrections to improve accuracy
"""

from .STT import (
    transcribe,
    transcribe_blocking,
    transcribe_pcm,
    transcribe_with_confidence,
    record_audio,
    listen,
    SpeechRecognition,
    correct_text,
    query_modifier,
    detect_language,
    get_model,
    is_loaded,
    is_loaded as stt_loaded,
    STTConfig,
)
# Voice learner functions (placeholder)
def record_correction(misheard: str, corrected: str) -> bool:
    return False

def get_learner_stats() -> dict:
    return {}
from .TTS import (
    speak,
    speak_async,
    speak_romantic,
    is_speaking,
    TTSConfig,
    Emotion,
)
from .WakeWord import (
    WakeWordDetector,
    acquire_stream_lock,
    release_stream_lock,
    get_active_detector,
)
from .VoiceManager import (
    VoiceManager,
    VoiceState,
    VoiceConfig,
)
from .VoiceLearner import VoiceLearner

__all__ = [
    # STT
    "transcribe",
    "transcribe_blocking",
    "transcribe_pcm",
    "transcribe_with_confidence",
    "record_audio",
    "listen",
    "SpeechRecognition",
    "correct_text",
    "query_modifier",
    "detect_language",
    "record_correction",
    "get_learner_stats",
    "get_model",
    "stt_loaded",
    "STTConfig",
    # TTS
    "speak",
    "speak_async",
    "speak_romantic",
    "is_speaking",
    "TTSConfig",
    "Emotion",
    # Wake Word
    "WakeWordDetector",
    "acquire_stream_lock",
    "release_stream_lock",
    "get_active_detector",
    # Voice Manager
    "VoiceManager",
    "VoiceState",
    "VoiceConfig",
    # Voice Learner
    "VoiceLearner",
]
