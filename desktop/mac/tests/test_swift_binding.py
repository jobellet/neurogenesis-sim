"""The Mac app's binding to the shared C kernel: fixtures read with the app's NGB1 reader and run through NativeSim
(Sources/SimEngine.swift) give the golden spikes of desktop/common/fixtures.

    pytest -q desktop/mac/tests          (macOS with the Swift toolchain)
"""
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

MAC = Path(__file__).resolve().parents[1]
COMMON = MAC.parent / "common"


@pytest.mark.skipif(platform.system() != "Darwin" or shutil.which("swiftc") is None, reason="needs macOS and swiftc")
def test_native_sim_reproduces_the_golden_fixtures(tmp_path):
    nglif = COMMON / "native" / "nglif"
    obj = tmp_path / "nglif.o"
    subprocess.run(["clang", "-std=c11", "-O2", "-c", str(nglif / "nglif.c"), "-o", str(obj)], check=True)
    exe = tmp_path / "native_check"
    subprocess.run(["swiftc", "-O", "-swift-version", "5", "-I", str(nglif), str(obj), str(MAC / "Sources" / "Network.swift"),
                    str(MAC / "Sources" / "SimEngine.swift"), str(MAC / "tools" / "native_check" / "main.swift"), "-o", str(exe)],
                   check=True)
    r = subprocess.run([str(exe), str(COMMON / "fixtures")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
