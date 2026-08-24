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
