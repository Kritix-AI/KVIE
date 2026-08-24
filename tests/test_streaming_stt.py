import threading
import time

from Backend.voice.StreamingSTT import StreamingSTT, StreamingSTTConfig


def test_sliding_windows_emit_partials_and_final_event():
    calls = []

    def fake_transcriber(audio, duration, language):
        calls.append((len(audio), duration, language))
        return f"chunk-{len(calls)}", 0.8

    config = StreamingSTTConfig(window_ms=1000, overlap_ms=250)
    engine = StreamingSTT(config=config, transcriber=fake_transcriber)
    engine.start()
    bytes_per_second = config.bytes_per_second
    engine.push_pcm(b"a" * int(bytes_per_second * 1.75))
    engine.flush()
    engine.stop(flush=False)

    events = list(engine.events())
    kinds = [event.kind for event in events]
    assert kinds[0] == "started"
    assert "partial" in kinds
    assert kinds[-1] == "stopped"
    assert any(event.kind == "final" for event in events)
    assert all(event.end_ms >= event.start_ms for event in events if event.kind in {"partial", "final"})
    assert len(calls) == 3


def test_engine_can_receive_chunks_from_another_thread():
    seen = []
    ready = threading.Event()

    def fake_transcriber(audio, duration, language):
        ready.set()
        return "hello", 0.9

    engine = StreamingSTT(
        config=StreamingSTTConfig(window_ms=400, overlap_ms=100),
        transcriber=fake_transcriber,
        on_event=seen.append,
    )
    producer = threading.Thread(target=lambda: engine.push_pcm(b"b" * 16000))
    producer.start()
    producer.join()
    assert ready.wait(2)
    engine.stop(flush=True)

    partials = [event for event in seen if event.kind == "partial"]
    assert partials
    assert partials[0].confidence == 0.9
    assert partials[0].language == ""


def test_invalid_window_configuration_is_rejected():
    try:
        StreamingSTT(StreamingSTTConfig(window_ms=500, overlap_ms=500))
    except ValueError as exc:
        assert "overlap_ms" in str(exc)
    else:
        raise AssertionError("expected invalid overlap configuration to fail")


def test_low_confidence_hypothesis_does_not_contaminate_stronger_partial():
    results = iter([("hallucinated", 0.0), ("real speech", 0.8)])

    def fake_transcriber(audio, duration, language):
        return next(results)

    config = StreamingSTTConfig(window_ms=400, overlap_ms=100)
    engine = StreamingSTT(config=config, transcriber=fake_transcriber)
    engine.start()
    engine.push_pcm(b"x" * config.bytes_per_second)
    engine.flush()
    engine.stop(flush=False)
    partials = [event.text for event in engine.events() if event.kind == "partial"]
    assert partials
    assert all("hallucinated" not in text for text in partials)


def test_merge_rolling_text_with_punctuation_and_overlap():
    left = "Hello everyone, how are you today."
    right = "Today we will start the demo."
    merged = StreamingSTT._merge_rolling_text(left, right)
    assert merged == "Hello everyone, how are you today. we will start the demo."


def test_merge_rolling_text_without_overlap():
    left = "Aaj meeting hai."
    right = "Sab log time pe aa jana."
    merged = StreamingSTT._merge_rolling_text(left, right)
    assert merged == "Aaj meeting hai. Sab log time pe aa jana."

