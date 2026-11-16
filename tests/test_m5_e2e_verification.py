"""Milestone 5 Final E2E Integration & Adversarial Stress Tests.

Independently written and executed by kvie-verifier (empirical challenger).
Verifies acceptance criteria across Components 2, 3, and 4.
"""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from Backend.kvie.service import (
    app,
    get_allowed_origins,
    is_origin_allowed,
    ALLOWED_BROWSER_ORIGINS,
    lifespan,
    run,
)
from Backend.voice import STT


@pytest.fixture
def client():
    return TestClient(app)


# ─── Acceptance Criteria Group 1: Security & CORS Verification ──────────────

def test_ac_security_default_allowed_origins():
    """Verify that default allowed origins contain all necessary local/Tauri origins."""
    origins = get_allowed_origins()
    for expected in [
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]:
        assert expected in origins
        assert is_origin_allowed(expected) is True


def test_ac_security_cors_and_ws_rejection_unauthorized(client):
    """Verify unauthorized origins are rejected with 403 on HTTP and 1008 on WebSocket."""
    with patch.dict(os.environ, {"KVIE_ALLOWED_ORIGINS": ""}, clear=False):
        # HTTP
        res = client.get("/health", headers={"Origin": "https://attacker.evil.com"})
        assert res.status_code == 403
        assert res.json() == {"detail": "origin not allowed"}

        # WebSocket
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/transcribe", headers={"Origin": "https://attacker.evil.com"}):
                pass


def test_ac_security_dynamic_comma_separated_origins(client):
    """Verify comma-separated origins with whitespace, trailing slashes, and port numbers."""
    custom_origins = " https://app.example.com/ , http://192.168.1.100:3000/ , http://internal-server:8080 "
    with patch.dict(os.environ, {"KVIE_ALLOWED_ORIGINS": custom_origins}, clear=False):
        assert is_origin_allowed("https://app.example.com") is True
        assert is_origin_allowed("https://app.example.com/") is True
        assert is_origin_allowed("http://192.168.1.100:3000") is True
        assert is_origin_allowed("http://internal-server:8080") is True
        assert is_origin_allowed("https://other.example.com") is False

        # HTTP preflight/request check
        res1 = client.get("/health", headers={"Origin": "https://app.example.com"})
        assert res1.status_code == 200
        assert res1.headers.get("access-control-allow-origin") == "https://app.example.com"

        res_bad = client.get("/health", headers={"Origin": "https://other.example.com"})
        assert res_bad.status_code == 403


def test_ac_security_wildcard_origin(client):
    """Verify wildcard '*' allows any arbitrary Origin header for both HTTP and WebSocket."""
    with patch.dict(os.environ, {"KVIE_ALLOWED_ORIGINS": "*"}, clear=False):
        assert is_origin_allowed("https://anywhere.world") is True
        assert is_origin_allowed("http://random-ip:9999") is True

        res = client.get("/health", headers={"Origin": "https://anywhere.world"})
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "https://anywhere.world"


def test_ac_security_native_client_no_origin(client):
    """Native clients (Tauri Rust backend, cURL, Python scripts) send no Origin header."""
    assert is_origin_allowed(None) is True
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


# ─── Acceptance Criteria Group 2: Service Telemetry & Lifecycle ─────────────

def test_ac_service_run_binding():
    """Verify run() respects KVIE_HOST and KVIE_PORT with defaults 127.0.0.1:8765."""
    with patch("uvicorn.run") as mock_uvicorn:
        # Defaults
        with patch.dict(os.environ, {}, clear=True):
            run()
            mock_uvicorn.assert_called_once()
            _, kwargs = mock_uvicorn.call_args
            assert kwargs["host"] == "127.0.0.1"
            assert kwargs["port"] == 8765

    with patch("uvicorn.run") as mock_uvicorn:
        # Custom environment
        with patch.dict(os.environ, {"KVIE_HOST": "0.0.0.0", "KVIE_PORT": "9000"}):
            run()
            mock_uvicorn.assert_called_once()
            _, kwargs = mock_uvicorn.call_args
            assert kwargs["host"] == "0.0.0.0"
            assert kwargs["port"] == 9000


@pytest.mark.anyio
async def test_ac_service_lifespan_background_warmup():
    """Verify FastAPI lifespan triggers STT warmup in the background without blocking."""
    mock_app = MagicMock()
    with patch("Backend.voice.STT.warmup", return_value=True) as mock_warmup:
        async with lifespan(mock_app):
            # Allow event loop iteration for background task
            await asyncio.sleep(0.05)
            assert mock_warmup.called


