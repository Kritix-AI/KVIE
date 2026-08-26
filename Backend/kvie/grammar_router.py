"""
KVIE Multi-Tier Grammar Router Pipeline (Python Backend)

Architecture:
          │ Grammar Router │
          └───────┬────────┘
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
    TOKEN       SENTENCE   PARAGRAPH
    ENGINE       ENGINE      ENGINE
       │          │          │
       ▼          ▼          ▼
   Spelling    Grammar     Context
   Typo        Structure   Coherence
   Casing      Tense       Flow
       │          │          │
       └──────────┼──────────┘
                  ▼
             FINAL EDITOR
                  │
                  ▼
           Corrected Text
"""

import re
from typing import Dict, List, Tuple


class TokenEngine:
    TYPO_MAP: Dict[str, str] = {
        "teh": "the",
        "recieve": "receive",
        "seperate": "separate",
        "definately": "definitely",
        "occured": "occurred",
        "untill": "until",
        "truely": "truly",
        "whcih": "which",
        "wierd": "weird",
        "accomodate": "accommodate",
        "tommorow": "tomorrow",
        "neccessary": "necessary",
        "goverment": "government",
        "arguement": "argument",
        "enviroment": "environment",
        "beleive": "believe",
        "calender": "calendar",
        "critics": "Kritix",
        "critic": "Kritix",
        "critcs": "Kritix",
        "kritics": "Kritix",
        "kritik": "Kritix",
        "kritiks": "Kritix",
        "kritic": "Kritix",
        "critis": "Kritix",
        "kritcs": "Kritix",
        "kritix": "Kritix",
        "kvie": "KVIE",
    }

    HOMOPHONE_RULES: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"\b(their)\s+(going|coming|leaving|working|doing|running|trying|making|feeling|happy|ready|sure|online)\b", re.IGNORECASE), r"they're \2"),
        (re.compile(r"\b(they're|there)\s+(house|car|office|team|code|project|family|time|idea|work|opinion)\b", re.IGNORECASE), r"their \2"),
        (re.compile(r"\b(their)\s+(is|are|was|were|will|can|could|should|must|has|have)\b", re.IGNORECASE), r"there \2"),
        (re.compile(r"\b(your)\s+(welcome|right|wrong|going|coming|doing|making|smart|invited|ready|sure)\b", re.IGNORECASE), r"you're \2"),
        (re.compile(r"\b(you're)\s+(house|car|phone|name|email|code|message|work|turn|time)\b", re.IGNORECASE), r"your \2"),
        (re.compile(r"\b(its)\s+(a|an|the|my|your|his|her|our|their|going|been|working|ready|done|cool|good|bad|fine)\b", re.IGNORECASE), r"it's \2"),
        (re.compile(r"\b(to)\s+(much|many|late|fast|slow|bad|good|expensive|hard|easy)\b", re.IGNORECASE), r"too \2"),
        (re.compile(r"\b(more|less|better|worse|greater|smaller|faster|slower|earlier|later|higher|lower)\s+(then)\b", re.IGNORECASE), r"\1 than"),
        (re.compile(r"\b(will|can|could|should|would|might|to)\s+(effect)\b", re.IGNORECASE), r"\1 affect"),
        (re.compile(r"\b(the|a|an|direct|negative|positive)\s+(affect)\b", re.IGNORECASE), r"\1 effect"),
        (re.compile(r"\b(to|will|might|don't)\s+(loose)\b", re.IGNORECASE), r"\1 lose"),
    ]

    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text

        # 1. Squash exaggerated character repetitions
        result = re.sub(r"([a-zA-Z])\1{2,}", r"\1", result)

        # 2. Token dictionary lookup
        def typo_replace(match):
            word = match.group(0)
            lower = word.lower()
            replacement = cls.TYPO_MAP.get(lower)
            if replacement:
                if word.istitle():
                    return replacement.capitalize()
                elif word.isupper():
                    return replacement.upper()
                return replacement
            return word

        result = re.sub(r"\b[a-zA-Z]+\b", typo_replace, result)

        # 3. Homophones & Confusions
        for pattern, repl in cls.HOMOPHONE_RULES:
            result = pattern.sub(repl, result)

        # 4. Standalone pronoun capitalization
        result = re.sub(r"\bi\b", "I", result)
        result = re.sub(r"(?i)\bi'm\b", "I'm", result)
        result = re.sub(r"(?i)\bi've\b", "I've", result)
        result = re.sub(r"(?i)\bi'll\b", "I'll", result)
        result = re.sub(r"(?i)\bi'd\b", "I'd", result)

        return result


class SentenceEngine:
    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text

        # Articles
        result = re.sub(r"(?i)\b(a)\s+([aeiou][a-z]+)\b", r"an \2", result)
        result = re.sub(r"(?i)\b(an)\s+([bcdfghjklmnpqrstvwxyz][a-z]+)\b", r"a \2", result)

        # Prepositions
        result = re.sub(r"(?i)\binterested\s+on\b", "interested in", result)
        result = re.sub(r"(?i)\bcongratulations\s+for\b", "congratulations on", result)
        result = re.sub(r"(?i)\bdiscuss\s+about\b", "discuss", result)
        result = re.sub(r"(?i)\bexplain\s+about\b", "explain", result)
        result = re.sub(r"(?i)\bmarried\s+with\b", "married to", result)
        result = re.sub(r"(?i)\bdepend\s+of\b", "depend on", result)

        # Capitalize sentence boundaries
        sentences = re.split(r"(?<=[.!?\n])\s+", result)
        capitalized = []
        for s in sentences:
            s_clean = s.strip()
            if s_clean:
                capitalized.append(s_clean[0].upper() + s_clean[1:])
        return " ".join(capitalized)


class ParagraphEngine:
    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text
        # Remove consecutive duplicate words
        result = re.sub(r"(?i)\b(\w+)\s+\1\b", r"\1", result)
        # Remove hesitation fragments
        result = re.sub(r"(?i)(\b\w+\b)\s+(\.\.\.|—|-)\s+(actually|wait|i mean|no)\s+", "", result)
        return result


class FinalEditor:
    @classmethod
    def process(cls, text: str) -> str:
        if not text or not text.strip():
            return ""

        result = text
        # Normalize whitespace around punctuation
        result = re.sub(r"\s+([,.:;?!])", r"\1", result)
        result = re.sub(r"([,.:;?!])([a-zA-Z])", r"\1 \2", result)
        result = re.sub(r"\s+", " ", result).strip()

        words = result.split(" ")
        if len(words) >= 3 and not re.search(r"[.!?]$", result):
            result = f"{result}."

        return result


class GrammarRouter:
    @classmethod
    def route(cls, text: str, enabled: bool = True) -> str:
        if not enabled or not text or not text.strip():
            return text.strip() if text else ""

        step1 = TokenEngine.process(text)
        step2 = SentenceEngine.process(step1)
        step3 = ParagraphEngine.process(step2)
        step4 = FinalEditor.process(step3)
        return step4
