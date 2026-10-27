"""KVIE Model Management & Real-Time Downloader

Manages downloading, caching, inspecting, and switching local speech and LLM models.
"""

from __future__ import annotations

import os
import hashlib
import threading
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, List, Optional
from urllib.parse import quote

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND_DIR)

MODEL_REPO_MAP = {
    "kritix-stt": "kritix-ai/Stt",
}

_active_download_lock = threading.Lock()
_current_downloads: Dict[str, dict] = {}
_MAX_MODEL_FILES = 512
_MAX_MODEL_DOWNLOAD_BYTES = 20 * 1024 * 1024 * 1024
_HF_REQUEST_ATTEMPTS = 3


def _is_retryable_hf_error(error: Exception) -> bool:
    """Recognize transient transport failures from requests and HF Hub clients."""
    name = type(error).__name__.lower()
    return any(token in name for token in ("connect", "timeout", "temporarilyunavailable"))


def _retry_hf_request(operation: Callable[[], object], description: str):
    """Retry transient Hugging Face API failures with short bounded backoff."""
    import time

    for attempt in range(1, _HF_REQUEST_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as error:
            if not _is_retryable_hf_error(error) or attempt == _HF_REQUEST_ATTEMPTS:
                raise
            delay = 0.5 * (2 ** (attempt - 1))
            print(
                f"[ModelManager] Temporary Hugging Face {description} failure "
                f"({type(error).__name__}); retrying in {delay:.1f}s ({attempt}/{_HF_REQUEST_ATTEMPTS - 1})",
                flush=True,
            )
            time.sleep(delay)


def _download_error_message(error: Exception) -> str:
    """Return actionable, non-sensitive diagnostics for the model UI."""
    name = type(error).__name__.lower()
    if "connect" in name or "timeout" in name:
        return (
            "KVIE could not connect to Hugging Face. Check this PC's internet, "
            "VPN/proxy or firewall access to huggingface.co, then retry."
        )

    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None) or getattr(error, "status_code", None)
    if status in (401, 403):
        return "Hugging Face denied access to this model. Check that the repository is public or that access is authorized."
    if status == 404:
        return "Hugging Face could not find this model repository or one of its files."
    if status == 429:
        return "Hugging Face is rate limiting model downloads. Wait a moment, then retry."
    if isinstance(status, int) and status >= 500:
        return "Hugging Face is temporarily unavailable. Wait a moment, then retry."
    return f"Model download failed ({type(error).__name__}). Check the KVIE backend log for details, then retry."


def _get_hub_cache_dir() -> Path:
    """Return the Hugging Face hub cache directory used by HF libraries."""
    configured = os.environ.get("HF_HUB_CACHE")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return (Path(hf_home).expanduser() / "hub").resolve(strict=False)
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache).expanduser() if xdg_cache else Path.home() / ".cache"
    return (base / "huggingface" / "hub").resolve(strict=False)


def _safe_model_file_path(target_dir: str | Path, remote_path: str) -> Path:
    """Resolve an HF repo path under the cache root; reject traversal and platform paths."""
    if not isinstance(remote_path, str) or not remote_path or "\\" in remote_path or "\x00" in remote_path:
        raise ValueError("invalid model file path")
    relative = PurePosixPath(remote_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} or ":" in part for part in relative.parts):
        raise ValueError("invalid model file path")
    root = Path(target_dir).resolve(strict=False)
    destination = root.joinpath(*relative.parts).resolve(strict=False)
    # Windows paths are case-insensitive while pathlib path comparisons are
    # case-sensitive. Compare normalized absolute paths to support HF repo IDs
    # whose owner/repo capitalization differs from the cache's canonical path.
    root_path = os.path.normcase(str(root))
    destination_path = os.path.normcase(str(destination))
    try:
        within_root = os.path.commonpath((root_path, destination_path)) == root_path
    except ValueError:
        within_root = False
    if destination_path == root_path or not within_root:
        raise ValueError("model file path escapes the cache directory")
    return destination


def _expected_sha256(file_entry) -> Optional[str]:
    """Read a Hugging Face LFS digest when the repository supplies one."""
    lfs = getattr(file_entry, "lfs", None)
    digest = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
    if not isinstance(digest, str):
        return None
    digest = digest.lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return None
    return digest


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_active_model_id() -> str:
    """Read currently configured ASR model from .env or fallback."""
    try:
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_ROOT, ".env"))
        configured = env.get("ASRModel") or env.get("WhisperModel") or "kritix-stt"
        return configured if configured in MODEL_REPO_MAP else "kritix-stt"
    except Exception:
        return "kritix-stt"


