"""
Voice/VoiceManager.py - Voice System Orchestrator
Ties together STT, TTS, and Wake Word Detection
"""

import os
import sys
import time
import threading
import queue
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field


# ── State Machine ──────────────────────────────────────────────────────────────

class VoiceState:
    """Voice system state machine"""
    IDLE = "idle"
    WAKE_WORD_DETECTED = "wake"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    FOLLOW_UP = "follow_up"


@dataclass
class VoiceConfig:
    """Configuration for voice system"""
    wake_words: list = field(default_factory=lambda: ["hey kritix", "hello kritix"])
    wake_word_enabled: bool = True
    command_timeout: float = 10.0
    silence_duration: float = 1.5
    echo_buffer_ms: float = 150
    follow_up_enabled: bool = True
    follow_up_timeout: float = 5.0

    @classmethod
    def from_env(cls):
        """Load from environment"""
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

        wake_words_raw = env.get("WakeWords", "hey kritix,hello kritix,listen kritix")
        wake_words = [w.strip() for w in wake_words_raw.split(",") if w.strip()]

        return cls(
            wake_words=wake_words,
            wake_word_enabled=env.get("WakeWordEnabled", "True").lower() == "true",
        )


# ── Voice Manager ──────────────────────────────────────────────────────────────

class VoiceManager:
    """Orchestrates the voice system."""

    def __init__(
        self,
        callback: Optional[Callable[[str], None]] = None,
        config: Optional[VoiceConfig] = None
    ):
        self.config = config or VoiceConfig.from_env()
        self.callback = callback

        self._state = VoiceState.IDLE
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._wake_detector = None
        self._stt_module = None
        self._tts_module = None

        self._command_queue: queue.Queue = queue.Queue()

        self._data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "Data"
        )
        os.makedirs(self._data_dir, exist_ok=True)

        print(f"[VOICE] Wake words: {self.config.wake_words}", flush=True)
        print(f"[VOICE] Echo buffer: {self.config.echo_buffer_ms}ms", flush=True)

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @state.setter
    def state(self, value: str):
        with self._lock:
            self._state = value
            self._update_status()

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Component Access ───────────────────────────────────────────────────────

    def _get_stt(self):
        if self._stt_module is None:
            try:
                from Backend.voice import STT
                self._stt_module = STT
                print("[VOICE] STT module loaded", flush=True)
            except ImportError as e:
                print(f"[VOICE] STT import error: {e}", flush=True)
        return self._stt_module

    def _get_tts(self):
        if self._tts_module is None:
            try:
                from Backend.voice import TTS
                self._tts_module = TTS
                print("[VOICE] TTS module loaded", flush=True)
            except ImportError as e:
                print(f"[VOICE] TTS import error: {e}", flush=True)
        return self._tts_module

    def _get_wake_detector(self):
        if self._wake_detector is None:
            try:
                from Backend.voice.WakeWord import WakeWordDetector
                self._wake_detector = WakeWordDetector(
                    callback=self._on_wake_word,
                )
                print("[VOICE] Wake word detector loaded", flush=True)
            except ImportError as e:
                print(f"[VOICE] WakeWord import error: {e}", flush=True)
        return self._wake_detector

    # ── Status Updates ─────────────────────────────────────────────────────────

    def _update_status(self):
        try:
            status_file = os.path.join(self._data_dir, "Status.data")
            with open(status_file, "w", encoding="utf-8") as f:
                f.write(f"Voice: {self._state}")

            mic_file = os.path.join(self._data_dir, "Mic.data")
            mic_status = "ON" if self._state in [VoiceState.LISTENING, VoiceState.FOLLOW_UP] else "OFF"
            with open(mic_file, "w", encoding="utf-8") as f:
                f.write(mic_status)
        except Exception as e:
            print(f"[VOICE] Status update error: {e}", flush=True)

    # ── Start/Stop ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return

        self._running = True
        self.state = VoiceState.IDLE

        if self.config.wake_word_enabled:
            wake_detector = self._get_wake_detector()
            if wake_detector:
                wake_detector.start()

        print("[VOICE] Voice system started", flush=True)

    def stop(self):
        self._running = False

        if self._wake_detector:
            self._wake_detector.stop()

        self.state = VoiceState.IDLE
        print("[VOICE] Voice system stopped", flush=True)

    def pause(self):
        if self._wake_detector:
            self._wake_detector.pause()
        self.state = VoiceState.IDLE

    def resume(self):
        if self._wake_detector:
            self._wake_detector.resume()
        self.state = VoiceState.IDLE

    # ── Wake Word Handler ──────────────────────────────────────────────────────

    def _on_wake_word(self, command: str = ""):
        print(f"[VOICE] Wake word detected!", flush=True)
        # Wake word detected - trigger callback to start command listening
        # Main execution will handle the actual command listening
        self.state = VoiceState.LISTENING

        if self.callback:
            try:
                self.callback(command)
            except Exception as e:
                print(f"[VOICE] Callback error: {e}", flush=True)

    # ── Command Processing ─────────────────────────────────────────────────────

    def _process_command(self, text: str):
        if not text:
            self.state = VoiceState.IDLE
            return

        print(f"[VOICE] Command: {text}", flush=True)
        self.state = VoiceState.PROCESSING

        self._command_queue.put(text)

        if self.callback:
            try:
                self.callback(text)
            except Exception as e:
                print(f"[VOICE] Callback error: {e}", flush=True)

    # ── Speaking ──────────────────────────────────────────────────────────────

    def speak(self, text: str, emotion: str = "neutral"):
        self.state = VoiceState.SPEAKING

        try:
            TTS = self._get_tts()
            if TTS is None:
                print("[VOICE] TTS not available", flush=True)
                self.state = VoiceState.IDLE
                return

            from Backend.voice.TTS import Emotion
            emotion_enum = Emotion[emotion.upper()] if emotion.upper() in [e.name for e in Emotion] else Emotion.NEUTRAL

            TTS.speak(text, emotion=emotion_enum)

        except Exception as e:
            print(f"[VOICE] Speak error: {e}", flush=True)

        finally:
            self.state = VoiceState.IDLE

    def speak_async(self, text: str, emotion: str = "neutral"):
        def _speak():
            self.speak(text, emotion)

        thread = threading.Thread(target=_speak, daemon=True)
        thread.start()

    # ── Follow-up Mode ─────────────────────────────────────────────────────────

    def enable_follow_up(self):
        if not self.config.follow_up_enabled:
            return

        print("[VOICE] Entering follow-up mode", flush=True)
        self.state = VoiceState.FOLLOW_UP

        def _timeout():
            time.sleep(self.config.follow_up_timeout)
            if self.state == VoiceState.FOLLOW_UP:
                print("[VOICE] Follow-up timeout", flush=True)
                self.state = VoiceState.IDLE

        threading.Thread(target=_timeout, daemon=True).start()

    def listen_follow_up(self) -> str:
        try:
            STT = self._get_stt()
            if STT is None:
                return ""

            text = STT.listen(
                timeout=self.config.follow_up_timeout,
                silence_duration=0.8
            )

            if text:
                print(f"[VOICE] Follow-up: {text}", flush=True)

            return text

        except Exception as e:
            print(f"[VOICE] Follow-up error: {e}", flush=True)
            return ""

    # ── Queue Access ───────────────────────────────────────────────────────────

    def get_command(self, timeout: float = 0.1) -> Optional[str]:
        try:
            return self._command_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_commands(self):
        while not self._command_queue.empty():
            try:
                self._command_queue.get_nowait()
            except queue.Empty:
                break

    # ── Status ───────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        stt_status = self._get_stt()
        tts_status = self._get_tts()

        return {
            "running": self._running,
            "state": self.state,
            "wake_enabled": self.config.wake_word_enabled,
            "stt_ready": stt_status is not None,
            "tts_ready": tts_status is not None,
            "commands_pending": self._command_queue.qsize(),
        }


# ── Standalone Test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("Voice Manager Test", flush=True)
    print("=" * 60, flush=True)

    def on_command(command: str):
        print(f"\n[CMD] Got command: {command}", flush=True)
        import random
        responses = [
            "I heard you!",
            "Okay, I'm working on that.",
            "Sure thing!",
            "Got it!",
        ]
        vm.speak(random.choice(responses))

    config = VoiceConfig.from_env()
    vm = VoiceManager(callback=on_command, config=config)

    print("\n[START] Starting voice system...", flush=True)
    vm.start()

    print("\n[READY] Say wake word or press Ctrl+C to stop", flush=True)

    try:
        while vm.is_running:
            cmd = vm.get_command()
            if cmd:
                print(f"[MAIN] Processing: {cmd}", flush=True)

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[EXIT]", flush=True)
        vm.stop()