from Backend.kvie.intent_engine import IntentDecision
from Backend.kvie.session import KVIESession
from Backend.kvie.storage import KVIEStore


def test_session_connects_transcript_to_document_and_storage(tmp_path):
    store = KVIEStore(tmp_path / "kvie.sqlite3")
    session = KVIESession(store=store)
    result = session.process_transcript("We launched KVIE.")
    assert result.changed
    assert result.decision.action == "append"
    assert session.document.text == "We launched KVIE."
    assert store.load_document("active").text == "We launched KVIE."
    assert store.count("edit_operations") == 1
    store.close()


def test_session_correction_replaces_previous_sentence(tmp_path):
    store = KVIEStore(tmp_path / "kvie.sqlite3")
    session = KVIESession(store=store)
    session.process_transcript("We launched Kritix AI.")
    result = session.process_transcript("Actually, replace with We officially launched KVIE.")
    assert result.decision.action == "replace_sentence"
    assert session.document.text == "We officially launched KVIE"
    store.close()


def test_session_grammar_routing_applied_on_append(tmp_path):
    store = KVIEStore(tmp_path / "kvie.sqlite3")
    session = KVIESession(store=store)
    result = session.process_transcript("we launched critics and teh engine is working")
    assert result.changed
    assert result.grammar_changed is True
    assert result.decision.action == "append"
    assert "Kritix" in result.decision.content
    assert "the engine" in result.decision.content
    assert session.document.text == result.decision.content
    store.close()


def test_session_grammar_routing_applied_on_correction(tmp_path):
    store = KVIEStore(tmp_path / "kvie.sqlite3")
    session = KVIESession(store=store)
    session.process_transcript("We launched our old system.")
    result = session.process_transcript("Actually, replace with we launched critics and teh engine is working")
    assert result.changed
    assert result.grammar_changed is True
    assert result.decision.action == "replace_sentence"
    assert "Kritix" in result.decision.content
    assert "the engine" in result.decision.content
    assert session.document.text == result.decision.content
    store.close()


def test_session_grammar_routing_bypassed_for_non_content_commands(tmp_path):
    store = KVIEStore(tmp_path / "kvie.sqlite3")
    session = KVIESession(store=store)
    session.process_transcript("First sentence.")
    session.process_transcript("Second sentence.")

    # Undo command
    undo_res = session.process_transcript("undo")
    assert undo_res.decision.action == "undo"
    assert undo_res.grammar_changed is False

    # Redo command
    redo_res = session.process_transcript("redo")
    assert redo_res.decision.action == "redo"
    assert redo_res.grammar_changed is False

    # Delete sentence command
    del_res = session.process_transcript("delete the last sentence")
    assert del_res.decision.action == "delete_sentence"
    assert del_res.grammar_changed is False
    store.close()


def test_session_grammar_changed_false_when_no_edits_needed(tmp_path):
    store = KVIEStore(tmp_path / "kvie.sqlite3")
    session = KVIESession(store=store)
    result = session.process_transcript("We launched KVIE.")
    assert result.changed is True
    assert result.grammar_changed is False
    assert result.decision.content == "We launched KVIE."
    store.close()

