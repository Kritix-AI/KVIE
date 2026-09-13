"""
Voice/TTS.py — TTS facade for the voice package.

Priority chain:
  1. ChatterboxInference  (CUDA, high-quality multilingual)
  2. StreamingTTSEngine   (Edge TTS, low-latency cloud fallback)

Both engines are optional — if neither is available the speak() calls
return False and print a notice rather than crashing.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class TTSConfig:
    """Configuration for TTS module."""
    voice: str = "en-IN-NeerjaNeural"
    voice_hindi: str = "hi-IN-SwaraNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"

    @classmethod
    def from_env(cls) -> "TTSConfig":
        try:
            from dotenv import dotenv_values
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            env = dotenv_values(os.path.join(_root, ".env"))
            return cls(
                voice=env.get("AssistantVoice") or "en-IN-NeerjaNeural",
                voice_hindi=env.get("AssistantVoiceHindi") or "hi-IN-SwaraNeural",
            )
        except Exception:
            return cls()


class Emotion(Enum):
    """Emotion types for voice modulation."""
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


# ── Global speaking state ───────────────────────────────────────────────────────

@dataclass
class _TTSState:
    is_speaking: bool = False
    mute_until: float = 0.0


_state_lock = threading.Lock()
_state = _TTSState()


def is_speaking() -> bool:
    """Return True if TTS is currently producing audio."""
    with _state_lock:
        return _state.is_speaking or time.time() < _state.mute_until


def _set_speaking(speaking: bool) -> None:
    with _state_lock:
        _state.is_speaking = speaking
        if not speaking:
            _state.mute_until = time.time() + 0.15


# ── Engine helpers ──────────────────────────────────────────────────────────────

def _try_chatterbox(text: str, emotion: str) -> bool:
    """Attempt synthesis via ChatterboxInference (CUDA only)."""
    try:
        from Backend.voice.chatterbox_inference import get_chatterbox_engine
        engine = get_chatterbox_engine()
        if engine is None:
            return False

        # Map Emotion enum string to language_id
        lang_id = "hi" if emotion in {"romantic", "loving", "sweet"} else "en"
        wav_path = engine.synthesize(text, emotion=emotion, language_id=lang_id)
        if not wav_path:
            return False

        # Play the generated WAV
        try:
            import sounddevice as sd
            import soundfile as sf
            data, sr = sf.read(wav_path, dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)
            sd.play(data, sr, blocking=True)
        except Exception:
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(wav_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.quit()
            except Exception as e:
                print(f"[TTS] Playback error: {e}", flush=True)
                return False
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass
        return True

    except Exception as e:
        print(f"[TTS] Chatterbox notice: {e}", flush=True)
        return False


def _try_edge_tts(text: str, emotion: str) -> bool:
    """Attempt synthesis via StreamingTTSEngine (Edge TTS)."""
    try:
        from Backend.voice.StreamingTTS import get_streaming_engine
        engine = get_streaming_engine()
        config = TTSConfig.from_env()
        return engine.speak(text, voice=config.voice, emotion=emotion)
    except Exception as e:
        print(f"[TTS] Edge TTS notice: {e}", flush=True)
        return False


# ── Public API ──────────────────────────────────────────────────────────────────

async def speak_async(text: str, emotion: Emotion = Emotion.NEUTRAL) -> bool:
    """Async speak — tries Chatterbox then Edge TTS."""
    if not text or not text.strip():
        return False
    emotion_str = emotion.value if isinstance(emotion, Emotion) else str(emotion)
    _set_speaking(True)
    try:
        result = await asyncio.to_thread(_try_chatterbox, text, emotion_str)
        if not result:
            result = await asyncio.to_thread(_try_edge_tts, text, emotion_str)
        return result
    finally:
        _set_speaking(False)


def speak(text: str, emotion: Emotion = Emotion.NEUTRAL) -> bool:
    """Synchronous speak — tries Chatterbox then Edge TTS."""
    if not text or not text.strip():
        return False
    emotion_str = emotion.value if isinstance(emotion, Emotion) else str(emotion)
    _set_speaking(True)
    try:
        result = _try_chatterbox(text, emotion_str)
        if not result:
            result = _try_edge_tts(text, emotion_str)
        return result
    finally:
        _set_speaking(False)


def speak_romantic(text: str) -> bool:
    """Speak with romantic emotion."""
    return speak(text, emotion=Emotion.ROMANTIC)


async def speak_romantic_async(text: str) -> bool:
    """Async speak with romantic emotion."""
    return await speak_async(text, emotion=Emotion.ROMANTIC)


def get_status() -> dict:
    """Return current TTS status."""
    return {"speaking": _state.is_speaking, "ready": True}


def preview_voice(voice: str, text: str = "Hello! This is a test of my voice.") -> bool:
    """Preview a voice (voice param reserved for future routing)."""
    return speak(text)


def list_available_voices() -> list:
    """Return the languages supported by the active TTS engine."""
    return [
        {"ShortName": "en", "Locale": "en", "DisplayName": "English"},
        {"ShortName": "hi", "Locale": "hi", "DisplayName": "Hindi / Hinglish"},
    ]


# ── Standalone test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("Voice TTS Facade Test", flush=True)
    print("=" * 60, flush=True)

    test_cases = [
        ("English neutral", "Hello! How are you today?", Emotion.NEUTRAL),
        ("Excited",         "Wow! That's amazing news!", Emotion.EXCITED),
        ("Thinking",        "Let me think about that...", Emotion.THINKING),
        ("Friendly",        "Sure, I can help you with that!", Emotion.FRIENDLY),
    ]

    for name, text, emotion in test_cases:
        print(f"\n[{name}] {text}", flush=True)
        ok = speak(text, emotion=emotion)
        print(f"  -> {'OK' if ok else 'FAILED'}", flush=True)

    print("\n[DONE]", flush=True)
