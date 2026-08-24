from Backend.kvie.document_state import DocumentState
from Backend.kvie.semantic_match import SemanticMatcher


def test_lexical_match_finds_referenced_sentence():
    document = DocumentState("We launched the website. The team is planning a release. Tomorrow we will test the voice engine.")
    match = SemanticMatcher().best_sentence("the voice engine", document)
    assert match is not None
    assert match.sentence_index == 2


def test_embedding_provider_is_combined_and_failures_fallback():
    document = DocumentState("Alpha project. Beta project.")
    match = SemanticMatcher(lambda query, sentence: 1.0 if "beta" in sentence.lower() else 0.0).best_sentence("release", document)
    assert match is not None
    assert match.sentence_index == 1
    assert match.method == "embedding+lexical"

    fallback = SemanticMatcher(lambda query, sentence: (_ for _ in ()).throw(RuntimeError("offline"))).best_sentence("alpha", document)
    assert fallback is not None
    assert fallback.method == "lexical"
