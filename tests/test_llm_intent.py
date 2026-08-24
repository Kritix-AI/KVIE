from Backend.kvie.document_state import DocumentState
from Backend.kvie.llm_intent import KvieDecisionEngine


def test_model_refinement_is_used_for_rewrite():
    document = DocumentState("Today I will explain AI.")
    engine = KvieDecisionEngine(lambda transcript, current: {"action": "rewrite", "content": "Rewrite professionally", "target_sentence": 0})
    decision = engine.decide("Rewrite this professionally", document)
    assert decision.action == "rewrite"
    assert decision.target_sentence == 0


def test_invalid_model_output_falls_back_to_rule_decision():
    document = DocumentState("Today I will explain AI.")
    engine = KvieDecisionEngine(lambda transcript, current: {"action": "execute_shell", "content": "danger"})
    decision = engine.decide("Rewrite this professionally", document)
    assert decision.action == "rewrite"
    assert decision.requires_llm


def test_model_cannot_target_a_nonexistent_sentence():
    document = DocumentState("One sentence.")
    engine = KvieDecisionEngine(lambda transcript, current: {"action": "rewrite", "target_sentence": 99})
    decision = engine.decide("Rewrite this", document)
    assert decision.action == "rewrite"
    assert decision.target_sentence == 0
