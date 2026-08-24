from Backend.kvie.document_state import DocumentState
from Backend.kvie.intent_engine import IntentEngine


def test_rules_classify_and_apply_correction():
    document = DocumentState("We launched Kritix AI.")
    engine = IntentEngine()
    decision = engine.classify("Actually, replace with We officially launched Kritix AI", document)
    assert decision.action == "replace_sentence"
    engine.apply(decision, document)
    assert document.text == "We officially launched Kritix AI"


def test_insert_delete_undo_and_append_intents():
    document = DocumentState("First sentence. Last sentence.")
    engine = IntentEngine()
    engine.apply(engine.classify("Insert a middle sentence after first sentence.", document), document)
    assert document.text == "First sentence. a middle sentence Last sentence."
    engine.apply(engine.classify("Delete the last sentence", document), document)
    assert "Last sentence" not in document.text
    engine.apply(engine.classify("Undo", document), document)
    assert "Last sentence" in document.text
    engine.apply(engine.classify("And one more thought.", document), document)
    assert document.text.endswith("And one more thought.")


def test_model_backed_intents_are_explicitly_flagged():
    document = DocumentState("Today I will explain AI.")
    decision = IntentEngine().classify("Rewrite this in a more professional tone", document)
    assert decision.action == "rewrite"
    assert decision.requires_llm


def test_semantic_sentence_targeting_finds_meaningful_reference():
    document = DocumentState("We launched the website. Tomorrow we will test the voice engine.")
    decision = IntentEngine().classify("Replace the sentence about the voice engine with We will test KVIE.", document)
    assert decision.action == "replace_sentence"
    assert decision.target_sentence == 1
