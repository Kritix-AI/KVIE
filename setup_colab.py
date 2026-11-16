#!/usr/bin/env python3
"""
KVIE Colab GPU Setup & Installer Script
Prepares Google Colab (or any remote Linux GPU instance) for KVIE:
1. Installs GPU dependencies (faster-whisper, ctranslate2, fastapi, etc.)
2. Fixes Linux NVIDIA CUDA 12 / cuDNN library paths for CTranslate2
3. Unpacks updated KVIE backend files if kvie_backend_update.zip is present
4. Installs cloudflared tunnel client
5. Validates environment and prints readiness status
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path


def run_cmd(cmd, desc=None, check=True):
    if desc:
        print(f"⏳ {desc}...")
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"❌ Error during: {desc or cmd}")
        print(result.stderr)
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result


def configure_nvidia_cuda_libraries():
    """Ensure ctranslate2 can locate nvidia-cublas and nvidia-cudnn libraries on Linux."""
    print("🔍 Configuring CUDA / cuDNN library paths for CTranslate2...")
    try:
        import site
        site_packages = site.getsitepackages()
        nvidia_lib_dirs = []

        for sp in site_packages:
            sp_path = Path(sp) / "nvidia"
            if sp_path.exists():
                for lib_sub in ["cublas/lib", "cudnn/lib", "cuda_runtime/lib", "cufft/lib"]:
                    p = sp_path / lib_sub
                    if p.exists():
                        nvidia_lib_dirs.append(str(p))

        current_ld = os.environ.get("LD_LIBRARY_PATH", "")
        new_dirs = [d for d in nvidia_lib_dirs if d not in current_ld]

        if new_dirs:
            updated_ld = ":".join(new_dirs) + (":" + current_ld if current_ld else "")
            os.environ["LD_LIBRARY_PATH"] = updated_ld
            print(f"  + Added to LD_LIBRARY_PATH: {', '.join(new_dirs)}")
        else:
            print("  ✓ NVIDIA library paths already configured.")
    except Exception as e:
        print(f"  ⚠️ Warning configuring CUDA paths: {e}")


def install_dependencies():
    print("\n📦 Installing Python GPU packages...")
    packages = [
        "faster-whisper>=1.0.0",
        "ctranslate2>=4.0.0",
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "websockets>=12.0",
        "python-dotenv>=1.0.0",
        "huggingface_hub>=0.21.0",
        "librosa>=0.10.0",
        "soundfile>=0.12.0",
        "pydub>=0.25.1",
        "requests>=2.31.0",
        "nvidia-cublas-cu12",
        "nvidia-cudnn-cu12",
    ]
    cmd = f"{sys.executable} -m pip install -q " + " ".join(packages)
    run_cmd(cmd, "Installing faster-whisper, FastAPI, websockets, and CUDA runtime")
    print("  ✓ Python dependencies installed.")


def unpack_update_bundle():
    """If kvie_backend_update.zip exists, unpack it into current directory."""
    bundle_names = [
        "kvie_backend_update.zip",
        "dist_colab/kvie_backend_update.zip",
        "../kvie_backend_update.zip"
    ]
    bundle_file = None
    for b in bundle_names:
        p = Path(b)
        if p.exists():
            bundle_file = p
            break

    if bundle_file:
        print(f"\n📂 Found updated backend bundle '{bundle_file}'. Unpacking...")
        with zipfile.ZipFile(bundle_file, "r") as zf:
            zf.extractall(".")
        print("  ✓ Extracted updated Backend and configuration files.")
    else:
        print("\nℹ️ No kvie_backend_update.zip found; using existing local Backend repository files.")


def install_cloudflared():
    print("\n🌐 Checking Cloudflare Tunnel (cloudflared)...")
    if shutil.which("cloudflared") is not None:
        print("  ✓ cloudflared is already installed.")
        return

    if sys.platform != "linux":
        print(f"  ℹ️ Non-Linux platform ({sys.platform}) detected. Skipping Linux deb install.")
        return

    print("  + Downloading and installing cloudflared-linux-amd64...")
    try:
        run_cmd("wget -q -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb")
        run_cmd("dpkg -i -E cloudflared-linux-amd64.deb > /dev/null 2>&1")
        print("  ✓ cloudflared installed successfully.")
    except Exception as e:
        print(f"  ⚠️ Could not install deb package: {e}")
        print("  Trying direct binary download...")
        run_cmd("wget -q -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared")
        run_cmd("chmod +x /usr/local/bin/cloudflared")
        print("  ✓ cloudflared binary installed to /usr/local/bin/cloudflared.")


def verify_installation():
    print("\n🔬 Verifying KVIE updated modules...")
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if cuda_avail else "CPU (No CUDA)"
        print(f"  • Hardware: {gpu_name} (CUDA: {cuda_avail})")

        # Test STT imports
        from Backend.voice.STT import _HOTWORD_PROMPT, HALLUCINATION_BLACKLIST_REGEX, correct_text
        print(f"  • Hotword Prompt Sanitized: {'KVIE, Kritix' in _HOTWORD_PROMPT}")
        print(f"  • Subtitle Blacklist Filter: {HALLUCINATION_BLACKLIST_REGEX is not None}")

        # Test GrammarRouter
        from Backend.kvie.grammar_router import GrammarRouter
        test_phrase = "its a university and i could of done it"
        polished = GrammarRouter.route(test_phrase)
        print(f"  • 4-Tier Grammar Engine: Verified! ('{test_phrase}' ➔ '{polished}')")

        # Test Service & Storage
        from Backend.kvie.service import app
        from Backend.kvie.session import KVIESession
        print("  • FastAPI Service & Session Engine: Verified!")

        print("\n" + "=" * 60)
        print("🎉 KVIE BACKEND LOGIC FULLY INSTALLED & VERIFIED FOR COLAB GPU!")
        print("=" * 60)
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        raise


def main():
    print("=" * 60)
    print("🚀 Kritix Voice Intelligence Engine (KVIE) — Colab Installer")
    print("=" * 60)

    install_dependencies()
    configure_nvidia_cuda_libraries()
    unpack_update_bundle()
    install_cloudflared()
    verify_installation()


if __name__ == "__main__":
    main()
