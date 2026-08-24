"""End-to-end KVIE session orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .document_state import DocumentSnapshot, DocumentState
from .intent_engine import IntentDecision
from .llm_intent import KvieDecisionEngine
from .storage import KVIEStore


@dataclass(frozen=True)
class SessionResult:
    decision: IntentDecision
    snapshot: DocumentSnapshot
    changed: bool


class KVIESession:
    """Connect transcript text to safe decisions, document state, and storage."""

    def __init__(self, document_id: str = "active", store: Optional[KVIEStore] = None, decision_engine: Optional[KvieDecisionEngine] = None):
        self.document_id = document_id
        self.store = store
        self.decisions = decision_engine or KvieDecisionEngine()
        loaded = store.load_document(document_id) if store else None
        self.document = loaded or DocumentState()

    def process_transcript(self, text: str, metadata: Optional[dict] = None) -> SessionResult:
        decision = self.decisions.decide(text, self.document)
        before = self.document.text
        snapshot = self.decisions.apply(decision, self.document)
        changed = before != snapshot.text
        if changed and self.store:
            self.store.save_document(self.document_id, self.document)
            self.store.save_operation(self.document_id, self.document.history()[-1])
        return SessionResult(decision=decision, snapshot=snapshot, changed=changed)