def get_model_snapshot_path(model_id: str) -> Optional[str]:
    """Return the verified local snapshot path used by the downloader.

    KVIE downloads model files directly into the Hugging Face cache layout.
    Loading by repository ID can still miss that snapshot when HF cache
    metadata differs, so STT should load this concrete directory instead.
    """
    repo_id = MODEL_REPO_MAP.get(model_id)
    if not repo_id:
        return None

    repo_dir = _get_hub_cache_dir() / ("models--" + repo_id.lower().replace("/", "--"))
    refs_file = repo_dir / "refs" / "main"
    try:
        revision = refs_file.read_text(encoding="utf-8").strip()
        snapshots_root = (repo_dir / "snapshots").resolve(strict=False)
        snapshot = (snapshots_root / revision).resolve(strict=False)
        if snapshots_root not in snapshot.parents:
            return None
        model_file = snapshot / "model.bin"
        if snapshot.is_dir() and model_file.is_file() and model_file.stat().st_size > 0:
            return str(snapshot)
    except (OSError, ValueError):
        return None
    return None


def set_active_model_id(model_id: str) -> bool:
    """Set active model in .env and reset loaded Whisper instance."""
    if not isinstance(model_id, str) or model_id not in MODEL_REPO_MAP:
        return False
    if model_id not in get_installed_models():
        return False

    try:
        from Backend.voice import STT
        STT._asr_model = None
        STT._loaded_device = None
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

        # Atomic replace: a crash mid-write must not corrupt the config.
        import tempfile
        fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(env_path) or ".", prefix=".env.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.replace(temp_path, env_path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            raise
        return True
    except Exception as e:
        print(f"[ModelManager] Failed to update .env ({type(e).__name__})", flush=True)
        return False


def get_download_progress(model_id: str) -> dict:
    """Get real-time download progress dictionary for a model."""
    if not isinstance(model_id, str) or model_id not in MODEL_REPO_MAP:
        return {"model_id": "", "progress": 0.0, "status": "error", "error": "Unknown model"}
    with _active_download_lock:
        if model_id in _current_downloads:
            return dict(_current_downloads[model_id])

    # If not currently in active downloads map, check if it's already installed
    installed = get_installed_models()
    if model_id in installed:
        return {
            "model_id": model_id,
            "progress": 100.0,
            "status": "completed",
        }

    return {
        "model_id": model_id,
        "progress": 0.0,
        "status": "idle",
    }


def start_download_background(model_id: str) -> bool:
    """Start background download thread if not already running."""
    if not isinstance(model_id, str) or model_id not in MODEL_REPO_MAP:
        return False
    with _active_download_lock:
        cur = _current_downloads.get(model_id, {})
        current_status = str(cur.get("status", "")).lower()
        if current_status in {"downloading", "starting", "connecting"} or current_status.startswith("downloading"):
            return True
        _current_downloads[model_id] = {
            "model_id": model_id,
            "progress": 1.0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "status": "connecting",
        }

    def _worker():
        try:
            download_model_stream(model_id, lambda p: None)
        except Exception as e:
            print(f"[ModelManager] Background download failed for {model_id} ({type(e).__name__})", flush=True)

    t = threading.Thread(target=_worker, name=f"kvie-model-{model_id}", daemon=True)
    t.start()
    return True


def get_installed_models() -> List[str]:
    """Scan local HuggingFace cache directory to detect installed models."""
    installed = set()

    # 1. Direct directory scan on local disk (fast & always accurate)
    hub_path = _get_hub_cache_dir()
    if os.path.exists(hub_path):
        try:
            for model_id, repo_id in MODEL_REPO_MAP.items():
                expected_dir = "models--" + repo_id.lower().replace("/", "--")
                repo_dir = hub_path / expected_dir
                refs_file = repo_dir / "refs" / "main"
                if not repo_dir.is_dir() or not refs_file.is_file():
                    continue
                revision = refs_file.read_text(encoding="utf-8").strip()
                snapshot = repo_dir / "snapshots" / revision
                weight_files = {"model.bin", "model.safetensors", "pytorch_model.bin", "model.ckpt", "model.nemo", "model.onnx"}
                if snapshot.is_dir() and any(
                    path.is_file()
                    and path.stat().st_size > 0
                    and (path.name.lower() in weight_files or (path.name.lower().startswith("model-") and path.name.lower().endswith(".safetensors")))
                    for path in snapshot.rglob("*")
                ):
                    installed.add(model_id)
        except Exception:
            pass

    return sorted(list(installed))


