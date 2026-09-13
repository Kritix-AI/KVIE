"""Local KVIE streaming transcription service.

Run with ``python -m Backend.kvie.service``. The browser/Tauri client sends
16 kHz mono signed-int16 PCM frames over WebSocket and receives JSON
TranscriptEvent objects from ``StreamingSTT``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from Backend.voice.StreamingSTT import StreamingSTT, StreamingSTTConfig, TranscriptEvent
from Backend.kvie.session import KVIESession
from Backend.kvie.storage import KVIEStore
from Backend.kvie.grammar_router import GrammarRouter
from Backend.voice import ModelManager

logger = logging.getLogger("kvie.service")


app = FastAPI(title="KVIE Local Streaming Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return JSONResponse({
        "service": "Kritix Voice Intelligence Engine (KVIE)",
        "status": "online",
        "version": "0.1.6",
        "endpoints": {
            "health": "/health",
            "models": "/api/models",
            "models_download": "/api/models/download?model_id=<id>",
            "websocket_stt": "/ws/transcribe",
            "transcribe": "/api/transcribe",
            "transcribe_partial": "/api/transcribe/partial",
            "swagger_docs": "/docs",
        },
        "message": "KVIE Backend Service is running successfully. Open the Kritix Desktop App or http://localhost:5173 for the graphical interface.",
    })


@app.get("/health")
async def health():
    return JSONResponse({
        "ok": True,
        "service": "kvie-streaming-stt",
        "sample_rate": 16000,
        "model_loaded": _is_model_loaded(),
        "active_connections": len(_active_connections),
        "audio_device": _audio_device_name(),
    })


# Track active connections for health endpoint
_active_connections: int = 0
_audio_device_name_cache: Optional[str] = None


def _is_model_loaded() -> bool:
    try:
        from Backend.voice.STT import get_model
        return get_model() is not None
    except Exception:
        return False


def _audio_device_name() -> Optional[str]:
    global _audio_device_name_cache
    if _audio_device_name_cache is not None:
        return _audio_device_name_cache
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            default = pa.get_default_input_device_info()
            _audio_device_name_cache = default.get("name", "unknown")
        except Exception:
            _audio_device_name_cache = None
        finally:
            pa.terminate()
    except Exception:
        _audio_device_name_cache = None
    return _audio_device_name_cache


@app.get("/api/models")
@app.get("/models")
async def list_models():
    installed = ModelManager.get_installed_models()
    active = ModelManager.get_active_model_id()
    return JSONResponse({"installed": installed, "active": active})


class SelectModelRequest(BaseModel):
    model_id: str


@app.post("/api/models/select")
@app.post("/models/select")
async def select_model(req: SelectModelRequest):
    success = ModelManager.set_active_model_id(req.model_id)
    return JSONResponse({"ok": success, "active": req.model_id})


@app.post("/api/models/download/start")
@app.get("/api/models/download/start")
@app.post("/models/download/start")
@app.get("/models/download/start")
async def start_model_download(model_id: str):
    success = ModelManager.start_download_background(model_id)
    return JSONResponse({"ok": success, "model_id": model_id})


@app.get("/api/models/progress")
@app.get("/models/progress")
async def get_model_progress(model_id: str):
    progress = ModelManager.get_download_progress(model_id)
    return JSONResponse(progress)


@app.get("/api/models/download")
@app.get("/models/download")
async def download_model_sse(model_id: str):
    loop = asyncio.get_running_loop()
    progress_queue: asyncio.Queue[Optional[dict]] = asyncio.Queue()

    def on_progress(data: dict):
        loop.call_soon_threadsafe(progress_queue.put_nowait, data)

    def worker():
        try:
            ModelManager.download_model_stream(model_id, on_progress)
        finally:
            loop.call_soon_threadsafe(progress_queue.put_nowait, None)

    async def event_generator():
        asyncio.create_task(asyncio.to_thread(worker))
        while True:
            item = await progress_queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Real-time Transcription HTTP Endpoints (for Android) ─────────────────

import io as _io_module
import numpy as _np

def _decode_wav_to_float32(wav_bytes: bytes) -> _np.ndarray:
    """Decode WAV bytes to float32 numpy array for Whisper."""
    try:
        import soundfile as sf
        data, sr = sf.read(_io_module.BytesIO(wav_bytes), dtype="float32")
        return data
    except ImportError:
        pass
    # Fallback: basic WAV header parsing → raw PCM
    import struct as _struct
    try:
        import wave as _wave
        with _wave.open(_io_module.BytesIO(wav_bytes), 'rb') as wf:
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
            arr = _np.frombuffer(raw, dtype=_np.int16).astype(_np.float32) / 32768.0
            return arr
    except Exception:
        return _np.array([], dtype=_np.float32)


@app.post("/api/transcribe")
async def transcribe_audio(request: Request):
    """Final transcription endpoint. Accepts WAV/PCM bytes, returns JSON text."""
    body = await request.body()
    if not body or len(body) < 100:
        return JSONResponse({"text": "", "error": "audio too short"}, status_code=400)

    is_partial = request.headers.get("X-Partial", "false").lower() == "true"

    try:
        audio_float32 = _decode_wav_to_float32(body)
        if len(audio_float32) == 0:
            return JSONResponse({"text": "", "error": "decode failed"})

        from Backend.voice.STT import transcribe_with_confidence
        duration = len(audio_float32) / 16000.0
        language = request.query_params.get("language", "auto")

        text, confidence = transcribe_with_confidence(audio_float32, duration, language)

        # Apply post-processing
        if text.strip():
            from Backend.voice.STT import correct_text
            text = correct_text(text)

        return JSONResponse({
            "text": text.strip(),
            "confidence": round(confidence, 3),
            "is_partial": is_partial,
            "duration_ms": int(duration * 1000),
        })
    except Exception as e:
        logger.error("Transcription error: %s", e)
        return JSONResponse({"text": "", "error": str(e)}, status_code=500)


@app.post("/api/transcribe/partial")
async def transcribe_partial(request: Request):
    """Lightning-fast partial transcription for streaming. Reduced beam size."""
    body = await request.body()
    if not body or len(body) < 50:
        return JSONResponse({"text": "", "confidence": 0.0})

    try:
        audio_float32 = _decode_wav_to_float32(body)
        if len(audio_float32) == 0:
            return JSONResponse({"text": "", "confidence": 0.0})

        from Backend.voice.STT import _transcribe_faster_whisper, _load_model
        import time as _time
        start = _time.monotonic()

        model = _load_model()
        if model is None:
            return JSONResponse({"text": "", "confidence": 0.0, "error": "model not loaded"})

        # Ultra-fast beam_size=1 for partials
        segments, info = model.transcribe(
            audio_float32,
            language=None,
            beam_size=1,
            vad_filter=False,  # VAD already applied on Android
            condition_on_previous_text=False,  # Don't lock into wrong context
            compression_ratio_threshold=999.0,  # Disable repetition penalty for speed
        )

        text = ""
        confidence = 0.0
        count = 0
        for seg in segments:
            text += seg.text
            confidence += seg.avg_logprob
            count += 1

        latency_ms = int((_time.monotonic() - start) * 1000)

        if count > 0:
            confidence = confidence / count

        # Light post-processing
        text = text.strip()
        text = text.replace("  ", " ")

        logger.debug("Partial transcription: %dms, text='%s'", latency_ms, text[:60])

        return JSONResponse({
            "text": text,
            "confidence": round(confidence, 3),
            "is_partial": True,
            "latency_ms": latency_ms,
        })
    except Exception as e:
        logger.debug("Partial transcription error: %s", e)
        return JSONResponse({"text": "", "confidence": 0.0})


@app.websocket("/ws/transcribe")
async def transcribe_socket(websocket: WebSocket):
    global _active_connections
    await websocket.accept()
    _active_connections += 1
    logger.info("WebSocket connected (active=%d)", _active_connections)

    loop = asyncio.get_running_loop()
    outgoing: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
    engine: Optional[StreamingSTT] = None
    store = KVIEStore()
    session = KVIESession(store=store)
    client_id = id(websocket)

    def handle_event(event: TranscriptEvent) -> None:
        """Process a transcript event — put to outgoing queue, parse document in background."""
        try:
            outgoing.put_nowait(asdict(event))
        except asyncio.QueueFull:
            logger.warning("outgoing queue full, dropping event kind=%s", event.kind)
            return

        # Parse document state without blocking the sender — fire-and-forget on thread pool.
        # IntentEngine.classify() is regex-fast; KvieDecisionEngine.decide() may call
        # Ollama (slow), so we offload everything to a worker thread.
        if event.kind in ("final",) and event.text.strip():
            def _parse():
                try:
                    result = session.process_transcript(event.text, asdict(event))
                    if result.changed:
                        loop.call_soon_threadsafe(outgoing.put_nowait, {
                            "kind": "document",
                            "text": result.snapshot.text,
                            "action": result.decision.action,
                            "confidence": result.decision.confidence,
                            "version": result.snapshot.version,
                        })
                    logger.info(
                        "pipeline_result",
                        extra={
                            "raw_stt": event.text[:120],
                            "grammar_changed": False,
                            "intent_changed": result.decision.action != "append",
                            "final_text_len": len(result.snapshot.text),
                            "ws_client": client_id,
                            "llm_used": result.decision.requires_llm,
                        },
                    )
                except Exception:
                    logger.exception("session.process_transcript failed")

            asyncio.get_running_loop().run_in_executor(None, _parse)

    def publish(event: TranscriptEvent) -> None:
        loop.call_soon_threadsafe(handle_event, event)

    async def sender():
        while True:
            msg = await outgoing.get()
            await websocket.send_json(msg)

    sender_task = asyncio.create_task(sender())
    try:
        # Send initial document snapshot
        snapshot = session.document.snapshot()
        await outgoing.put({
            "kind": "document",
            "text": snapshot.text,
            "action": "loaded",
            "version": snapshot.version,
        })

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                # Keep connection alive with a ping
                try:
                    await websocket.send_json({"kind": "ping"})
                except WebSocketDisconnect:
                    break
                continue

            if message.get("bytes") is not None:
                if engine is None:
                    logger.info("Client %d: creating engine from PCM stream", client_id)
                    engine = StreamingSTT(on_event=publish)
                    engine.start()
                engine.push_pcm(message["bytes"])
                continue

            raw = message.get("text")
            if raw is None:
                continue
            command = json.loads(raw)
            action = command.get("type")

            if action == "start":
                if engine is None:
                    config = StreamingSTTConfig(language=command.get("language", "auto"))
                    logger.info("Client %d: starting engine lang=%s", client_id, config.language)
                    engine = StreamingSTT(config=config, on_event=publish)
                    engine.start()
                    snapshot = session.document.snapshot()
                    await outgoing.put({
                        "kind": "document",
                        "text": snapshot.text,
                        "action": "loaded",
                        "version": snapshot.version,
                    })
            elif action == "flush" and engine is not None:
                await asyncio.to_thread(engine.flush)
                await outgoing.put({"kind": "flush-complete"})
            elif action == "stop":
                if engine is not None and engine.is_running:
                    await asyncio.to_thread(engine.stop, False)
                break
    except WebSocketDisconnect:
        logger.info("Client %d disconnected normally", client_id)
    except Exception:
        logger.exception("Client %d: unexpected error in WebSocket handler", client_id)
    finally:
        if engine is not None and engine.is_running:
            try:
                await asyncio.to_thread(engine.stop, False)
            except Exception:
                logger.exception("Error stopping engine for client %d", client_id)
        sender_task.cancel()
        try:
            await sender_task
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass
        store.close()
        _active_connections = max(0, _active_connections - 1)
        logger.info("Client %d disconnected (active=%d)", client_id, _active_connections)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
