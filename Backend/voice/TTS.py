"""
Voice/TTS.py — Thin wrapper delegating to Backend.TextToSpeech

The authoritative TTS implementation is Backend/TextToSpeech.py, which includes:
- Full romantic/girlfriend mode
- 9 emotion types with prosody
- Hinglish language support
- Human-like text transformations (conversational starters, fillers, pet names)
- Long-text intelligent splitting

This wrapper provides a clean async API for the voice/ package.
New code: from Backend.voice import speak, speak_async
Legacy code: from Backend.TextToSpeech import TTS, TextToSpeech
"""

import os
import sys
import asyncio
import threading
from typing import Optional
from dataclasses import dataclass
from enum import Enum


# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class TTSConfig:
    """Configuration for TTS module"""
    voice: str = "en-IN-NeerjaNeural"
    voice_hindi: str = "hi-IN-SwaraNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"

    @classmethod
    def from_env(cls):
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
        return cls(
            voice=env.get("AssistantVoice") or "en-IN-NeerjaNeural",
            voice_hindi=env.get("AssistantVoiceHindi") or "hi-IN-SwaraNeural",
        )


class Emotion(Enum):
    """Emotion types for voice modulation"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    EXCITED = "excited"
    CALM = "calm"
    FRIENDLY = "friendly"
    THINKING = "thinking"
    ROMANTIC = "romantic"
    EMPATHETIC = "empathetic"
    URGENT = "urgent"


# ── Global State ────────────────────────────────────────────────────────────────

@dataclass
class TTSState:
    is_speaking: bool = False
    mute_until: float = 0.0

_state_lock = threading.Lock()
_state = TTSState()


def is_speaking() -> bool:
    """Check if TTS is currently speaking"""
    import time
    with _state_lock:
        if _state.is_speaking:
            return True
        if time.time() < _state.mute_until:
            return True
        return False


def _set_speaking(speaking: bool):
    with _state_lock:
        _state.is_speaking = speaking
        if not speaking:
            import time
            _state.mute_until = time.time() + 0.15


# ── Core Speak ─────────────────────────────────────────────────────────────────

async def _speak_async_impl(text: str, emotion: Optional[Emotion] = None) -> bool:
    """
    Internal async implementation — delegates to Backend.TextToSpeech
    """
    if not text:
        return False

    # Map Emotion enum to legacy string
    emotion_map = {
        Emotion.NEUTRAL: "neutral",
        Emotion.HAPPY: "happy",
        Emotion.SAD: "sad",
        Emotion.EXCITED: "excited",
        Emotion.CALM: "calm",
        Emotion.FRIENDLY: "friendly",
        Emotion.THINKING: "thinking",
        Emotion.ROMANTIC: "romantic",
        Emotion.EMPATHETIC: "empathetic",
        Emotion.URGENT: "urgent",
    }
    emotion_str = emotion_map.get(emotion, "neutral") if emotion else "neutral"

    try:
        # Ensure project root is on sys.path when running as __main__
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from Backend.TextToSpeech import TTS as LegacyTTS
    except ImportError:
        print("[TTS] Backend.TextToSpeech not available", flush=True)
        return False

    _set_speaking(True)
    try:
        result = LegacyTTS(text, emotion=emotion_str)
        return bool(result)
    except Exception as e:
        print(f"[TTS] Error: {e}", flush=True)
        return False
    finally:
        _set_speaking(False)


async def speak_async(text: str, emotion: Emotion = Emotion.NEUTRAL) -> bool:
    """Async speak — delegates to Backend.TextToSpeech"""
    return await _speak_async_impl(text, emotion)


def speak(text: str, emotion: Emotion = Emotion.NEUTRAL) -> bool:
    """Synchronous speak — delegates to Backend.TextToSpeech"""
    try:
        loop = asyncio.get_running_loop()
        # Already inside a running loop — run in thread to avoid conflict
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, speak_async(text, emotion))
            return future.result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run
        return asyncio.run(speak_async(text, emotion))


def speak_romantic(text: str) -> bool:
    """Speak with romantic emotion"""
    return speak(text, emotion=Emotion.ROMANTIC)


async def speak_romantic_async(text: str) -> bool:
    """Async speak with romantic emotion"""
    return await speak_async(text, emotion=Emotion.ROMANTIC)


def get_status() -> dict:
    """Get TTS status"""
    return {"speaking": _state.is_speaking, "ready": True}


def preview_voice(voice: str, text: str = "Hello! This is a test of my voice.") -> bool:
    """Preview a specific voice"""
    try:
        return speak(text)
    except Exception as e:
        print(f"[TTS] Preview error: {e}", flush=True)
        return False


def list_available_voices() -> list:
    """Return the languages supported by the Chatterbox multilingual model."""
    return [
        {"ShortName": "en", "Locale": "en", "DisplayName": "English"},
        {"ShortName": "hi", "Locale": "hi", "DisplayName": "Hindi / Hinglish"},
    ]


# ── Standalone Test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("Voice TTS Wrapper Test (delegates to TextToSpeech.py)", flush=True)
    print("=" * 60, flush=True)

    test_texts = [
        ("English neutral", "Hello! How are you today?", Emotion.NEUTRAL),
        ("Excited", "Wow! That's amazing news!", Emotion.EXCITED),
        ("Thinking", "Let me think about that for a moment...", Emotion.THINKING),
        ("Friendly", "Sure, I can help you with that!", Emotion.FRIENDLY),
    ]

    config = TTSConfig.from_env()
    print(f"\n[Config] Voice: {config.voice}", flush=True)

    for name, text, emotion in test_texts:
        print(f"\n[{name}] {text}", flush=True)
        speak(text, emotion=emotion)

    print("\n[DONE]", flush=True)
