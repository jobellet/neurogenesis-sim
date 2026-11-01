"""Golden fixtures of the native kernel (desktop/common/fixtures): they are exactly what the Python reference gives
today, and the portable C kernel nglif (desktop/common/native/nglif) reproduces them bit for bit."""
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "desktop" / "common" / "fixtures"
NGLIF = ROOT / "desktop" / "common" / "native" / "nglif"


def load_generator():
    spec = importlib.util.spec_from_file_location("make_fixtures", FIXTURES / "make_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fixtures_follow_the_reference_kernel(tmp_path):
    load_generator().make(tmp_path, check_jax=False)
    committed = sorted(p.name for p in FIXTURES.iterdir() if p.is_file() and p.suffix != ".py" and p.name != "README.md")
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == committed
    for name in committed:
        assert (tmp_path / name).read_bytes() == (FIXTURES / name).read_bytes(), f"{name} differs: regenerate with make_fixtures.py"


def test_c_kernel_reproduces_the_fixtures(tmp_path):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("no C compiler (the nglif CI job builds it on Linux, macOS and Windows)")
    exe = tmp_path / "nglif_test"
    subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", str(NGLIF / "nglif.c"), str(NGLIF / "nglif_test.c"),
                    "-o", str(exe)], check=True)
    r = subprocess.run([str(exe), str(FIXTURES)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 failures" in r.stdout
