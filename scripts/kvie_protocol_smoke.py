"""Verify the live KVIE WebSocket lifecycle against a running service."""

from __future__ import annotations

import asyncio
import json
import sys

import websockets


async def run() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8765/ws/transcribe"
    async with websockets.connect(url, open_timeout=5, close_timeout=5) as socket:
        await socket.send(json.dumps({"type": "start", "language": "auto"}))
        events = [json.loads(await asyncio.wait_for(socket.recv(), timeout=10)) for _ in range(2)]
        kinds = {event.get("kind") for event in events}
        assert "started" in kinds, events
        assert "document" in kinds, events

        await socket.send(json.dumps({"type": "flush"}))
        flushed = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        assert flushed.get("kind") == "flush-complete", flushed

        await socket.send(json.dumps({"type": "stop"}))
        print("KVIE WebSocket smoke test passed:", sorted(kinds | {flushed.get("kind")}))


if __name__ == "__main__":
    asyncio.run(run())
