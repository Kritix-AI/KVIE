"""Sentence matching for KVIE references such as 'that sentence'."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Optional

from .document_state import DocumentState


@dataclass(frozen=True)
class SentenceMatch:
    sentence_index: int
    sentence: str
    score: float
    method: str


EmbeddingProvider = Callable[[str, str], float]


class SemanticMatcher:
    def __init__(self, embedding_provider: Optional[EmbeddingProvider] = None):
        self.embedding_provider = embedding_provider

    def best_sentence(self, query: str, document: DocumentState, minimum_score: float = 0.2) -> Optional[SentenceMatch]:
        candidates = document.sentences()
        if not candidates:
            return None
        scored = [self._score(query, sentence, index) for index, sentence in enumerate(candidates)]
        best = max(scored, key=lambda item: item.score)
        return best if best.score >= minimum_score else None

    def _score(self, query: str, sentence: str, index: int) -> SentenceMatch:
        lexical = self._lexical_score(query, sentence)
        if self.embedding_provider:
            try:
                embedding = max(0.0, min(1.0, float(self.embedding_provider(query, sentence))))
                return SentenceMatch(index, sentence, (lexical * .35) + (embedding * .65), "embedding+lexical")
            except Exception:
                pass
        return SentenceMatch(index, sentence, lexical, "lexical")

    @staticmethod
    def _lexical_score(left: str, right: str) -> float:
        normalize = lambda value: set(re.findall(r"[a-zA-Z0-9']+", value.lower()))
        left_words, right_words = normalize(left), normalize(right)
        overlap = len(left_words & right_words) / max(1, len(left_words | right_words))
        sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
        return (overlap * .7) + (sequence * .3)
