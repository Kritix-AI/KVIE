"""
Voice/VoiceLearner.py - Learning System for Voice Recognition
Learns from user corrections to improve STT and Wake Word accuracy

Usage:
    from Backend.voice.VoiceLearner import VoiceLearner

    learner = VoiceLearner()
    learner.correct("hey kritix", "hey kritix")  # correct transcription
    learner.learn_wake_word("hey kritix")  # improve wake word detection
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, asdict


# ── Data Paths ──────────────────────────────────────────────────────────────

def _get_data_dir():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


# ── Phonetic Pattern ─────────────────────────────────────────────────────────

@dataclass
class PhoneticPattern:
    """A phonetic pattern that maps misrecognized → corrected"""
    misheard: str           # What was transcribed
    corrected: str           # What user meant
    count: int = 1          # Times seen
    last_seen: float = 0.0  # Timestamp


# ── Wake Word Stats ─────────────────────────────────────────────────────────

@dataclass
class WakeWordStats:
    """Statistics for a wake word"""
    word: str
    attempts: int = 0        # Times user tried to trigger
    successes: int = 0      # Times successfully detected
    failures: int = 0       # Times failed to detect
    avg_confidence: float = 0.0
    # Audio characteristics that trigger detection
    avg_energy: float = 0.0
    avg_duration: float = 0.0


# ── Voice Learner ───────────────────────────────────────────────────────────

class VoiceLearner:
    """
    Learns from user interactions to improve voice recognition.

    Tracks:
    - Phonetic corrections (misheard → corrected)
    - Wake word detection success/failure
    - Audio characteristics
    - User preferences
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        """Initialize the learner"""
        self._data_dir = _get_data_dir()

        # Phonetic patterns: misheard → PhoneticPattern
        self._phonetic_patterns: Dict[str, PhoneticPattern] = {}

        # Wake word stats
        self._wake_word_stats: Dict[str, WakeWordStats] = {}

        # User corrections log
        self._corrections_log: List[dict] = []

        # Audio samples for training (encrypted references)
        self._audio_samples: List[dict] = []

        # Settings
        self._settings = {
            "min_pattern_count": 2,      # Min corrections before applying pattern
            "confidence_threshold": 0.7,  # Min confidence to apply correction
            "learning_enabled": True,
            "auto_apply_corrections": True,
        }

        # Load saved data
        self._load()

        print("[LEARNER] VoiceLearner initialized", flush=True)

    # ── Phonetic Corrections ─────────────────────────────────────────────────

    def correct(self, misheard: str, corrected: str) -> bool:
        """
        Register a correction from user.
        Call this when user confirms STT got it wrong.

        Args:
            misheard: What the system transcribed
            corrected: What user actually said

        Returns:
            True if pattern was new/updated
        """
        if not self._settings["learning_enabled"]:
            return False

        if not misheard or not corrected:
            return False

        if misheard.lower() == corrected.lower():
            return False  # No correction needed

        misheard_lower = misheard.lower().strip()
        corrected_lower = corrected.lower().strip()

        # Update or create pattern
        if misheard_lower in self._phonetic_patterns:
            pattern = self._phonetic_patterns[misheard_lower]
            if pattern.corrected != corrected_lower:
                pattern.corrected = corrected_lower
                pattern.count += 1
                pattern.last_seen = time.time()
        else:
            self._phonetic_patterns[misheard_lower] = PhoneticPattern(
                misheard=misheard_lower,
                corrected=corrected_lower,
                count=1,
                last_seen=time.time()
            )

        # Log correction
        self._corrections_log.append({
            "misheard": misheard_lower,
            "corrected": corrected_lower,
            "timestamp": time.time(),
            "type": "phonetic"
        })

        # Save
        self._save()

        print(f"[LEARNER] Registered correction: '{misheard}' → '{corrected}'", flush=True)
        return True

    def apply_corrections(self, text: str) -> str:
        """
        Apply learned corrections to transcribed text.

        Args:
            text: Raw transcribed text

        Returns:
            Corrected text
        """
        if not self._settings["auto_apply_corrections"]:
            return text

        text_lower = text.lower().strip()
        result = text_lower

        for misheard, pattern in self._phonetic_patterns.items():
            if pattern.count >= self._settings["min_pattern_count"]:
                import re
                pattern_str = r'\b' + re.escape(misheard) + r'\b'
                result = re.sub(pattern_str, pattern.corrected, result)

        # Capitalize proper nouns
        proper_nouns = ["kritix", "youtube", "whatsapp", "spotify", "chrome"]
        for word in proper_nouns:
            result = result.replace(word, word.title())

        return result if result != text_lower else text

    def get_corrections(self) -> Dict[str, str]:
        """Get all phonetic corrections"""
        return {
            misheard: pattern.corrected
            for misheard, pattern in self._phonetic_patterns.items()
            if pattern.count >= self._settings["min_pattern_count"]
        }

    # ── Wake Word Learning ───────────────────────────────────────────────────

    def learn_wake_attempt(self, wake_word: str, energy: float = 0, duration: float = 0):
        """Record wake word detection attempt"""
        if wake_word not in self._wake_word_stats:
            self._wake_word_stats[wake_word] = WakeWordStats(word=wake_word)

        stats = self._wake_word_stats[wake_word]
        stats.attempts += 1
        stats.avg_energy = (stats.avg_energy * 0.9 + energy * 0.1)
        stats.avg_duration = (stats.avg_duration * 0.9 + duration * 0.1)

        self._save()

    def learn_wake_success(self, wake_word: str, confidence: float = 1.0):
        """Record successful wake word detection"""
        if wake_word not in self._wake_word_stats:
            self._wake_word_stats[wake_word] = WakeWordStats(word=wake_word)

        stats = self._wake_word_stats[wake_word]
        stats.attempts += 1
        stats.successes += 1
        stats.avg_confidence = (stats.avg_confidence * 0.9 + confidence * 0.1)

        self._save()

        success_rate = stats.successes / max(1, stats.attempts) * 100
        print(f"[LEARNER] Wake '{wake_word}': {stats.successes}/{stats.attempts} ({success_rate:.0f}%)", flush=True)

    def learn_wake_failure(self, wake_word: str):
        """Record failed wake word detection"""
        if wake_word not in self._wake_word_stats:
            self._wake_word_stats[wake_word] = WakeWordStats(word=wake_word)

        stats = self._wake_word_stats[wake_word]
        stats.failures += 1

        self._save()

    def get_wake_word_sensitivity(self, wake_word: str) -> Tuple[float, float]:
        """
        Get adjusted energy/duration thresholds based on learning.

        Returns:
            (energy_adjustment, duration_adjustment) - multipliers for thresholds
        """
        if wake_word not in self._wake_word_stats:
            return (1.0, 1.0)

        stats = self._wake_word_stats[wake_word]

        if stats.attempts < 5:
            return (1.0, 1.0)

        success_rate = stats.successes / stats.attempts

        # If low success rate, lower thresholds (make more sensitive)
        if success_rate < 0.5:
            return (0.7, 0.8)  # 30% more sensitive
        elif success_rate < 0.8:
            return (0.85, 0.9)  # Slightly more sensitive

        return (1.0, 1.0)

    # ── Audio Learning ───────────────────────────────────────────────────────

    def learn_audio_characteristics(self, audio_bytes: bytes, wake_word: str, detected: bool):
        """
        Learn audio characteristics of user's voice for wake word.

        Args:
            audio_bytes: Raw audio
            wake_word: Which wake word was attempted
            detected: Whether it was detected
        """
        import numpy as np

        try:
            samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            energy = float(np.sqrt(np.mean(samples ** 2)))
            duration = len(audio_bytes) / 32000.0  # Approx sample rate

            if detected:
                self.learn_wake_success(wake_word, confidence=0.8)
            else:
                # User said wake word but it wasn't detected
                self.learn_wake_failure(wake_word)

        except Exception as e:
            print(f"[LEARNER] Audio analysis error: {e}", flush=True)

    # ── User Corrections Interface ───────────────────────────────────────────

    def record_correction(self, transcribed: str, actual: str, context: str = ""):
        """
        Record a user correction with context.

        Args:
            transcribed: What system transcribed
            actual: What user actually said
            context: Optional context (e.g., "after saying 'hey kritix'")
        """
        self.correct(transcribed, actual)

        self._corrections_log.append({
            "misheard": transcribed.lower(),
            "corrected": actual.lower(),
            "context": context,
            "timestamp": time.time(),
            "type": "user_correction"
        })

        self._save()

    def get_correction_suggestions(self, text: str) -> List[Tuple[str, str]]:
        """
        Get suggested corrections for text.

        Returns:
            List of (original, corrected) tuples
        """
        suggestions = []
        text_lower = text.lower()

        for misheard, pattern in self._phonetic_patterns.items():
            if pattern.count >= self._settings["min_pattern_count"]:
                if misheard in text_lower:
                    suggestions.append((misheard, pattern.corrected))

        return suggestions

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        """Load saved data"""
        try:
            # Phonetic patterns
            patterns_file = os.path.join(self._data_dir, "VoiceLearner_patterns.json")
            if os.path.exists(patterns_file):
                with open(patterns_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for misheard, pdata in data.items():
                        self._phonetic_patterns[misheard] = PhoneticPattern(**pdata)

            # Wake word stats
            stats_file = os.path.join(self._data_dir, "VoiceLearner_wake_stats.json")
            if os.path.exists(stats_file):
                with open(stats_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for word, sdata in data.items():
                        self._wake_word_stats[word] = WakeWordStats(**sdata)

            # Settings
            settings_file = os.path.join(self._data_dir, "VoiceLearner_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    saved_settings = json.load(f)
                    self._settings.update(saved_settings)

        except Exception as e:
            print(f"[LEARNER] Load error: {e}", flush=True)

    def _save(self):
        """Save data"""
        try:
            # Phonetic patterns
            patterns_file = os.path.join(self._data_dir, "VoiceLearner_patterns.json")
            data = {
                misheard: asdict(pattern)
                for misheard, pattern in self._phonetic_patterns.items()
            }
            with open(patterns_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            # Wake word stats
            stats_file = os.path.join(self._data_dir, "VoiceLearner_wake_stats.json")
            data = {
                word: asdict(stats)
                for word, stats in self._wake_word_stats.items()
            }
            with open(stats_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            # Settings
            settings_file = os.path.join(self._data_dir, "VoiceLearner_settings.json")
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)

        except Exception as e:
            print(f"[LEARNER] Save error: {e}", flush=True)

    # ── Reset/Clear ──────────────────────────────────────────────────────────

    def reset(self, what: str = "all"):
        """
        Reset learned data.

        Args:
            what: "all", "patterns", "wake_words", "corrections"
        """
        if what in ["all", "patterns"]:
            self._phonetic_patterns = {}

        if what in ["all", "wake_words"]:
            self._wake_word_stats = {}

        if what in ["all", "corrections"]:
            self._corrections_log = []

        self._save()
        print(f"[LEARNER] Reset {what}", flush=True)

    def get_stats(self) -> dict:
        """Get learner statistics"""
        return {
            "patterns_learned": len(self._phonetic_patterns),
            "patterns_active": sum(1 for p in self._phonetic_patterns.values()
                                  if p.count >= self._settings["min_pattern_count"]),
            "wake_words_tracked": len(self._wake_word_stats),
            "corrections_logged": len(self._corrections_log),
            "learning_enabled": self._settings["learning_enabled"],
        }


# ── Standalone Test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("VoiceLearner Test", flush=True)
    print("=" * 60, flush=True)

    learner = VoiceLearner()

    # Test phonetic corrections
    print("\n[TEST] Adding phonetic corrections...", flush=True)

    learner.correct("hey kritix", "hey kritix")  # Should be ignored (same)
    learner.correct("courtiers", "kritix")
    learner.correct("critters", "kritix")
    learner.correct("you've duped", "youtube")
    learner.correct("wats app", "whatsapp")

    # Apply corrections
    test_texts = [
        "courtiers open chrome",
        "you've duped search python",
        "hello kritix play music",
    ]

    print("\n[TEST] Applying corrections:", flush=True)
    for text in test_texts:
        corrected = learner.apply_corrections(text)
        print(f"  '{text}' → '{corrected}'", flush=True)

    # Wake word learning
    print("\n[TEST] Wake word statistics:", flush=True)
    learner.learn_wake_attempt("hey kritix", energy=5000, duration=0.8)
    learner.learn_wake_success("hey kritix", confidence=0.9)
    learner.learn_wake_success("hey kritix", confidence=0.85)
    learner.learn_wake_failure("hey kritix")

    sensitivity = learner.get_wake_word_sensitivity("hey kritix")
    print(f"  Sensitivity adjustment: {sensitivity}", flush=True)

    # Stats
    print(f"\n[STATS] {learner.get_stats()}", flush=True)