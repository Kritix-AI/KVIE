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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

from Backend.voice.StreamingSTT import StreamingSTT, StreamingSTTConfig, TranscriptEvent
from Backend.kvie.session import KVIESession
from Backend.kvie.storage import KVIEStore


app = FastAPI(title="KVIE Local Streaming Service", version="0.1.0")


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "service": "kvie-streaming-stt", "sample_rate": 16000})


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
