"""The embedded-runtime builder (desktop/common/runtime/build_runtime.py), without network: committed pins and locks,
archive choice, pruning, and the macOS thinning of universal binaries. CI builds real runtimes (Release workflow)."""
import importlib.util
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "desktop" / "common" / "runtime"


@pytest.fixture()
def br(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_runtime", RUNTIME / "build_runtime.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "CACHE", tmp_path)
    return mod


def test_every_target_has_a_committed_cpython_hash(br):
    pins = json.loads((RUNTIME / "pins.json").read_text())
    assert pins["release"] == br.RELEASE and pins["python"] == br.PYTHON
    assert set(pins["archives"]) == set(br.TARGETS)
    for target, a in pins["archives"].items():
        assert re.fullmatch(r"[0-9a-f]{64}", a["sha256"])
        assert f"+{br.RELEASE}-{br.TARGETS[target][0]}-install_only_stripped.tar.gz" in a["name"]
        assert a["name"].startswith(f"cpython-{br.PYTHON}.")


def test_every_target_is_locked_with_hashes_and_the_same_packages(br):
    sets = {}
    for target in br.TARGETS:
        lines = [l for l in (RUNTIME / "locks" / f"{target}.txt").read_text().splitlines() if l and not l.startswith("#")]
        assert lines and all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[^ ]+ --hash=sha256:[0-9a-f]{64}", l) for l in lines), target
        sets[target] = {l.split(" ")[0] for l in lines}
    first = next(iter(sets.values()))
    assert all(s == first for s in sets.values()), "every app must run the same package versions"
    assert {"jax==0.4.38", "jaxlib==0.4.38"} <= first and any(p.startswith("numpy==") for p in first)


def test_archive_is_chosen_by_triple_and_minor_version(br, tmp_path):
    (tmp_path / "R").mkdir()
    (tmp_path / "R" / "SHA256SUMS").write_text(
        "aa  cpython-3.12.15+R-x86_64-apple-darwin-install_only.tar.gz\n"
        "bb  cpython-3.12.15+R-x86_64-apple-darwin-install_only_stripped.tar.gz\n"
        "cc  cpython-3.13.9+R-x86_64-apple-darwin-install_only_stripped.tar.gz\n"
        "dd  cpython-3.12.15+R-aarch64-apple-darwin-install_only_stripped.tar.gz\n")
    assert br.archive_from_sums("x86_64-apple-darwin", "R", "3.12") == ("cpython-3.12.15+R-x86_64-apple-darwin-install_only_stripped.tar.gz", "bb")
    assert br.archive_from_sums("aarch64-apple-darwin", "R", "3.12")[1] == "dd"
    with pytest.raises(SystemExit):
        br.archive_from_sums("x86_64-pc-windows-msvc", "R", "3.12")


def test_prune_removes_package_tests_only(br, tmp_path):
    root = tmp_path / "python"
    for d in ("lib/python3.12/site-packages/numpy/tests", "lib/python3.12/site-packages/numpy/testing",
              "lib/python3.12/site-packages/jax/__pycache__", "lib/python3.12/test", "lib/python3.12/json"):
        (root / d).mkdir(parents=True)
        (root / d / "x.py").write_text("")
    br.prune(root)
    left = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_dir()}
    assert "lib/python3.12/site-packages/numpy/testing" in left and "lib/python3.12/json" in left
    assert not {"lib/python3.12/site-packages/numpy/tests", "lib/python3.12/site-packages/jax/__pycache__", "lib/python3.12/test"} & left


@pytest.mark.skipif(platform.system() != "Darwin" or not shutil.which("clang"), reason="macOS tools (lipo, codesign)")
def test_universal_binaries_are_thinned_and_resigned(br, tmp_path):
    src = tmp_path / "f.c"
    src.write_text("int f(void) { return 1; }\n")
    lib = tmp_path / "python" / "lib" / "python3.12" / "site-packages" / "pkg" / "_ext.so"
    lib.parent.mkdir(parents=True)
    subprocess.run(["clang", "-shared", "-arch", "x86_64", "-arch", "arm64", str(src), "-o", str(lib)], check=True)
    assert sorted(subprocess.run(["lipo", "-archs", str(lib)], capture_output=True, text=True).stdout.split()) == ["arm64", "x86_64"]
    br.thin_and_strip_macos(tmp_path / "python", "arm64")
    assert subprocess.run(["lipo", "-archs", str(lib)], capture_output=True, text=True).stdout.split() == ["arm64"]
    subprocess.run(["codesign", "--verify", str(lib)], check=True)
