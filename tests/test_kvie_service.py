from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from Backend.kvie.service import app, get_allowed_origins, is_origin_allowed, run


@pytest.fixture
def client():
    """TestClient without lifespan management for lightweight route testing."""
    return TestClient(app)


def test_streaming_service_exposes_health_and_websocket_routes():
    routes = {getattr(route, "path", None) for route in app.routes}
    assert "/health" in routes
    assert "/ws/transcribe" in routes


def test_cors_default_allowed_origins(client):
    # Origin in ALLOWED_BROWSER_ORIGINS must succeed with CORS header
    res = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert res.headers.get("access-control-allow-credentials") is None

    res_tauri = client.get("/health", headers={"Origin": "tauri://localhost"})
    assert res_tauri.status_code == 200
    assert res_tauri.headers.get("access-control-allow-origin") == "tauri://localhost"


def test_cors_native_client_without_origin(client):
    # Native clients (Tauri Rust IPC, cURL, Python) send no Origin header and must succeed
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok") is True


def test_cors_rejects_untrusted_origins(client):
    # Untrusted origins must be rejected with 403 Forbidden
    res = client.get("/health", headers={"Origin": "http://untrusted-domain.invalid"})
    assert res.status_code == 403
    assert res.json() == {"detail": "origin not allowed"}


def test_cors_dynamic_allowed_origins_comma_separated(client, monkeypatch):
    monkeypatch.setenv(
        "KVIE_ALLOWED_ORIGINS",
        " http://192.168.1.50:5173 , https://remote.kvie.app/ ",
    )

    # Cleaned and normalized origins should be permitted
    res1 = client.get("/health", headers={"Origin": "http://192.168.1.50:5173"})
    assert res1.status_code == 200
    assert res1.headers.get("access-control-allow-origin") == "http://192.168.1.50:5173"

    res2 = client.get("/health", headers={"Origin": "https://remote.kvie.app"})
    assert res2.status_code == 200
    assert res2.headers.get("access-control-allow-origin") == "https://remote.kvie.app"

    # Trailing slash requested should match normalized allowed origin
    res2_slash = client.get("/health", headers={"Origin": "https://remote.kvie.app/"})
    assert res2_slash.status_code == 200

    # Non-configured remote origin should still be rejected
    res3 = client.get("/health", headers={"Origin": "http://192.168.1.99:5173"})
    assert res3.status_code == 403
    assert res3.json() == {"detail": "origin not allowed"}


