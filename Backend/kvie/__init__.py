"""Core domain modules for the Kritix Voice Intelligence Engine."""

from .document_state import DocumentState, EditOperation, DocumentSnapshot
from .intent_engine import IntentDecision, IntentEngine
from .storage import KVIEStore
from .llm_intent import KvieDecisionEngine, OllamaIntentClassifier
from .session import KVIESession, SessionResult
from .semantic_match import SemanticMatcher, SentenceMatch

__all__ = ["DocumentState", "EditOperation", "DocumentSnapshot", "IntentDecision", "IntentEngine", "KVIEStore", "KvieDecisionEngine", "OllamaIntentClassifier", "KVIESession", "SessionResult", "SemanticMatcher", "SentenceMatch"]
