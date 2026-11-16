# Project: KVIE Backend & Integration Polish

## Architecture
KVIE is a low-latency local and remote voice dictation desktop application built with:
- **Desktop Shell**: Tauri v2 (Rust in `src-tauri/`) providing global hotkeys (`Alt+\``), hardware modifier release (`VK_MENU`), and low-level typing simulation (`enigo`).
- **Frontend Client**: React + Vite + TypeScript (`src/`) with real-time streaming audio worklets, sliding overlap deduplication (`stripCommittedOverlap`), models status polling, and Settings UI.
- **Backend Service**: FastAPI (`Backend/kvie/service.py`) exposing `/health`, `/models`, and real-time streaming STT over `/ws/transcribe`.
- **STT Engine**: CTranslate2 / Faster-Whisper (`Backend/voice/STT.py`) with CUDA acceleration, NVIDIA library resolution, non-blocking lifespan warmup, and VRAM telemetry.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | F1: Environment-driven host & port | `run()` binds to `KVIE_HOST` (default `127.0.0.1`) and `KVIE_PORT` (default `8765`) | M3 | R1 |
| 2 | F2: Dynamic allowed origins parsing | Parse `KVIE_ALLOWED_ORIGINS` (comma-separated or `*`) merging with `ALLOWED_BROWSER_ORIGINS` | M3 | R1 |
| 3 | F3: Dynamic HTTP CORS middleware | Validate HTTP Origin against merged allowed origins, supporting `*` | M3 | R1 |
| 4 | F4: WebSocket origin validation | Validate `/ws/transcribe` WebSocket Origin header against merged allowed origins (close 1008 if rejected) | M3 | R1 |
| 5 | F5: Background STT warmup lifespan | FastAPI lifespan handler executing non-blocking background STT warmup during startup | M3 | R1 |
| 6 | F6: Structured GPU/VRAM telemetry | `/health` endpoint returning `gpu_name`, `compute_type`, `vram_allocated_mb`, `vram_reserved_mb`, `vram_total_mb`, `vram_free_mb` | M3 | R1 |
| 7 | F7: Linux `.so` library resolution | `_register_nvidia_dlls()` searching and preloading Linux `.so` libraries via `LD_LIBRARY_PATH` and `ctypes.CDLL` | M2 | R2 |
| 8 | F8: STT warmup inference | `warmup(model_name=None)` executing 0.5s silent audio inference | M2 | R2 |
| 9 | F9: STT device telemetry | `get_device_telemetry()` returning device, compute type, and VRAM stats via PyTorch/NVML | M2 | R2 |
| 10 | F10: Relaxed remote URL validation | `modelsApi.ts` allowing non-loopback valid HTTP/HTTPS URLs | M4 | R3 |
| 11 | F11: URL change event & setter | `setServiceBaseUrl(url)` storing URL and dispatching `kvie_backend_url_changed` | M4 | R3 |
| 12 | F12: Updated health TypeScript types | `ServiceHealthResponse` with GPU and VRAM telemetry fields | M4 | R3 |
| 13 | F13: Client hook URL listener | `useLocalStreamingVoice.ts` listening for `kvie_backend_url_changed` and re-evaluating connection | M4 | R3 |
| 14 | F14: Settings UI Card | Settings tab card in `src/App.tsx` with remote URL input, status badge, and live GPU/VRAM badge | M4 | R3 |
| 15 | F15: Tauri WebView CSP | Update `src-tauri/tauri.conf.json` `connect-src` to allow remote backend endpoints (`http: https: ws: wss:`) | M4 | R3 |
| 16 | F16: Security Audit Pre-review | Formal security evaluation of `*` wildcard origin, CSWSH, and CORS attack vectors | M1 | AC Security |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Security Pre-requisite Review | Pre-implementation security audit of CORS and WebSocket origin validation | none | DONE |
| M2 | Component 3: STT & CUDA Acceleration | `Backend/voice/STT.py` (`_register_nvidia_dlls`, `warmup`, `get_device_telemetry`) | none | DONE |
| M3 | Component 2: FastAPI Service & Remote Networking | `Backend/kvie/service.py` & `tests/test_kvie_service.py` (lifespan warmup, CORS, `/health`, `run()`) | M1, M2 | DONE |
| M4 | Component 4: Client Remote Configuration | `modelsApi.ts`, `useLocalStreamingVoice.ts`, `App.tsx`, `tauri.conf.json` | M3 | DONE |
| M5 | Final E2E Verification & Sign-off | Run all unit tests, builds, and zero-trust verification | M4 | DONE |

## Interface Contracts
### `Backend/voice/STT.py` ↔ `Backend/kvie/service.py`
- `warmup(model_name: Optional[str] = None) -> bool`:
  - Warms up the STT engine with 0.5s of silent PCM audio. Non-blocking when called in an asyncio thread.
  - Returns `True` if warmed up, `False` on error.
- `get_device_telemetry() -> Dict[str, Any]`:
  - Returns dictionary with keys:
    - `gpu_name: Optional[str]`
    - `compute_type: Optional[str]`
    - `vram_allocated_mb: Optional[int]`
    - `vram_reserved_mb: Optional[int]`
    - `vram_total_mb: Optional[int]`
    - `vram_free_mb: Optional[int]`
    - `device: str` ("cuda" or "cpu")
    - `gpu_available: bool`

### `Backend/kvie/service.py` ↔ Frontend (`src/lib/modelsApi.ts`)
- `GET /health` JSON Response Contract:
  ```json
  {
    "ok": true,
    "service": "kvie-streaming-stt",
    "sample_rate": 16000,
    "model_loaded": true,
    "active_model": "deepdml/faster-whisper-large-v3-turbo-ct2",
    "model_ready": true,
    "device": "cuda",
    "gpu_available": true,
    "gpu_name": "NVIDIA GeForce RTX 4080",
    "compute_type": "float16",
    "vram_allocated_mb": 1450,
    "vram_reserved_mb": 2048,
    "vram_total_mb": 16384,
    "vram_free_mb": 14336,
    "active_connections": 0,
    "audio_device": "Microphone"
  }
  ```
- `WS /ws/transcribe`:
  - Origin header validated against `ALLOWED_BROWSER_ORIGINS` + `KVIE_ALLOWED_ORIGINS`.
  - Close code 1008 if rejected.

## Code Layout
- `Backend/voice/STT.py`: Owned by Milestone 2 (Worker 2)
- `Backend/kvie/service.py`: Owned by Milestone 3 (Worker 3)
- `tests/test_kvie_service.py`: Owned by Milestone 3 (Worker 3)
- `src/lib/modelsApi.ts`: Owned by Milestone 4 (Worker 4)
- `src/hooks/useLocalStreamingVoice.ts`: Owned by Milestone 4 (Worker 4)
- `src/App.tsx`: Owned by Milestone 4 (Worker 4)
- `src-tauri/tauri.conf.json`: Owned by Milestone 4 (Worker 4)
