"""The embedded-runtime builder (desktop/common/runtime/build_runtime.py), without network: archive choice from a
release's SHA256SUMS, targets, pruning. CI builds real runtimes in the Release workflow."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "desktop" / "common" / "runtime" / "build_runtime.py"


@pytest.fixture()
def br(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_runtime", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "CACHE", tmp_path)
    return mod


def test_archive_is_chosen_by_triple_and_minor_version(br, tmp_path):
    (tmp_path / "R").mkdir()
    (tmp_path / "R" / "SHA256SUMS").write_text(
        "aa  cpython-3.12.15+R-x86_64-apple-darwin-install_only.tar.gz\n"
        "bb  cpython-3.12.15+R-x86_64-apple-darwin-install_only_stripped.tar.gz\n"
        "cc  cpython-3.13.9+R-x86_64-apple-darwin-install_only_stripped.tar.gz\n"
        "dd  cpython-3.12.15+R-aarch64-apple-darwin-install_only_stripped.tar.gz\n")
    assert br.locate_archive("x86_64-apple-darwin", "R", "3.12") == ("cpython-3.12.15+R-x86_64-apple-darwin-install_only_stripped.tar.gz", "bb")
    assert br.locate_archive("aarch64-apple-darwin", "R", "3.12")[1] == "dd"
    with pytest.raises(SystemExit):
        br.locate_archive("x86_64-pc-windows-msvc", "R", "3.12")


def test_targets_cover_the_three_apps(br):
    assert set(br.TARGETS) == {"macos-x86_64", "macos-arm64", "linux-x86_64", "linux-arm64", "windows-x86_64"}
    assert br.host_target() in br.TARGETS or br.host_target().split("-")[0] not in ("macos", "linux", "windows")
    assert br.RELEASE.isdigit() and len(br.RELEASE) == 8          # pinned python-build-standalone release


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
