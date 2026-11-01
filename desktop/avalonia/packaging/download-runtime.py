#!/usr/bin/env python3
"""Downloads and unpacks relocatable Python 3.11 standalone runtime into target directory.

Usage:
    python download-runtime.py --platform [windows|linux] --output-dir <path>
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

# Astral python-build-standalone release
STANDALONE_RELEASE = "20241016"
URLS = {
    "windows": (
        f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_RELEASE}/"
        f"cpython-3.11.10+{STANDALONE_RELEASE}-x86_64-pc-windows-msvc-shared-install_only.tar.gz"
    ),
    "linux": (
        f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_RELEASE}/"
        f"cpython-3.11.10+{STANDALONE_RELEASE}-x86_64-unknown-linux-gnu-install_only.tar.gz"
    ),
}

def download_and_extract(target_platform: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    url = URLS[target_platform]
    archive_name = os.path.basename(url)
    archive_path = os.path.join(output_dir, archive_name)

    print(f"Downloading Python 3.11 standalone for {target_platform}...")
    print(f"URL: {url}")
    urllib.request.urlretrieve(url, archive_path)

    print("Extracting archive...")
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(output_dir)

    os.remove(archive_path)
    python_dir = os.path.join(output_dir, "python")
    print(f"Extracted to {python_dir}")
    return python_dir

def install_dependencies(python_dir: str, target_platform: str, repo_root: str):
    if target_platform == "windows":
        py_exe = os.path.join(python_dir, "python.exe")
    else:
        py_exe = os.path.join(python_dir, "bin", "python3")

    if not os.path.exists(py_exe):
        print(f"Warning: {py_exe} does not exist yet (cross-target provision). Skipping pip install.")
        return

    print("Installing dependencies into embedded Python environment...")
    subprocess.check_call([py_exe, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([py_exe, "-m", "pip", "install", "numpy", "matplotlib"])
    
    # Install neurogenesis in editable or wheel mode
    subprocess.check_call([py_exe, "-m", "pip", "install", "--no-deps", "-e", repo_root])
    print("Embedded Python environment ready.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["windows", "linux"], default="windows" if os.name == "nt" else "linux")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo-root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
    args = parser.parse_args()

    python_dir = download_and_extract(args.platform, args.output_dir)
    # Only run pip if running natively for this platform
    current_os = "windows" if os.name == "nt" else "linux"
    if args.platform == current_os:
        install_dependencies(python_dir, args.platform, args.repo_root)

if __name__ == "__main__":
    main()
