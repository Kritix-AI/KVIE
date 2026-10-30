import threading
import time

from Backend.voice.StreamingSTT import StreamingSTT, StreamingSTTConfig
def _synthetic_speech(duration_s: float, sample_rate: int = 16000, freq: float = 440.0, amplitude: float = 1000.0) -> bytes:
    """Generate synthetic PCM audio with speech-level RMS energy (> 200)."""
    import math
    import struct
    num_samples = int(sample_rate * duration_s)
    samples = [
        int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(num_samples)
    ]
    return struct.pack(f"<{num_samples}h", *samples)


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
    # 1.75s is fully covered by 2 full windows (0..1.0s and 0.75..1.75s); flush does not re-transcribe the 250ms overlap.
    assert len(calls) == 2


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
    engine.start()
    producer = threading.Thread(target=lambda: engine.push_pcm(b"b" * 16000))
    producer.start()
    producer.join()
    assert ready.wait(2)
    engine.stop(flush=True)

    partials = [event for event in seen if event.kind == "partial"]
    assert partials
    # Compact partial events intentionally omit confidence metadata.
    assert partials[0].text == "hello"
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
    assert merged == "Hello everyone, how are you today. Today we will start the demo."


def test_merge_rolling_text_without_overlap():
    left = "Aaj meeting hai."
    right = "Sab log time pe aa jana."
    merged = StreamingSTT._merge_rolling_text(left, right)
    assert merged == "Aaj meeting hai. Sab log time pe aa jana."


def test_merge_rolling_text_sentence_boundary_single_word_lowercase_and_uppercase():
    left = "I said no."
    right = "no I will not."
    assert StreamingSTT._merge_rolling_text(left, right) == "I said no. no I will not."

    right_upper = "No, I will not."
    assert StreamingSTT._merge_rolling_text(left, right_upper) == "I said no. No, I will not."


def test_draft_does_not_mutate_rolling_text_or_duplicate_clauses():
    calls = []
    responses = [
        ("call Alex", 0.8),             # 500ms draft
        ("call Alice tomorrow", 0.9),    # 1000ms full window
        ("", 0.0),                       # flush
    ]

    def fake_transcriber(audio, duration, language):
        calls.append((len(audio), duration))
        if responses:
            return responses.pop(0)
        return "", 0.0

    config = StreamingSTTConfig(
        window_ms=1000,
        overlap_ms=200,
        min_chunk_ms=400,
        draft_interval_ms=200,
    )
    engine = StreamingSTT(config=config, transcriber=fake_transcriber)
    engine.start()

    chunk_500ms = _synthetic_speech(0.5, config.sample_rate)

    # 1. Feed 500ms (accumulates >= 400ms min_chunk, triggering draft)
    engine.push_pcm(chunk_500ms)
    time.sleep(0.1)

    # 2. Feed second 500ms (buffer reaches 1000ms, triggering full window)
    engine.push_pcm(chunk_500ms)
    time.sleep(0.1)

    # 3. Flush and stop
    engine.flush()
    engine.stop(flush=False)

    events = list(engine.events())
    partials = [e.text for e in events if e.kind == "partial"]
    finals = [e.text for e in events if e.kind == "final"]

    assert "call Alex" in partials
    assert any("call Alice tomorrow" in p for p in partials)
    assert len(finals) == 1
    assert finals[0] == "call Alice tomorrow"
    assert "call Alex call Alice tomorrow" not in finals[0]


def test_flush_does_not_retranscribe_committed_overlap():
    calls = []
    responses = [
        ("Call life tomorrow.", 0.9),
        ("Bye to tomorrow.", 0.8),  # Must NOT be called
    ]

    def mock_transcriber(audio, duration, language):
        calls.append((len(audio), duration))
        return responses[len(calls) - 1]

    config = StreamingSTTConfig(window_ms=1000, overlap_ms=300)
    engine = StreamingSTT(config=config, transcriber=mock_transcriber)
    engine.start()

    # Feed exactly one full window (1000ms) and immediately flush
    pcm = b"\x00" * int(config.bytes_per_second * 1.0)
    engine.push_pcm(pcm)
    time.sleep(0.05)
    engine.flush()
    engine.stop(flush=False)

    finals = [e for e in engine.events() if e.kind == "final"]
    assert len(calls) == 1, f"Expected transcriber called once, got {len(calls)}"
    assert len(finals) == 1
    assert finals[0].text == "Call life tomorrow."
    assert "Bye to tomorrow" not in finals[0].text


