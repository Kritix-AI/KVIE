from Backend.kvie.document_state import DocumentState


def test_append_and_sentence_replacement_are_undoable():
    document = DocumentState("Hello everyone. We are building KVIE.")
    document.append("It is local-first.")
    assert document.sentences() == ["Hello everyone.", "We are building KVIE.", "It is local-first."]

    document.replace_sentence(1, "We are building a voice intelligence engine.")
    assert "voice intelligence engine" in document.text
    document.undo()
    assert "We are building KVIE." in document.text
    document.redo()
    assert "voice intelligence engine" in document.text


def test_insert_delete_and_cursor_are_tracked():
    document = DocumentState("Hello world")
    document.set_cursor(6)
    document.insert("brave ")
    assert document.text == "Hello brave world"
    assert document.cursor == 12
    document.delete(6, 12)
    assert document.text == "Hello world"
    assert document.snapshot().can_undo


def test_invalid_sentence_and_range_operations_fail_cleanly():
    document = DocumentState("One sentence.")
    try:
        document.replace_sentence(2, "No")
    except IndexError:
        pass
    else:
        raise AssertionError("expected invalid sentence index")

    try:
        document.replace(-1, 2, "No")
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid replacement range")
