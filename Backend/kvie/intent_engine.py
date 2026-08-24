"""Deterministic intent rules for KVIE document editing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .document_state import DocumentState, DocumentSnapshot
from .semantic_match import SemanticMatcher


@dataclass(frozen=True)
class IntentDecision:
    action: str
    content: str = ""
    confidence: float = 1.0
    target_sentence: Optional[int] = None
    language: Optional[str] = None
    reason: str = ""
    requires_llm: bool = False


class IntentEngine:
    """Classifies safe, high-signal editing phrases without model latency."""

    _correction = re.compile(r"^(?:actually|wait|sorry|no),?\s+(?:replace|change|make it)(?:\s+with)?\s+(.+)$", re.I)
    _insert = re.compile(r"^insert\s+(.+?)\s+after\s+(?:the\s+)?(first|last|\d+)(?:st|nd|rd|th)?\s+sentence\.?$", re.I)
    _translate = re.compile(r"^(?:translate|write this)\s+(?:in|to)\s+([a-zA-Z -]+)$", re.I)
    _semantic_replace = re.compile(r"^(?:replace|change)\s+(?:the\s+)?(?:sentence\s+)?(?:about|containing)\s+(.+?)\s+(?:with|to)\s+(.+)$", re.I)

    def __init__(self, matcher: Optional[SemanticMatcher] = None):
        self.matcher = matcher or SemanticMatcher()

    def classify(self, text: str, document: DocumentState) -> IntentDecision:
        normalized = re.sub(r"\s+", " ", text.strip())
        lower = normalized.lower()
        last_sentence = len(document.sentences()) - 1 if document.sentences() else None

        if lower in {"undo", "undo that", "go back", "undo karo"}:
            return IntentDecision("undo", reason="explicit undo command")
        if lower in {"redo", "redo that", "bring it back", "redo karo"}:
            return IntentDecision("redo", reason="explicit redo command")
        if lower in {"stop", "cancel", "never mind", "nevermind", "ruko"}:
            return IntentDecision("ignore", reason="explicit cancellation")
        if lower in {"clear", "clear all", "clear text", "clear document", "delete all", "sab clear karo", "clear kardo", "sab delete karo"}:
            return IntentDecision("clear", reason="explicit clear command")

        correction = self._correction.match(normalized)
        if correction and last_sentence is not None:
            return IntentDecision("replace_sentence", correction.group(1).rstrip("."), .98, last_sentence, reason="correction phrase")

        if lower.startswith(("delete the last sentence", "delete last sentence", "pichla sentence delete karo")) and last_sentence is not None:
            return IntentDecision("delete_sentence", target_sentence=last_sentence, reason="last sentence deletion")
        if lower.startswith(("delete this sentence", "delete current sentence", "yeh sentence delete karo")) and last_sentence is not None:
            return IntentDecision("delete_sentence", target_sentence=last_sentence, reason="current sentence deletion")

        targeted_replace = self._semantic_replace.match(normalized)
        if targeted_replace:
            match = self.matcher.best_sentence(targeted_replace.group(1), document)
            if match:
                return IntentDecision("replace_sentence", targeted_replace.group(2).rstrip("."), .92, match.sentence_index, reason="semantic sentence match")

        insertion = self._insert.match(normalized)
        if insertion:
            marker = insertion.group(2).lower()
            target = 0 if marker == "first" else (last_sentence if marker == "last" else int(marker) - 1)
            if target is not None and target >= 0:
                return IntentDecision("insert_after_sentence", insertion.group(1).strip(), .96, target, reason="explicit sentence insertion")

        translation = self._translate.match(normalized)
        if translation:
            return IntentDecision("translate", language=translation.group(1).strip().lower(), reason="explicit translation request")

        if lower.startswith(("rewrite", "rephrase", "paraphrase", "change tone", "make this", "make it", "summarize", "shorten", "expand", "fix grammar", "correct mistakes", "polish", "is text ko", "isko", "formal banao", "summary bana")):
            return IntentDecision("rewrite", content=normalized, confidence=.9, target_sentence=last_sentence, reason="rewrite instruction", requires_llm=True)

        if lower.startswith(("format ", "make this a list", "turn this into", "bullet points")):
            return IntentDecision("format", content=normalized, confidence=.9, reason="formatting instruction", requires_llm=True)

        if not normalized:
            return IntentDecision("ignore", confidence=1.0, reason="empty transcript")
        return IntentDecision("append", content=normalized, confidence=.75, reason="default continuation")

    def apply(self, decision: IntentDecision, document: DocumentState) -> DocumentSnapshot:
        if decision.action == "append":
            return document.append(decision.content, {"intent": decision.action, "confidence": decision.confidence})
        if decision.action == "clear":
            return document.clear({"intent": decision.action})
        if decision.action == "replace_sentence":
            if decision.target_sentence is None:
                return document.snapshot()
            return document.replace_sentence(decision.target_sentence, decision.content, {"intent": decision.action})
        if decision.action == "delete_sentence":
            if decision.target_sentence is None:
                return document.snapshot()
            spans = document.sentence_spans()
            if decision.target_sentence >= len(spans):
                return document.snapshot()
            return document.delete(*spans[decision.target_sentence], {"intent": decision.action})
        if decision.action == "insert_after_sentence":
            if decision.target_sentence is None:
                return document.snapshot()
            spans = document.sentence_spans()
            if decision.target_sentence >= len(spans):
                return document.snapshot()
            return document.insert(" " + decision.content, spans[decision.target_sentence][1], {"intent": decision.action})
        if decision.action == "undo":
            return document.undo()
        if decision.action == "redo":
            return document.redo()
        return document.snapshot()