def test_legitimate_repeated_words_are_preserved():
    assert (
        StreamingSTT._merge_rolling_text("", "The car was very very fast.")
        == "The car was very very fast."
    )
    assert (
        StreamingSTT._merge_rolling_text("", "I think that that is true.")
        == "I think that that is true."
    )
    assert (
        StreamingSTT._merge_rolling_text("", "No no no.")
        == "No no no."
    )
    assert (
        StreamingSTT._merge_rolling_text("The car was very very", "very fast.")
        == "The car was very very fast."
    )


def test_pause_clears_buffer_overlap():
    responses = [
        ("Hello world.", 0.9),   # Window 1 (speech)
        ("", 0.0),                # Window 2 (silence 1)
        ("", 0.0),                # Window 3 (silence 2 -> pause finalization)
        ("Next sentence.", 0.9), # Window 4 (new speech)
    ]
    call_idx = 0

    def mock_transcriber(audio, duration, language):
        nonlocal call_idx
        resp = responses[call_idx] if call_idx < len(responses) else ("", 0.0)
        call_idx += 1
        return resp

    config = StreamingSTTConfig(window_ms=1000, overlap_ms=250)
    engine = StreamingSTT(config=config, transcriber=mock_transcriber)
    engine.start()

    # Window 1: speech (1000ms)
    engine.push_pcm(b"\x01" * int(config.bytes_per_second * 1.0))
    time.sleep(0.05)

    # Window 2: silence (750ms -> brings buffer back to 1000ms)
    engine.push_pcm(b"\x00" * int(config.bytes_per_second * 0.75))
    time.sleep(0.05)

    # Window 3: silence (750ms -> brings buffer back to 1000ms, triggers pause finalization)
    engine.push_pcm(b"\x00" * int(config.bytes_per_second * 0.75))
    time.sleep(0.05)

    events = list(engine.events())
    finals = [e for e in events if e.kind == "final"]
    assert len(finals) == 1
    assert finals[0].text == "Hello world."
    assert len(engine._buffer) == 0, f"Expected empty buffer after pause, got {len(engine._buffer)}"

    # Window 4: new speech after pause
    engine.push_pcm(b"\x02" * int(config.bytes_per_second * 1.0))
    time.sleep(0.05)
    engine.flush()
    engine.stop(flush=False)

    events2 = list(engine.events())
    finals2 = [e for e in events2 if e.kind == "final"]
    assert len(finals2) == 1
    assert finals2[0].text == "Next sentence."


def test_trace_full_window_trailing_silence_drafts_and_flush():
    calls = []
    responses = [
        ("Call life tomorrow.", 0.9),
        ("Bye to tomorrow.", 0.8),
    ]

    def mock_transcriber(audio, duration, language):
        calls.append((len(audio), duration))
        if len(calls) == 1:
            return responses[0]
        return responses[1]

    config = StreamingSTTConfig(
        window_ms=1000,
        overlap_ms=300,
        min_chunk_ms=400,
        draft_interval_ms=100,
    )
    engine = StreamingSTT(config=config, transcriber=mock_transcriber)
    engine.start()

    # Window 1 (1000ms): commits speech ("Call life tomorrow.", 0.9)
    # Stride discards 700ms, leaving 300ms overlap.
    engine.push_pcm(_synthetic_speech(1.0, config.sample_rate))
    time.sleep(0.05)

    # Drain events after window 1 (started + window 1 partial)
    list(engine.events())

    # Feed trailing silence frames (5x 130ms = 650ms) to attempt triggering trailing drafts.
    frame_bytes = int(config.bytes_per_second * 0.13)
    for _ in range(5):
        engine.push_pcm(b"\x00" * frame_bytes)
        time.sleep(0.03)

    # Call engine.flush()
    engine.flush()
    engine.stop(flush=False)

    trailing_events = list(engine.events())
    trailing_partials = [e for e in trailing_events if e.kind == "partial"]
    finals = [e for e in trailing_events if e.kind == "final"]

    # Assert transcriber was called EXACTLY ONCE for window 1, and 0 times during drafts or flush
    assert len(calls) == 1, f"Expected transcriber called exactly once, got {len(calls)}"
    assert len(finals) == 1
    assert finals[0].text == "Call life tomorrow."
    assert "Bye to tomorrow" not in finals[0].text
    assert "Bye to" not in finals[0].text
    # Assert no trailing partial events are emitted after window 1
    assert len(trailing_partials) == 0, f"Expected 0 trailing partials, got {len(trailing_partials)}"


