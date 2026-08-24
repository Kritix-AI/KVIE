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
from fastapi.responses import JSONResponse
import uvicorn

from Backend.voice.StreamingSTT import StreamingSTT, StreamingSTTConfig, TranscriptEvent
from Backend.kvie.session import KVIESession
from Backend.kvie.storage import KVIEStore
from Backend.kvie.document_state import DocumentState
from Backend.kvie.intent_engine import IntentEngine
from Backend.kvie.llm_intent import KvieDecisionEngine, OllamaIntentClassifier
from Backend.voice.OllamaClient import get_ollama_client


app = FastAPI(title="KVIE Local Streaming Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

intent_engine = IntentEngine()
decision_engine = KvieDecisionEngine(model_classifier=OllamaIntentClassifier())


@app.get("/health")
async def health():
    return JSONResponse({"ok": True, "service": "kvie-streaming-stt", "sample_rate": 16000})


@app.post("/api/intent/classify")
async def classify_intent(request: Request):
    """Classifies user spoken intent and returns structured JSON decision."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)

    transcript = str(data.get("transcript") or "").strip()
    doc_text = str(data.get("document") or "").strip()
    doc = DocumentState(doc_text)

    decision = decision_engine.decide(transcript, doc)
    return JSONResponse({
        "ok": True,
        "action": decision.action,
        "content": decision.content,
        "confidence": decision.confidence,
        "target_sentence": decision.target_sentence,
        "language": decision.language,
        "reason": decision.reason,
        "requires_llm": decision.requires_llm,
    })


@app.post("/api/command/execute")
async def execute_command(request: Request):
    """Executes a voice command on given text context and returns structured JSON."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)

    command = str(data.get("command") or "").strip()
    context = str(data.get("context") or "").strip()
    app_name = str(data.get("app_name") or "Desktop App").strip()

    if not command:
        return JSONResponse({
            "ok": True,
            "is_command": False,
            "intent": "empty",
            "transformed_text": context,
            "action": "none",
        })

    # Classify intent first
    doc = DocumentState(context)
    decision = intent_engine.classify(command, doc)

    # Handle deterministic document actions
    if decision.action == "clear":
        return JSONResponse({
            "ok": True,
            "is_command": True,
            "intent": "clear",
            "action": "clear",
            "transformed_text": "",
        })
    if decision.action == "undo":
        return JSONResponse({
            "ok": True,
            "is_command": True,
            "intent": "undo",
            "action": "undo",
            "transformed_text": "",
        })

    # Run local LLM to execute voice transformation
    client = get_ollama_client()
    system_prompt = f"""You are KVIE's Voice Command Engine.
Your task is to execute the user's voice instruction on the target text.

Target App: {app_name}
Voice Instruction: "{command}"

TARGET TEXT:
"{context[:1000]}"

RULES:
1. Transform the target text strictly according to the voice instruction (e.g. make formal, summarize in bullet points, fix grammar, shorten, expand, rewrite).
2. If TARGET TEXT is empty, compose a high-quality draft answering the voice instruction directly.
3. If Roman Hinglish is used, preserve Hinglish style.
4. Output ONLY the transformed text. Do NOT add meta commentary, explanations, or quotes."""

    response, error = client.chat(
        messages=[{"role": "user", "content": f"Execute instruction: {command}\n\nTarget text:\n{context}"}],
        system=system_prompt,
        temperature=0.2,
        max_tokens=400,
    )

    if not error and response:
        cleaned = response.strip().strip('"\'`')
        return JSONResponse({
            "ok": True,
            "is_command": True,
            "intent": decision.action,
            "action": "replace_text",
            "transformed_text": cleaned,
        })

    # Fallback if LLM offline
    return JSONResponse({
        "ok": True,
        "is_command": True,
        "intent": decision.action,
        "action": "fallback",
        "transformed_text": context or command,
    })


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
