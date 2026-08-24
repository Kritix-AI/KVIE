"""Optional local-LLM intent refinement for KVIE.

Rules handle high-signal commands first. This module only asks a local model
for the decisions that genuinely need language understanding and validates the
response before it can mutate a document.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Callable, Optional

from .document_state import DocumentState
from .intent_engine import IntentDecision, IntentEngine

ALLOWED_ACTIONS = {"append", "replace_sentence", "delete_sentence", "insert_after_sentence", "undo", "redo", "clear", "translate", "rewrite", "format", "ignore"}


class OllamaIntentClassifier:
    def __init__(self, client=None, model: Optional[str] = None):
        if client is None:
            from Backend.voice.OllamaClient import get_ollama_client
            client = get_ollama_client()
        self.client = client
        self.model = model

    def __call__(self, transcript: str, document: DocumentState) -> Optional[dict]:
        prompt = json.dumps({"transcript": transcript, "document": document.text, "last_sentence": len(document.sentences()) - 1}, ensure_ascii=False)
        system = """You are KVIE's document intent classifier. Return JSON only with keys action, content, target_sentence, language. Allowed actions: append, replace_sentence, delete_sentence, insert_after_sentence, undo, redo, translate, rewrite, format, ignore. Never invent document content for delete/undo/redo. Keep content concise."""
        response, error = self.client.chat([{"role": "user", "content": prompt}], model=self.model, system=system, temperature=0.0, max_tokens=180)
        if error or not response:
            return None
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return None


class KvieDecisionEngine:
    def __init__(self, model_classifier: Optional[Callable[[str, DocumentState], Optional[dict]]] = None):
        self.rules = IntentEngine()
        self.model_classifier = model_classifier

    def decide(self, transcript: str, document: DocumentState) -> IntentDecision:
        rule_decision = self.rules.classify(transcript, document)
        if not rule_decision.requires_llm or self.model_classifier is None:
            return rule_decision
        try:
            payload = self.model_classifier(transcript, document)
            refined = self._validate(payload, document)
            return refined or rule_decision
        except Exception:
            return rule_decision

    def apply(self, decision: IntentDecision, document: DocumentState):
        return self.rules.apply(decision, document)

    @staticmethod
    def _validate(payload: Optional[dict], document: DocumentState) -> Optional[IntentDecision]:
        if not isinstance(payload, dict) or payload.get("action") not in ALLOWED_ACTIONS:
            return None
        action = payload["action"]
        target = payload.get("target_sentence")
        if target is not None and (not isinstance(target, int) or target < 0 or target >= len(document.sentences())):
            return None
        return IntentDecision(action=action, content=str(payload.get("content") or "").strip(), confidence=.8, target_sentence=target, language=str(payload.get("language") or "").strip() or None, reason="local LLM refinement", requires_llm=True)