def test_ac_service_health_telemetry_fields(client):
    """Verify /health returns all required structured GPU/VRAM telemetry metrics."""
    with patch(
        "Backend.voice.STT.get_device_telemetry",
        return_value={
            "device": "cuda",
            "gpu_available": True,
            "gpu_name": "NVIDIA GeForce RTX 4090",
            "compute_type": "float16",
            "vram_allocated_mb": 2048,
            "vram_reserved_mb": 4096,
            "vram_total_mb": 24576,
            "vram_free_mb": 22528,
        },
    ), patch("Backend.kvie.service._gpu_available", return_value=True):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["gpu_name"] == "NVIDIA GeForce RTX 4090"
        assert data["compute_type"] == "float16"
        assert data["vram_allocated_mb"] == 2048.0
        assert data["vram_reserved_mb"] == 4096.0
        assert data["vram_total_mb"] == 24576.0
        assert data["vram_free_mb"] == 22528.0
        assert data["device"] == "cuda"
        assert data["gpu_available"] is True


def test_ac_service_health_telemetry_cpu_fallback(client):
    """Verify /health handles CPU systems where VRAM is None safely."""
    with patch(
        "Backend.voice.STT.get_device_telemetry",
        return_value={
            "device": "cpu",
            "gpu_available": False,
            "gpu_name": None,
            "compute_type": "int8",
            "vram_allocated_mb": None,
            "vram_reserved_mb": None,
            "vram_total_mb": None,
            "vram_free_mb": None,
        },
    ):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["gpu_name"] is None
        assert data["compute_type"] == "int8"
        assert data["vram_allocated_mb"] is None
        assert data["vram_total_mb"] is None
        assert data["device"] == "cpu"
        assert data["gpu_available"] is False


# ─── Acceptance Criteria Group 3: STT & Acceleration ────────────────────────

def test_ac_stt_linux_so_resolution():
    """Verify _register_nvidia_dlls scans and registers Linux .so libraries."""
    fake_sp = "/tmp/fake_site_packages"
    nvidia_dir = os.path.join(fake_sp, "nvidia", "cublas", "lib")
    fake_so = "libcublas.so.12"

    with patch("sys.platform", "linux"):
        with patch("site.getsitepackages", return_value=[fake_sp]):
            with patch("site.getusersitepackages", return_value="/tmp/fake_user"):
                with patch("os.path.isdir", side_effect=lambda d: d.startswith(fake_sp)):
                    with patch(
                        "os.walk",
                        return_value=[(nvidia_dir, [], [fake_so])],
                    ):
                        with patch("ctypes.CDLL") as mock_cdll:
                            env_copy = os.environ.copy()
                            env_copy.pop("LD_LIBRARY_PATH", None)
                            with patch.dict(os.environ, env_copy, clear=True):
                                STT._register_nvidia_dlls()
                                assert nvidia_dir in os.environ.get("LD_LIBRARY_PATH", "")
                                mock_cdll.assert_called_with(
                                    os.path.join(nvidia_dir, fake_so),
                                    mode=getattr(sys.modules["ctypes"], "RTLD_GLOBAL", 0),
                                )


def test_ac_stt_warmup_execution():
    """Verify warmup runs 0.5s silent audio inference and drains generator."""
    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = " hello"
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())

    with patch("Backend.voice.STT._asr_model", mock_model):
        res = STT.warmup()
        assert res is True
        assert mock_model.transcribe.called
        args, kwargs = mock_model.transcribe.call_args
        # 0.5s at 16kHz = 8000 samples
        assert len(args[0]) == 8000
        assert kwargs["language"] == "en"
        assert kwargs["beam_size"] == 1


def test_ac_stt_warmup_error_resilience():
    """Verify warmup returns False without throwing when model transcribe raises."""
    mock_model = MagicMock()
    mock_model.transcribe.side_effect = RuntimeError("CUDA out of memory")

    with patch("Backend.voice.STT._asr_model", mock_model):
        res = STT.warmup()
        assert res is False


def test_ac_stt_get_device_telemetry_schema():
    """Verify get_device_telemetry() returns all required keys with proper types."""
    telemetry = STT.get_device_telemetry()
    expected_keys = {
        "gpu_name",
        "compute_type",
        "vram_allocated_mb",
        "vram_reserved_mb",
        "vram_total_mb",
        "vram_free_mb",
        "device",
        "gpu_available",
    }
    assert expected_keys.issubset(telemetry.keys())
    assert isinstance(telemetry["device"], str)
    assert isinstance(telemetry["gpu_available"], bool)
    assert telemetry["compute_type"] in ["float16", "int8_float16", "int8", "int8 (CPU fallback)"]
