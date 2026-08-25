"""Local KVIE streaming transcription service.

Run with ``python -m Backend.kvie.service``. The browser/Tauri client sends
16 kHz mono signed-int16 PCM frames over WebSocket and receives JSON
TranscriptEvent objects from ``StreamingSTT``.
"""

from __future__ import annotations

import asyncio
import json
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
from Backend.voice import ModelManager


app = FastAPI(title="KVIE Local Streaming Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "service": "kvie-streaming-stt", "sample_rate": 16000})


@app.get("/api/models")
async def list_models():
    installed = ModelManager.get_installed_models()
    active = ModelManager.get_active_model_id()
    return JSONResponse({"installed": installed, "active": active})


class SelectModelRequest(BaseModel):
    model_id: str


@app.post("/api/models/select")
async def select_model(req: SelectModelRequest):
    success = ModelManager.set_active_model_id(req.model_id)
    return JSONResponse({"ok": success, "active": req.model_id})


@app.get("/api/models/download")
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


@app.websocket("/ws/transcribe")
async def transcribe_socket(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()
    outgoing: asyncio.Queue[dict] = asyncio.Queue()
    engine: Optional[StreamingSTT] = None
    store = KVIEStore()
    session = KVIESession(store=store)

    def handle_event(event: TranscriptEvent) -> None:
        outgoing.put_nowait(asdict(event))
        if event.kind == "final" and event.text.strip():
            result = session.process_transcript(event.text, asdict(event))
            outgoing.put_nowait({
                "kind": "document",
                "text": result.snapshot.text,
                "action": result.decision.action,
                "confidence": result.decision.confidence,
                "version": result.snapshot.version,
            })

    def publish(event: TranscriptEvent) -> None:
        loop.call_soon_threadsafe(handle_event, event)

    async def sender():
        while True:
            await websocket.send_json(await outgoing.get())

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            message = await websocket.receive()
            if message.get("bytes") is not None:
                if engine is None:
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
                if engine is not None:
                    await asyncio.to_thread(engine.stop)
                break
    except WebSocketDisconnect:
        pass
    finally:
        if engine is not None and engine.is_running:
            await asyncio.to_thread(engine.stop, False)
        sender_task.cancel()
        store.close()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
