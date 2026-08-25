"""KVIE Model Management & Real-Time Downloader

Manages downloading, caching, inspecting, and switching local speech and LLM models.
"""

from __future__ import annotations

import os
import re
import sys
import threading
from typing import Callable, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND_DIR)

MODEL_REPO_MAP = {
    "large-v3-turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",
    "trelis-hinglish": "Trelis/whisper-hinglish-preview",
    "srota-qwen3": "moorlee/qwen3-asr-0.6b-hinglish",
    "shunya-zero-stt": "shunyalabs/zero-stt-hinglish",
    "indic-conformer-600m": "ai4bharat/indic-conformer-600m-multilingual",
    "indicwhisper": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
}

_active_download_lock = threading.Lock()
_current_downloads: Dict[str, dict] = {}


def get_active_model_id() -> str:
    """Read currently configured ASR model from .env or fallback."""
    try:
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_ROOT, ".env"))
        return env.get("ASRModel") or env.get("WhisperModel") or "large-v3-turbo"
    except Exception:
        return "large-v3-turbo"


def set_active_model_id(model_id: str) -> bool:
    """Set active model in .env and reset loaded Whisper instance."""
    try:
        from Backend.voice import STT
        STT._asr_model = None
    except Exception:
        pass

    env_path = os.path.join(_ROOT, ".env")
    try:
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("ASRModel=") or line.startswith("WhisperModel="):
                        lines.append(f"ASRModel={model_id}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"ASRModel={model_id}\n")
            lines.append(f"WhisperModel={model_id}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"[ModelManager] Failed to update .env: {e}", flush=True)
        return False


def get_installed_models() -> List[str]:
    """Scan local HuggingFace cache to detect installed models."""
    installed = []
    try:
        from huggingface_hub import scan_cache_dir
        cache_info = scan_cache_dir()
        cached_repos = {repo.repo_id.lower() for repo in cache_info.repos}

        for model_id, repo_id in MODEL_REPO_MAP.items():
            if repo_id.lower() in cached_repos:
                installed.append(model_id)

        # Ensure default model is considered installed if already cached under alternative name
        if any("faster-whisper-large-v3-turbo" in r for r in cached_repos) and "large-v3-turbo" not in installed:
            installed.append("large-v3-turbo")

    except Exception as e:
        print(f"[ModelManager] Cache scan notice: {e}", flush=True)
        hub_path = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.exists(hub_path):
            try:
                dirs = os.listdir(hub_path)
                for d in dirs:
                    d_clean = d.lower().replace("models--", "").replace("--", "/")
                    for model_id, repo_id in MODEL_REPO_MAP.items():
                        if model_id not in installed:
                            if repo_id.lower() in d_clean or model_id in d_clean:
                                installed.append(model_id)
            except Exception:
                pass

    if "large-v3-turbo" not in installed:
        installed.append("large-v3-turbo")

    return list(dict.fromkeys(installed))


def download_model_stream(
    model_id: str,
    progress_callback: Callable[[dict], None],
) -> bool:
    """Download model weights with real-time byte & percentage progress callback."""
    repo_id = MODEL_REPO_MAP.get(model_id, f"Systran/faster-whisper-{model_id}")

    with _active_download_lock:
        _current_downloads[model_id] = {"progress": 0, "status": "starting"}

    try:
        from huggingface_hub import snapshot_download
        from tqdm.auto import tqdm

        class CallbackTqdm(tqdm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._tot = kwargs.get("total", 0) or 1
                self._cur = 0

            def update(self, n=1):
                super().update(n)
                self._cur += n
                pct = min(100.0, max(0.0, (self._cur / self._tot) * 100))
                payload = {
                    "model_id": model_id,
                    "progress": round(pct, 1),
                    "downloaded_bytes": self._cur,
                    "total_bytes": self._tot,
                    "status": "downloading",
                }
                _current_downloads[model_id] = payload
                try:
                    progress_callback(payload)
                except Exception:
                    pass

        progress_callback({
            "model_id": model_id,
            "progress": 2.0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "status": "connecting",
        })

        snapshot_download(
            repo_id=repo_id,
            tqdm_class=CallbackTqdm,
        )

        final_payload = {
            "model_id": model_id,
            "progress": 100.0,
            "status": "completed",
        }
        _current_downloads[model_id] = final_payload
        progress_callback(final_payload)
        return True

    except Exception as e:
        err_payload = {
            "model_id": model_id,
            "progress": 0.0,
            "status": "error",
            "error": str(e),
        }
        _current_downloads[model_id] = err_payload
        progress_callback(err_payload)
        return False
    finally:
        with _active_download_lock:
            _current_downloads.pop(model_id, None)