def test_cors_dynamic_allowed_origins_wildcard(client, monkeypatch):
    monkeypatch.setenv("KVIE_ALLOWED_ORIGINS", "*")

    res = client.get("/health", headers={"Origin": "https://any-external-domain.invalid"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "https://any-external-domain.invalid"
    assert res.headers.get("access-control-allow-credentials") is None


def test_websocket_origin_allowed(client):
    # Allowed origin connects and can handshake
    with client.websocket_connect("/ws/transcribe", headers={"Origin": "http://localhost:5173"}) as ws:
        # Send minimal stop to terminate gracefully
        ws.send_text('{"action": "stop"}')


def test_websocket_native_client_allowed(client):
    # Native client without Origin connects and can handshake
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text('{"action": "stop"}')


def test_websocket_origin_rejected(client):
    # Untrusted origin must be closed with code 1008 (Policy Violation) before accept
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/transcribe", headers={"Origin": "http://untrusted-domain.invalid"}):
            pass
    assert exc_info.value.code == 1008


def test_websocket_dynamic_origins_and_wildcard(client, monkeypatch):
    monkeypatch.setenv("KVIE_ALLOWED_ORIGINS", "http://192.168.1.50:5173")

    with client.websocket_connect("/ws/transcribe", headers={"Origin": "http://192.168.1.50:5173"}) as ws:
        ws.send_text('{"action": "stop"}')

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/transcribe", headers={"Origin": "http://other-domain.invalid"}):
            pass
    assert exc_info.value.code == 1008

    monkeypatch.setenv("KVIE_ALLOWED_ORIGINS", "*")
    with client.websocket_connect("/ws/transcribe", headers={"Origin": "http://any-domain.invalid"}) as ws:
        ws.send_text('{"action": "stop"}')


def test_health_endpoint_schema_and_telemetry_fields(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()

    # Core health fields
    assert data["ok"] is True
    assert data["service"] == "kvie-streaming-stt"
    assert data["sample_rate"] == 16000
    assert "model_loaded" in data
    assert "active_model" in data
    assert "model_ready" in data
    assert "device" in data
    assert "gpu_available" in data
    assert "active_connections" in data
    assert "audio_device" in data

    # 6 Structured GPU/VRAM telemetry fields
    assert "gpu_name" in data
    assert "compute_type" in data
    assert "vram_allocated_mb" in data
    assert "vram_reserved_mb" in data
    assert "vram_total_mb" in data
    assert "vram_free_mb" in data

    # Type assertions
    assert isinstance(data["compute_type"], str)
    assert data["gpu_name"] is None or isinstance(data["gpu_name"], str)
    assert data["vram_allocated_mb"] is None or isinstance(data["vram_allocated_mb"], (int, float))
    assert data["vram_reserved_mb"] is None or isinstance(data["vram_reserved_mb"], (int, float))
    assert data["vram_total_mb"] is None or isinstance(data["vram_total_mb"], (int, float))
    assert data["vram_free_mb"] is None or isinstance(data["vram_free_mb"], (int, float))


def test_health_telemetry_with_stt_data(client, monkeypatch):
    mock_telemetry = {
        "gpu_name": "NVIDIA GeForce RTX 4090",
        "compute_type": "float16",
        "vram_allocated_mb": 1234.5,
        "vram_reserved_mb": 2048.0,
        "vram_total_mb": 24576.0,
        "vram_free_mb": 22528.0,
        "device": "cuda",
    }
    monkeypatch.setattr("Backend.kvie.service._device_telemetry", lambda: mock_telemetry)

    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()

    assert data["gpu_name"] == "NVIDIA GeForce RTX 4090"
    assert data["compute_type"] == "float16"
    assert data["vram_allocated_mb"] == 1234.5
    assert data["vram_reserved_mb"] == 2048.0
    assert data["vram_total_mb"] == 24576.0
    assert data["vram_free_mb"] == 22528.0
    assert data["device"] == "cuda"


def test_lifespan_warmup_execution():
    # Lifespan startup triggers non-blocking background STT warmup
    with TestClient(app) as test_client:
        res = test_client.get("/health")
        assert res.status_code == 200


def test_run_defaults_and_env_configuration(monkeypatch):
    mock_uvicorn_run = MagicMock()
    monkeypatch.setattr("uvicorn.run", mock_uvicorn_run)

    # 1. Defaults when no args and no env vars
    monkeypatch.delenv("KVIE_HOST", raising=False)
    monkeypatch.delenv("KVIE_PORT", raising=False)
    run()
    mock_uvicorn_run.assert_called_with(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="info",
        ws_max_size=64 * 1024,
        limit_concurrency=16,
    )

    # 2. Environment variable overrides
    monkeypatch.setenv("KVIE_HOST", "0.0.0.0")
    monkeypatch.setenv("KVIE_PORT", "9000")
    run()
    assert mock_uvicorn_run.call_args[1]["host"] == "0.0.0.0"
    assert mock_uvicorn_run.call_args[1]["port"] == 9000

    # 3. Explicit arguments take precedence over environment variables
    run(host="10.0.0.5", port=8080)
    assert mock_uvicorn_run.call_args[1]["host"] == "10.0.0.5"
    assert mock_uvicorn_run.call_args[1]["port"] == 8080

    # 4. Invalid KVIE_PORT falls back to 8765
    monkeypatch.setenv("KVIE_PORT", "not_a_number")
    run()
    assert mock_uvicorn_run.call_args[1]["port"] == 8765


def test_autoedit_fallback_when_ollama_offline(client, monkeypatch):
    """When Ollama has no models or is offline, /api/autoedit falls back to GrammarRouter with HTTP 200."""
    from fastapi import HTTPException
    def mock_select(preferred=None):
        raise HTTPException(status_code=503, detail="no local Ollama model is installed")
    monkeypatch.setattr("Backend.kvie.service._select_installed_local_model", mock_select)

    res = client.post("/api/autoedit", json={"text": "we launched critics and teh engine is working", "style": "clean"})
    assert res.status_code == 200
    data = res.json()
    assert data["model"] == "grammar-router-fallback"
    assert data["style"] == "clean"
    assert "Kritix" in data["refined_text"]
    assert "the engine" in data["refined_text"]


def test_autoedit_fallback_when_ollama_generation_fails(client, monkeypatch):
    """When Ollama model exists but generate call errors out, fallback to GrammarRouter with HTTP 200."""
    monkeypatch.setattr("Backend.kvie.service._select_installed_local_model", lambda preferred=None: "qwen2.5:1.5b")
    monkeypatch.setattr("Backend.kvie.service._generate_local_text", lambda *args, **kwargs: (None, "connection refused"))

    res = client.post("/api/autoedit", json={"text": "we launched critics and teh engine is working", "style": "clean"})
    assert res.status_code == 200
    data = res.json()
    assert data["model"] == "grammar-router-fallback"
    assert "Kritix" in data["refined_text"]


def test_autoedit_success_with_ollama(client, monkeypatch):
    """When Ollama is operational, return the model output and model identifier."""
    monkeypatch.setattr("Backend.kvie.service._select_installed_local_model", lambda preferred=None: "qwen2.5:1.5b")
    monkeypatch.setattr("Backend.kvie.service._generate_local_text", lambda *args, **kwargs: ("Polished output from LLM.", None))

    res = client.post("/api/autoedit", json={"text": "we launched critics and teh engine is working", "style": "clean"})
    assert res.status_code == 200
    data = res.json()
    assert data["model"] == "qwen2.5:1.5b"
    assert data["refined_text"] == "Polished output from LLM."


def test_autoedit_validation_errors(client):
    """Invalid requests must return HTTP 400 Bad Request."""
    res_empty = client.post("/api/autoedit", json={"text": "", "style": "clean"})
    assert res_empty.status_code == 400

    res_style = client.post("/api/autoedit", json={"text": "Hello world", "style": "unsupported_style"})
    assert res_style.status_code == 400

    res_too_long = client.post("/api/autoedit", json={"text": "a" * 12001, "style": "clean"})
    assert res_too_long.status_code == 400