def download_model_stream(
    model_id: str,
    progress_callback: Callable[[dict], None],
) -> bool:
    """Download model weights with real-time byte & percentage progress callback."""
    import time
    if not isinstance(model_id, str) or model_id not in MODEL_REPO_MAP:
        return False
    repo_id = MODEL_REPO_MAP[model_id]

    with _active_download_lock:
        _current_downloads[model_id] = {"progress": 0, "status": "starting"}

    session = None
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from huggingface_hub import HfApi
        from urllib3.util.retry import Retry

        progress_callback({
            "model_id": model_id,
            "progress": 1.0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "status": "Connecting to Hugging Face...",
        })

        from huggingface_hub import get_token
        token = get_token()
        api = HfApi(token=token)
        repo_info = _retry_hf_request(
            lambda: api.model_info(repo_id, revision="main"),
            "repository lookup",
        )
        revision = repo_info.sha
        if not isinstance(revision, str) or not revision:
            raise ValueError("model repository did not return a revision")
        repo_files = _retry_hf_request(
            lambda: list(api.list_repo_tree(repo_id, revision=revision, recursive=True)),
            "file listing",
        )
        files = []
        for item in repo_files:
            if not hasattr(item, "size") or item.size is None or item.path.startswith(".git"):
                continue
            filename = PurePosixPath(item.path).name
            if "/" in item.path or not (
                filename in {"config.json", "preprocessor_config.json", "model.bin", "tokenizer.json"}
                or filename.startswith("vocabulary.")
            ):
                continue
            _safe_model_file_path(".", item.path)
            if not isinstance(item.size, int) or item.size < 0:
                raise ValueError("invalid model file metadata")
            if len(files) >= _MAX_MODEL_FILES:
                raise ValueError("model repository contains too many files")
            files.append(item)
        if not files or not any(item.path == "model.bin" for item in files):
            raise ValueError("selected repository does not contain a faster-whisper CTranslate2 model.bin")
        total_repo_bytes = sum(f.size for f in files) or 1
        if total_repo_bytes > _MAX_MODEL_DOWNLOAD_BYTES:
            raise ValueError("model download exceeds the configured size limit")

        org_repo = repo_id.lower().replace("/", "--")
        cache_hub = _get_hub_cache_dir()
        repo_cache = cache_hub / f"models--{org_repo}"
        target_dir = (repo_cache / "snapshots" / revision).resolve(strict=False)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Quick check if all files already exist with correct size
        all_exist = True
        for item in files:
            dest_file = _safe_model_file_path(
                repo_cache, f"snapshots/{revision}/{item.path}"
            )
            if not dest_file.exists() or not dest_file.is_file() or dest_file.stat().st_size != item.size:
                all_exist = False
                break
            expected_digest = _expected_sha256(item)
            if expected_digest and _file_sha256(dest_file) != expected_digest:
                all_exist = False
                break

        if all_exist and len(files) > 0:
            refs_dir = repo_cache / "refs"
            refs_dir.mkdir(parents=True, exist_ok=True)
            (refs_dir / "main").write_text(revision + "\n", encoding="utf-8")
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

        progress_callback({
            "model_id": model_id,
            "progress": 0.5,
            "downloaded_bytes": 0,
            "total_bytes": total_repo_bytes,
            "status": f"Downloading 0.5% (0 MB / {total_repo_bytes / (1024*1024):.1f} MB)",
        })

        downloaded_bytes = 0
        start_time = time.time()
        last_emit_time = start_time
        retry_policy = Retry(
            total=4,
            connect=4,
            read=3,
            status=4,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=retry_policy))
        session.mount("http://", HTTPAdapter(max_retries=retry_policy))

        for item in files:
            file_path = item.path
            file_size = item.size
            # HF cache snapshots may contain links into this repository's
            # blobs directory. Allow those links only while they remain inside
            # the repository cache root.
            dest_path = _safe_model_file_path(
                repo_cache, f"snapshots/{revision}/{file_path}"
            )
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            expected_digest = _expected_sha256(item)
            # Skip only a complete file whose size and available repository
            # digest both match. A same-size corrupt model must be replaced.
            if dest_path.exists() and dest_path.is_file() and dest_path.stat().st_size == file_size:
                if not expected_digest or _file_sha256(dest_path) == expected_digest:
                    downloaded_bytes += file_size
                    continue
                dest_path.unlink()

            url = f"https://huggingface.co/{repo_id}/resolve/{revision}/{quote(file_path, safe='/')}"
            headers = {"User-Agent": "KVIE-Model-Downloader/1.0"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            part_file = dest_path.with_name(dest_path.name + ".part")
            bytes_for_file = part_file.stat().st_size if part_file.is_file() else 0
            if bytes_for_file > file_size:
                part_file.unlink(missing_ok=True)
                bytes_for_file = 0
            if bytes_for_file == file_size and file_size > 0:
                if not expected_digest or _file_sha256(part_file) == expected_digest:
                    if dest_path.exists():
                        dest_path.unlink()
                    os.replace(part_file, dest_path)
                    downloaded_bytes += file_size
                    continue
                part_file.unlink(missing_ok=True)
                bytes_for_file = 0
            if bytes_for_file:
                headers["Range"] = f"bytes={bytes_for_file}-"
                downloaded_bytes += bytes_for_file
            try:
                with session.get(url, headers=headers, stream=True, allow_redirects=True, timeout=(10, 60)) as res:
                    if bytes_for_file and res.status_code == 416:
                        # The saved partial no longer matches the server's
                        # current range. Drop it so the next explicit retry
                        # starts this file from byte zero instead of looping on
                        # the same unsatisfiable Range request forever.
                        downloaded_bytes -= bytes_for_file
                        bytes_for_file = 0
                        part_file.unlink(missing_ok=True)
                    if bytes_for_file and res.status_code == 200:
                        # The CDN ignored Range. Restart this file cleanly.
                        downloaded_bytes -= bytes_for_file
                        bytes_for_file = 0
                    elif bytes_for_file and res.status_code == 206:
                        content_range = res.headers.get("Content-Range", "")
                        if not content_range.startswith(f"bytes {bytes_for_file}-"):
                            raise ValueError("model server returned an invalid resume range")
                    res.raise_for_status()
                    mode = "ab" if bytes_for_file else "wb"
                    with open(part_file, mode) as f_out:
                        for chunk in res.iter_content(chunk_size=1024 * 512):
                            if not chunk:
                                continue
                            bytes_for_file += len(chunk)
                            if bytes_for_file > file_size or downloaded_bytes + len(chunk) > _MAX_MODEL_DOWNLOAD_BYTES:
                                raise ValueError("downloaded model file exceeds its declared size")
                            f_out.write(chunk)
                            downloaded_bytes += len(chunk)

                            now = time.time()
                            if now - last_emit_time > 0.15:
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
                if bytes_for_file != file_size:
                    raise ValueError("downloaded model file size does not match repository metadata")
                if expected_digest and _file_sha256(part_file) != expected_digest:
                    part_file.unlink(missing_ok=True)
                    raise ValueError("downloaded model file failed Hugging Face SHA-256 verification")
                if dest_path.exists():
                    if dest_path.is_dir():
                        raise ValueError("model destination is not a file")
                    dest_path.unlink()
                os.replace(part_file, dest_path)
            except Exception:
                # Keep bounded partial files for HTTP Range resume on the next
                # retry; corrupt, overlong and wrong-digest files are removed.
                if part_file.exists() and part_file.stat().st_size > file_size:
                    part_file.unlink(missing_ok=True)
                raise

        refs_dir = repo_cache / "refs"
        refs_dir.mkdir(parents=True, exist_ok=True)
        (refs_dir / "main").write_text(revision + "\n", encoding="utf-8")

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
        detail = _download_error_message(e)
        response = getattr(e, "response", None)
        status = getattr(response, "status_code", None) or getattr(e, "status_code", None)
        suffix = f", HTTP {status}" if isinstance(status, int) else ""
        print(f"[ModelManager] Download failed for {model_id}: {type(e).__name__}{suffix}", flush=True)
        err_payload = {
            "model_id": model_id,
            "progress": 0.0,
            "status": "error",
            "error": detail,
        }
        _current_downloads[model_id] = err_payload
        progress_callback(err_payload)
        return False
    finally:
        if session is not None:
            session.close()
# ── Auto-download default model on import ─────────────────────────────────────
def auto_download_default_model() -> None:
    """Automatic downloads are disabled; the desktop UI starts downloads explicitly."""
    return
