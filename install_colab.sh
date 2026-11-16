#!/usr/bin/env bash
# KVIE Colab GPU One-Click Installer
# Run in Google Colab: !bash install_colab.sh

set -e

echo "============================================================"
echo "🚀 Installing KVIE GPU Backend & Dependencies on Google Colab"
echo "============================================================"

# 1. System packages if needed
if command -v apt-get &> /dev/null; then
    echo "📦 Checking system libraries..."
    apt-get update -qq > /dev/null 2>&1 || true
    apt-get install -y -qq libsndfile1 ffmpeg > /dev/null 2>&1 || true
fi

# 2. Run Python installer
python3 setup_colab.py

echo ""
echo "✅ Setup complete! You are ready to run inference or launch the remote tunnel."
