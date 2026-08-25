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
    import time
    repo_id = MODEL_REPO_MAP.get(model_id, f"Systran/faster-whisper-{model_id}")

    with _active_download_lock:
        _current_downloads[model_id] = {"progress": 0, "status": "starting"}

    try:
        import requests
        from huggingface_hub import HfApi

        progress_callback({
            "model_id": model_id,
            "progress": 1.0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "status": "Connecting to Hugging Face...",
        })

        api = HfApi()
        repo_items = list(api.list_repo_tree(repo_id))
        files = [f for f in repo_items if hasattr(f, "size") and f.size is not None and not f.path.startswith(".git")]
        total_repo_bytes = sum(f.size for f in files) or 1

        org_repo = repo_id.replace("/", "--")
        cache_hub = os.path.expanduser("~/.cache/huggingface/hub")
        target_dir = os.path.join(cache_hub, f"models--{org_repo}", "snapshots", "main")
        os.makedirs(target_dir, exist_ok=True)

        downloaded_bytes = 0
        start_time = time.time()
        last_emit_time = start_time

        for item in files:
            file_path = item.path
            file_size = item.size
            dest_file = os.path.join(target_dir, file_path)
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)

            # Skip if already downloaded and size matches
            if os.path.exists(dest_file) and os.path.getsize(dest_file) == file_size:
                downloaded_bytes += file_size
                continue

            url = f"https://huggingface.co/{repo_id}/resolve/main/{file_path}"
            headers = {"User-Agent": "KVIE-Model-Downloader/1.0"}

            try:
                res = requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=60)
            except Exception:
                res = None

            if not res or res.status_code != 200:
                try:
                    from huggingface_hub import hf_hub_download
                    hf_hub_download(repo_id=repo_id, filename=file_path)
                    downloaded_bytes += file_size
                except Exception:
                    pass
                continue

            part_file = dest_file + ".part"
            with open(part_file, "wb") as f_out:
                for chunk in res.iter_content(chunk_size=1024 * 512):
                    if not chunk:
                        continue
                    f_out.write(chunk)
                    downloaded_bytes += len(chunk)

                    now = time.time()
                    if now - last_emit_time > 0.15:  # Emit every 150ms
                        last_emit_time = now
                        elapsed = max(now - start_time, 0.001)
                        speed_mb = (downloaded_bytes / (1024 * 1024)) / elapsed
                        pct = min(99.9, round((downloaded_bytes / total_repo_bytes) * 100, 1))
                        d_mb = downloaded_bytes / (1024 * 1024)
                        t_mb = total_repo_bytes / (1024 * 1024)

                        payload = {
                            "model_id": model_id,
                            "progress": pct,
                            "downloaded_bytes": downloaded_bytes,
                            "total_bytes": total_repo_bytes,
                            "status": f"Downloading {pct}% ({d_mb:.1f} MB / {t_mb:.1f} MB)",
                            "speed": f"{speed_mb:.1f} MB/s",
                        }
                        _current_downloads[model_id] = payload
                        try:
                            progress_callback(payload)
                        except Exception:
                            pass

            if os.path.exists(dest_file):
                try:
                    os.remove(dest_file)
                except Exception:
                    pass
            os.replace(part_file, dest_file)

        refs_dir = os.path.join(cache_hub, f"models--{org_repo}", "refs")
        os.makedirs(refs_dir, exist_ok=True)
        with open(os.path.join(refs_dir, "main"), "w", encoding="utf-8") as f_ref:
            f_ref.write("main\n")

        final_payload = {
            "model_id": model_id,
            "progress": 100.0,
            "downloaded_bytes": total_repo_bytes,
            "total_bytes": total_repo_bytes,
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
