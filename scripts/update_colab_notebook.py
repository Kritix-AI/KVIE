import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_PATH = ROOT / "kvie_colab_gpu.ipynb"

nb = {
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# 🎙️ Kritix Voice Intelligence Engine (KVIE) — Colab GPU Studio\n",
    "\n",
    "Run KVIE's upgraded speech-to-text inference engine, anti-hallucination guardrails, 4-tier grammar polisher, and FastAPI WebSocket server on a **free cloud NVIDIA GPU (T4 / A100)**.\n",
    "\n",
    "### What this updated notebook provides:\n",
    "1. **⚡ Faster-Whisper Large-v3-Turbo on CUDA**: Transcribes speech chunks in **~120–180 ms** using GPU Tensor Cores with greedy decoding (`temperature=0.0`).\n",
    "2. **🛡️ Anti-Hallucination & Subtitle Blacklist**: Eliminates web/YouTube hallucination loops on silence with strict VAD energy gating and sanitized hotword prompts.\n",
    "3. **✨ 4-Tier Multi-Tier Grammar Polisher (`GrammarRouter`)**: Automatically corrects typos, brand casing (`Kritix`, `GitHub`, `VS Code`), phonetic articles (`a university` / `an hour`), modal verbs, and removes verbal disfluencies (`um`, `uh`).\n",
    "4. **🌐 Remote Tunnel to Desktop KVIE**: Expose the backend via Cloudflare Tunnel so your local desktop KVIE app connects seamlessly to this cloud GPU with live VRAM telemetry!"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 1. Verify GPU Acceleration & Hardware Specs"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Check NVIDIA GPU allocation in Colab\n",
    "!nvidia-smi\n",
    "\n",
    "import torch\n",
    "print(f\"CUDA Available: {torch.cuda.is_available()}\")\n",
    "if torch.cuda.is_available():\n",
    "    gpu_name = torch.cuda.get_device_name(0)\n",
    "    total_mem = torch.cuda.get_device_properties(0).total_memory / 1e9\n",
    "    print(f\"Active GPU: {gpu_name}\")\n",
    "    print(f\"VRAM: {total_mem:.2f} GB\")\n",
    "else:\n",
    "    print(\"⚠️ WARNING: No GPU detected! Please go to: Runtime -> Change runtime type -> Hardware accelerator -> T4 GPU\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 2. Install KVIE & Updated Logic\n",
    "This step installs all required CUDA packages, sets up CTranslate2 library paths, installs `cloudflared`, and unpacks the latest updated KVIE backend logic."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1. Clone repository (or pull latest changes)\n",
    "!git clone https://github.com/Aryan-sourcee/KVIE.git 2>/dev/null || (cd KVIE && git pull)\n",
    "%cd KVIE\n",
    "\n",
    "# 2. Check for uploaded update bundle (if you uploaded kvie_backend_update.zip to Colab)\n",
    "import os, zipfile\n",
    "for bundle_path in [\"../kvie_backend_update.zip\", \"kvie_backend_update.zip\", \"/content/kvie_backend_update.zip\", \"dist_colab/kvie_backend_update.zip\"]:\n",
    "    if os.path.exists(bundle_path):\n",
    "        print(f\"📦 Found update bundle '{bundle_path}'. Unpacking updated KVIE logic...\")\n",
    "        with zipfile.ZipFile(bundle_path, \"r\") as zf:\n",
    "            zf.extractall(\".\")\n",
    "        break\n",
    "\n",
    "# 3. Run automated installer (installs packages, configures CUDA 12 paths, installs cloudflared)\n",
    "!bash install_colab.sh"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 3. Hugging Face Login (Optional for Gated Models)\n",
    "If you plan to use gated models like `kritix-ai/Swar-stt`, enter your Hugging Face Token below. Otherwise, public models like `Systran/faster-whisper-large-v3-turbo` work instantly without a token."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "import os\n",
    "from huggingface_hub import login\n",
    "\n",
    "# Paste your HF token here if using gated models\n",
    "HF_TOKEN = \"\"  # @param {type:\"string\"}\n",
    "\n",
    "if HF_TOKEN.strip():\n",
    "    login(token=HF_TOKEN.strip())\n",
    "    os.environ[\"HF_TOKEN\"] = HF_TOKEN.strip()\n",
    "    print(\"✅ Hugging Face authentication complete!\")\n",
    "else:\n",
    "    print(\"ℹ️ No token provided. Public models (large-v3-turbo, small, tiny) will run directly!\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 4. Test GPU STT Inference on Sample Speech\n",
    "Benchmark Faster-Whisper on CUDA with greedy decoding (`temperature=0.0`) and anti-hallucination settings."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "import time\n",
    "import numpy as np\n",
    "from faster_whisper import WhisperModel\n",
    "\n",
    "# Default: Systran/faster-whisper-large-v3-turbo (highest accuracy, near-realtime on T4 GPU)\n",
    "MODEL_NAME = \"Systran/faster-whisper-large-v3-turbo\"  # @param [\"Systran/faster-whisper-large-v3-turbo\", \"Systran/faster-whisper-small\", \"Systran/faster-whisper-tiny\", \"kritix-ai/Swar-stt\"]\n",
    "\n",
    "print(f\"⏳ Loading model '{MODEL_NAME}' onto CUDA GPU with float16 precision...\")\n",
    "t0 = time.time()\n",
    "model = WhisperModel(MODEL_NAME, device=\"cuda\", compute_type=\"float16\")\n",
    "print(f\"✅ Model loaded in {time.time() - t0:.2f} seconds!\")\n",
    "\n",
    "# Benchmark 0.5s dummy audio with greedy anti-hallucination parameters\n",
    "dummy_audio = np.zeros(16000, dtype=np.float32)\n",
    "t_inf = time.time()\n",
    "segments, _ = model.transcribe(\n",
    "    dummy_audio,\n",
    "    beam_size=1,\n",
    "    temperature=0.0,\n",
    "    repetition_penalty=1.15,\n",
    "    without_timestamps=False,\n",
    "    hallucination_silence_threshold=1.5\n",
    ")\n",
    "list(segments)\n",
    "print(f\"⚡ CUDA Greedy Inference Warmup Latency: {(time.time() - t_inf)*1000:.1f} ms\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 5. In-Browser Microphone Recording & Live 4-Tier Grammar Polisher\n",
    "Speak into your laptop mic, click **Stop Recording**, and observe:\n",
    "1. **Raw Whisper Transcription** on Colab GPU.\n",
    "2. **Deterministic 4-Tier Grammar Polishing** (`TokenEngine` ➔ `SentenceEngine` ➔ `ParagraphEngine` ➔ `FinalEditor`)."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "from IPython.display import HTML, Javascript, display\n",
    "from google.colab import output\n",
    "import base64\n",
    "import io\n",
    "import soundfile as sf\n",
    "import librosa\n",
    "from Backend.kvie.grammar_router import GrammarRouter\n",
    "\n",
    "RECORD_HTML = \"\"\"\n",
    "<div style=\"font-family: sans-serif; padding: 18px; border: 1px solid #3f3f46; border-radius: 12px; background: #18181b; color: #f4f4f5; max-width: 500px;\">\n",
    "  <h3 style=\"margin-top: 0; color: #22c55e;\">🎙️ KVIE Colab Voice & Grammar Test</h3>\n",
    "  <p style=\"font-size: 13px; color: #a1a1aa;\">Record speech from your browser and polish through KVIE's multi-tier engine:</p>\n",
    "  <button id=\"rec-btn\" style=\"background: #22c55e; color: #000; font-weight: bold; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer;\">🔴 Start Recording</button>\n",
    "  <span id=\"status\" style=\"margin-left: 12px; font-size: 13px; color: #71717a;\">Idle</span>\n",
    "</div>\n",
    "<script>\n",
    "var mediaRecorder;\n",
    "var audioChunks = [];\n",
    "var recBtn = document.getElementById('rec-btn');\n",
    "var statusText = document.getElementById('status');\n",
    "\n",
    "recBtn.onclick = async () => {\n",
    "  if (!mediaRecorder || mediaRecorder.state === 'inactive') {\n",
    "    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });\n",
    "    mediaRecorder = new MediaRecorder(stream);\n",
    "    audioChunks = [];\n",
    "    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);\n",
    "    mediaRecorder.onstop = async () => {\n",
    "      statusText.innerText = 'Processing audio on GPU & routing grammar...';\n",
    "      const blob = new Blob(audioChunks, { type: 'audio/webm' });\n",
    "      const reader = new FileReader();\n",
    "      reader.readAsDataURL(blob);\n",
    "      reader.onloadend = () => {\n",
    "        google.colab.kernel.invokeFunction('notebook.transcribe_audio', [reader.result], {});\n",
    "      };\n",
    "    };\n",
    "    mediaRecorder.start();\n",
    "    recBtn.innerText = '⏹️ Stop Recording';\n",
    "    recBtn.style.background = '#f43f5e';\n",
    "    recBtn.style.color = '#fff';\n",
    "    statusText.innerText = 'Listening... Speak now!';\n",
    "  } else {\n",
    "    mediaRecorder.stop();\n",
    "    recBtn.innerText = '🔴 Start Recording';\n",
    "    recBtn.style.background = '#22c55e';\n",
    "    recBtn.style.color = '#000';\n",
    "  }\n",
    "};\n",
    "</script>\n",
    "\"\"\"\n",
    "\n",
    "def transcribe_audio_callback(base64_audio):\n",
    "    try:\n",
    "        header, encoded = base64_audio.split(\",\", 1)\n",
    "        data = base64.b64decode(encoded)\n",
    "        audio_file = io.BytesIO(data)\n",
    "        \n",
    "        # Load and resample to 16 kHz\n",
    "        samples, sr = librosa.load(audio_file, sr=16000, mono=True)\n",
    "        duration = len(samples) / 16000.0\n",
    "        \n",
    "        t_start = time.time()\n",
    "        segments, info = model.transcribe(\n",
    "            samples,\n",
    "            beam_size=1,\n",
    "            language=\"en\",\n",
    "            temperature=0.0,\n",
    "            repetition_penalty=1.15,\n",
    "            without_timestamps=False,\n",
    "            hallucination_silence_threshold=1.5\n",
    "        )\n",
    "        raw_text = \" \".join(s.text.strip() for s in segments).strip()\n",
    "        latency = (time.time() - t_start) * 1000\n",
    "        \n",
    "        # Polish with KVIE 4-Tier Grammar Engine\n",
    "        polished_text = GrammarRouter.route(raw_text)\n",
    "        \n",
    "        print(\"\\n\" + \"=\"*65)\n",
    "        print(f\"🎯 Transcribed ({duration:.1f}s audio in {latency:.0f} ms on CUDA GPU):\")\n",
    "        print(f\"📝 Raw Acoustic:     \\\"{raw_text}\\\"\")\n",
    "        print(f\"✨ Grammar Polished: \\\"{polished_text}\\\"\")\n",
    "        print(\"=\"*65 + \"\\n\")\n",
    "    except Exception as e:\n",
    "        print(f\"Error processing audio: {e}\")\n",
    "\n",
    "output.register_callback('notebook.transcribe_audio', transcribe_audio_callback)\n",
    "display(HTML(RECORD_HTML))"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 6. Launch Remote KVIE FastAPI Backend & Cloudflare Tunnel\n",
    "Run the cell below to launch the KVIE FastAPI backend on GPU port 8765 and create a public Cloudflare Tunnel.\n",
    "\n",
    "Then copy the generated URL into **Desktop KVIE ➔ Settings ➔ Backend Service & Remote GPU**!"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "import os\n",
    "import time\n",
    "import subprocess\n",
    "import requests\n",
    "from IPython.display import HTML, display\n",
    "\n",
    "# 1. Start KVIE FastAPI backend in background on port 8765\n",
    "env = os.environ.copy()\n",
    "env[\"KVIE_HOST\"] = \"0.0.0.0\"\n",
    "env[\"KVIE_PORT\"] = \"8765\"\n",
    "env[\"KVIE_ALLOWED_ORIGINS\"] = \"*\"\n",
    "\n",
    "server_process = subprocess.Popen(\n",
    "    [\"python\", \"-m\", \"Backend.kvie.service\"],\n",
    "    env=env,\n",
    "    stdout=subprocess.PIPE,\n",
    "    stderr=subprocess.STDOUT,\n",
    "    text=True\n",
    ")\n",
    "\n",
    "print(\"⏳ Starting KVIE FastAPI Service and warming up GPU...\")\n",
    "time.sleep(5)\n",
    "\n",
    "# Verify health endpoint\n",
    "telemetry = {}\n",
    "try:\n",
    "    resp = requests.get(\"http://127.0.0.1:8765/health\", timeout=5)\n",
    "    if resp.status_code == 200:\n",
    "        telemetry = resp.json()\n",
    "        print(\"✅ Backend Health Verified:\")\n",
    "        print(f\"   • Device: {telemetry.get('device_name', 'CUDA')}\")\n",
    "        print(f\"   • Model: {telemetry.get('model_name', 'large-v3-turbo')}\")\n",
    "        print(f\"   • Precision: {telemetry.get('compute_type', 'float16')}\")\n",
    "        if telemetry.get('vram_total_mb'):\n",
    "            print(f\"   • VRAM: {telemetry.get('vram_allocated_mb', 0):.0f} MB / {telemetry.get('vram_total_mb', 0):.0f} MB\")\n",
    "except Exception as e:\n",
    "    print(f\"ℹ️ Service starting: {e}\")\n",
    "\n",
    "# 2. Open Cloudflare Tunnel to expose port 8765 publicly\n",
    "print(\"\\n🌐 Opening public Cloudflare tunnel to port 8765...\")\n",
    "tunnel_proc = subprocess.Popen(\n",
    "    [\"cloudflared\", \"tunnel\", \"--url\", \"http://127.0.0.1:8765\"],\n",
    "    stdout=subprocess.PIPE,\n",
    "    stderr=subprocess.STDOUT,\n",
    "    text=True\n",
    ")\n",
    "\n",
    "public_url = None\n",
    "for line in tunnel_proc.stdout:\n",
    "    if \"trycloudflare.com\" in line:\n",
    "        for part in line.split():\n",
    "            if \"trycloudflare.com\" in part:\n",
    "                public_url = part.strip()\n",
    "                if not public_url.startswith(\"http\"):\n",
    "                    public_url = \"https://\" + public_url\n",
    "                break\n",
    "        if public_url:\n",
    "            break\n",
    "\n",
    "if public_url:\n",
    "    display(HTML(f\"\"\"\n",
    "    <div style=\"font-family: sans-serif; padding: 20px; border: 2px solid #22c55e; border-radius: 12px; background: #0f172a; color: #f8fafc; max-width: 650px; margin-top: 15px;\">\n",
    "      <h3 style=\"margin-top: 0; color: #22c55e; display: flex; align-items: center; gap: 8px;\">\n",
    "        🚀 Remote KVIE GPU Backend Active!\n",
    "      </h3>\n",
    "      <p style=\"color: #94a3b8; font-size: 14px; margin-bottom: 8px;\">Copy your public Cloudflare Tunnel URL below:</p>\n",
    "      <div style=\"background: #1e293b; padding: 12px; border-radius: 8px; font-family: monospace; font-size: 15px; color: #38bdf8; word-break: break-all; border: 1px solid #334155;\">\n",
    "        {public_url}\n",
    "      </div>\n",
    "      <h4 style=\"margin-top: 16px; margin-bottom: 8px; color: #f8fafc;\">📱 Connect Desktop KVIE in 3 Clicks:</h4>\n",
    "      <ol style=\"color: #cbd5e1; font-size: 13px; line-height: 1.6; padding-left: 20px; margin: 0;\">\n",
    "        <li>Open your Desktop KVIE App (installed via <code>KVIE_2.0.0_x64-setup.exe</code>)</li>\n",
    "        <li>Click <b>Settings</b> (⚙️) ➔ Scroll to <b>Backend Service & Remote GPU</b></li>\n",
    "        <li>Paste <code>{public_url}</code> into the URL field and click <b>Save Backend URL</b></li>\n",
    "      </ol>\n",
    "      <p style=\"margin-top: 12px; font-size: 12px; color: #64748b; margin-bottom: 0;\">Status badge will turn green showing live remote GPU VRAM telemetry!</p>\n",
    "    </div>\n",
    "    \"\"\"))\n",
    "else:\n",
    "    print(\"Tunnel started. Check output lines above for your trycloudflare.com URL.\")"
   ]
  }
 ],
 "metadata": {
  "accelerator": "GPU",
  "colab": {
   "gpuType": "T4",
   "provenance": []
  },
  "kernelspec": {
   "display_name": "Python 3",
   "name": "python3"
  },
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 0
}

with open(NOTEBOOK_PATH, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print(f"Updated {NOTEBOOK_PATH} successfully!")
