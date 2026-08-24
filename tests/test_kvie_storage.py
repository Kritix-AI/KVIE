from Backend.kvie.document_state import DocumentState
from Backend.kvie.storage import KVIEStore
from Backend.voice.StreamingSTT import TranscriptEvent


def test_store_persists_documents_operations_and_events(tmp_path):
    store = KVIEStore(tmp_path / "kvie.sqlite3")
    document = DocumentState("Hello KVIE.")
    document.append("This is persistent.")
    store.save_document("doc-1", document)
    store.save_operation("doc-1", document.history()[-1])
    store.save_event("session-1", TranscriptEvent("final", "Hello KVIE.", "en", .98, 0, 1000, 1))
    store.close()

    reopened = KVIEStore(tmp_path / "kvie.sqlite3")
    loaded = reopened.load_document("doc-1")
    assert loaded is not None
    assert loaded.text == "Hello KVIE. This is persistent."
    assert reopened.count("documents") == 1
    assert reopened.count("edit_operations") == 1
    assert reopened.count("transcript_events") == 1
    reopened.close()
