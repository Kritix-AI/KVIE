#!/usr/bin/env python3
"""
KVIE Colab Bundle Packager
Packages the updated KVIE backend, grammar engine, dependencies, and Colab setup scripts
into dist_colab/kvie_backend_update.zip for seamless deployment to Google Colab GPU.
"""

import os
import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist_colab"
BUNDLE_PATH = DIST_DIR / "kvie_backend_update.zip"

INCLUDED_PATHS = [
    "Backend",
    "requirements.txt",
    "install_colab.sh",
    "setup_colab.py",
]

EXCLUDED_EXTENSIONS = {".pyc", ".pyo", ".pyd"}
EXCLUDED_DIRS = {"__pycache__", ".git", ".pytest_cache", "venv", ".venv"}


def package_bundle():
    print(f"📦 Packaging KVIE Backend for Google Colab GPU...")
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    file_count = 0
    with zipfile.ZipFile(BUNDLE_PATH, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in INCLUDED_PATHS:
            item_path = ROOT_DIR / item
            if not item_path.exists():
                print(f"⚠️ Warning: {item_path} not found, skipping...")
                continue

            if item_path.is_file():
                zip_file.write(item_path, arcname=item)
                file_count += 1
                print(f"  + Added file: {item}")
            elif item_path.is_dir():
                for root, dirs, files in os.walk(item_path):
                    # Filter out excluded directories
                    dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                    for file in files:
                        file_path = Path(root) / file
                        if file_path.suffix in EXCLUDED_EXTENSIONS:
                            continue
                        rel_path = file_path.relative_to(ROOT_DIR)
                        zip_file.write(file_path, arcname=str(rel_path).replace("\\", "/"))
                        file_count += 1

    bundle_size_kb = BUNDLE_PATH.stat().st_size / 1024
    print(f"\n✅ Packaged {file_count} files into '{BUNDLE_PATH}' ({bundle_size_kb:.1f} KB)")
    print(f"👉 You can upload this zip file directly into Google Colab or let install_colab.sh handle it!")


if __name__ == "__main__":
    package_bundle()