def test_trace_full_window_trailing_new_words_retained_once():
    calls = []
    responses = [
        ("Call life tomorrow.", 0.9),
        ("tomorrow and bring", 0.85),
        ("tomorrow and bring the keys.", 0.9),
    ]

    def mock_transcriber(audio, duration, language):
        calls.append((len(audio), duration))
        idx = min(len(calls) - 1, len(responses) - 1)
        return responses[idx]

    config = StreamingSTTConfig(
        window_ms=1000,
        overlap_ms=300,
        min_chunk_ms=400,
        draft_interval_ms=250,
    )
    engine = StreamingSTT(config=config, transcriber=mock_transcriber)
    engine.start()

    # Window 1 (1000ms): commits speech ("Call life tomorrow.", 0.9)
    engine.push_pcm(_synthetic_speech(1.0, config.sample_rate))
    time.sleep(0.05)

    # Feed trailing frames with genuinely spoken new words (5x 130ms = 650ms speech)
    frame_bytes = int(config.bytes_per_second * 0.13)
    speech_frame = _synthetic_speech(0.13, config.sample_rate)
    for _ in range(5):
        engine.push_pcm(speech_frame)
        time.sleep(0.02)

    # Call engine.flush()
    engine.flush()
    engine.stop(flush=False)

    events = list(engine.events())
    partials = [e for e in events if e.kind == "partial"]
    finals = [e for e in events if e.kind == "final"]

    # Verify calls: Window 1 (1.0s), Draft(s) during incoming speech, and final Flush
    assert len(calls) >= 2, f"Expected transcriber called for window and flush/drafts, got {len(calls)}"
    assert calls[0][0] == int(config.bytes_per_second * 1.0)
    # The final flush call receives overlap (300ms) + all trailing speech frames (650ms) = 950ms
    flush_call_bytes = calls[-1][0]
    expected_flush_bytes = int(config.bytes_per_second * 0.3) + (frame_bytes * 5)
    assert flush_call_bytes == expected_flush_bytes, f"Expected flush call to have {expected_flush_bytes} bytes, got {flush_call_bytes}"

    # Verify final transcript retains genuinely spoken continuation exactly once
    assert len(finals) == 1
    assert finals[0].text == "Call life tomorrow. and bring the keys."
    assert "Bye to" not in finals[0].text
    assert finals[0].text.count("tomorrow") == 1


def test_anchor_matching_does_not_delete_valid_clauses_or_sentence_openings():
    # Audit Case 1: Shared word in second clause must not delete opening clause
    assert (
        StreamingSTT._merge_rolling_text(
            "Call Alex tomorrow.", "See you tomorrow morning."
        )
        == "Call Alex tomorrow. See you tomorrow morning."
    )

    # Audit Case 2: Meeting continuation sharing anchor
    assert (
        StreamingSTT._merge_rolling_text(
            "I will go to the office tomorrow.", "Let us meet tomorrow at noon."
        )
        == "I will go to the office tomorrow. Let us meet tomorrow at noon."
    )

    # Audit Case 3: Sentence boundary repeated word (subject preservation)
    assert (
        StreamingSTT._merge_rolling_text("We need that.", "That was amazing.")
        == "We need that. That was amazing."
    )

    # Audit Case 4: Valid confirmation repeated sentence opener
    assert (
        StreamingSTT._merge_rolling_text("It is true.", "True stories are rare.")
        == "It is true. True stories are rare."
    )

    # Audit Case 5: Spoken repetition after sentence boundary
    assert (
        StreamingSTT._merge_rolling_text("I said no.", "No I will not.")
        == "I said no. No I will not."
    )
    assert (
        StreamingSTT._merge_rolling_text("I said no.", "no I will not.")
        == "I said no. no I will not."
    )
    assert (
        StreamingSTT._merge_rolling_text("I said no.", "No, I will not.")
        == "I said no. No, I will not."
    )

    # Multi-word genuine overlap across sliding windows
    assert (
        StreamingSTT._merge_rolling_text("Call Alex tomorrow", "Alex tomorrow is confirmed.")
        == "Call Alex tomorrow is confirmed."
    )


def test_default_transcriber_path_uses_stt_function(monkeypatch):
    from Backend.voice import STT

    calls = []

    def fake_transcribe_with_confidence(audio, duration, language=None, retry=False):
        calls.append((len(audio), duration, language, retry))
        return "default path verified", 0.95, "en"

    monkeypatch.setattr(STT, "transcribe_with_confidence", fake_transcribe_with_confidence)
    monkeypatch.setattr(STT, "is_loaded", lambda: True)

    config = StreamingSTTConfig(window_ms=1000, overlap_ms=200)
    engine = StreamingSTT(config=config)
    engine.start()
    engine.push_pcm(_synthetic_speech(1.0, config.sample_rate))
    engine.flush()
    engine.stop(flush=False)

    events = list(engine.events())
    errors = [event for event in events if event.kind == "error"]
    finals = [event for event in events if event.kind == "final"]

    assert not errors, f"Default transcriber emitted errors: {errors}"
    assert calls == [(config.window_bytes, 1.0, config.language, False)]
    assert len(finals) == 1
    assert finals[0].text == "default path verified"
