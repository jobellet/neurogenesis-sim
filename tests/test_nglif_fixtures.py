"""Golden fixtures of the native kernel (desktop/common/fixtures): they are exactly what the Python reference gives
today, and the portable C kernel nglif (desktop/common/native/nglif) reproduces them bit for bit."""
import importlib.util
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "desktop" / "common" / "fixtures"
NGLIF = ROOT / "desktop" / "common" / "native" / "nglif"


def load_generator():
    spec = importlib.util.spec_from_file_location("make_fixtures", FIXTURES / "make_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _assert_fixture_equal(actual: Path, expected: Path):
    if actual.suffix == ".ngb":
        from neurogenesis.bridge.ngb import read_extensions, read_network
        net1, net2 = read_network(actual), read_network(expected)
        assert len(net1.neurons) == len(net2.neurons)
        assert len(net1.synapses) == len(net2.synapses)
        for n1, n2 in zip(net1.neurons, net2.neurons):
            assert (n1.mode, n1.shift_v, n1.shift_s, n1.base_weight, n1.burst_period, n1.burst_duty,
                    n1.refractory, n1.role, n1.compartment, n1.threshold) == (
                   n2.mode, n2.shift_v, n2.shift_s, n2.base_weight, n2.burst_period, n2.burst_duty,
                   n2.refractory, n2.role, n2.compartment, n2.threshold)
            assert math.isclose(n1.x, n2.x, abs_tol=1e-7) and math.isclose(n1.y, n2.y, abs_tol=1e-7) and math.isclose(n1.z, n2.z, abs_tol=1e-7)
            assert math.isclose(n1.dir_x, n2.dir_x, abs_tol=1e-7) and math.isclose(n1.dir_y, n2.dir_y, abs_tol=1e-7) and math.isclose(n1.dir_z, n2.dir_z, abs_tol=1e-7)
            assert math.isclose(n1.poisson_hz, n2.poisson_hz, abs_tol=1e-7)
        for s1, s2 in zip(net1.synapses, net2.synapses):
            assert (s1.pre, s1.post, s1.weight, s1.delay) == (s2.pre, s2.post, s2.weight, s2.delay)
        ext1, ext2 = read_extensions(actual), read_extensions(expected)
        assert set(ext1.keys()) == set(ext2.keys())
        for k in ext1:
            ax1, arr1 = ext1[k]
            ax2, arr2 = ext2[k]
            assert ax1 == ax2
            np.testing.assert_allclose(arr1, arr2, atol=1e-7)
    else:
        assert actual.read_bytes() == expected.read_bytes(), f"{actual.name} differs: regenerate with make_fixtures.py"


def test_fixtures_follow_the_reference_kernel(tmp_path):
    load_generator().make(tmp_path, check_jax=False)
    committed = sorted(p.name for p in FIXTURES.iterdir() if p.is_file() and p.suffix != ".py" and p.name != "README.md")
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == committed
    for name in committed:
        _assert_fixture_equal(tmp_path / name, FIXTURES / name)


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
