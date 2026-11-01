"""The desktop app's native lif_int kernel (Sources/LIFKernel.swift) gives the same spikes as the Python reference and
the JAX kernel, through the NGB1 exchange format of the bridge.

    JAX_PLATFORMS=cpu pytest -q "desktop app/Mac/tests"        (macOS with the Swift toolchain; builds the harness once)
"""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

MAC = Path(__file__).resolve().parents[1]
REPO = MAC.parents[1]
sys.path.insert(0, str(REPO))
CLI = MAC / "build" / "kernel_cli"

spec = importlib.util.spec_from_file_location("ngbridge", MAC / "backend" / "ngbridge.py")
ngbridge = importlib.util.module_from_spec(spec)
_stdout = sys.stdout
spec.loader.exec_module(ngbridge)
sys.stdout = _stdout

from neurogenesis.spiking.morphology import MorphogeneticEngine  # noqa: E402
from neurogenesis.spiking.reference import IntegerSNNSimulator  # noqa: E402


@pytest.fixture(scope="module")
def cli():
    if shutil.which("swiftc") is None:
        pytest.skip("needs the Swift toolchain (macOS)")
    src = [MAC / "Sources" / "Network.swift", MAC / "Sources" / "LIFKernel.swift", MAC / "tools" / "kernel_cli" / "main.swift"]
    CLI.parent.mkdir(exist_ok=True)
    if not CLI.exists() or any(s.stat().st_mtime > CLI.stat().st_mtime for s in src):
        subprocess.run(["swiftc", "-O", "-swift-version", "5", *map(str, src), "-o", str(CLI)], check=True)
    return CLI


def native_spikes(cli, net, ticks, tmp_path, ext=None):
    f = tmp_path / "net.ngb"
    ngbridge.write_network(net, f)
    args = [str(cli), str(f), str(ticks)]
    if ext is not None:
        (tmp_path / "ext.bin").write_bytes(np.asarray(ext, "<i4").tobytes())
        args.append(str(tmp_path / "ext.bin"))
    out = subprocess.run(args, check=True, capture_output=True, text=True).stdout.split()
    return [(int(t), int(i)) for t, i in zip(out[::2], out[1::2])]


@pytest.mark.parametrize("make", [
    lambda: MorphogeneticEngine.generate_cortical_column(300, seed=1),
    lambda: MorphogeneticEngine.generate_cortical_column(300, seed=2, weight_scale=0.2, refractory=3),
    lambda: MorphogeneticEngine.generate_microcircuit(100, seed=3),
    lambda: MorphogeneticEngine.generate_layered_network(200, seed=4),
])
def test_native_kernel_matches_reference(cli, tmp_path, make):
    net = make()
    sim = IntegerSNNSimulator(net)
    sim.run(300)
    assert native_spikes(cli, net, 300, tmp_path) == sim.spike_history
    assert len(sim.spike_history) > 0


def test_native_kernel_matches_jax_with_external_current(cli, tmp_path):
    from neurogenesis.spiking import jax_backend
    net = MorphogeneticEngine.generate_cortical_column(200, seed=5, weight_scale=0.2, refractory=3)
    ext = np.zeros(net.num_neurons, np.int32)
    ext[::7] = 40
    a = jax_backend.pack(net)
    st = jax_backend.init_state(a, 12345)
    ref = []
    for t in range(200):
        st, spk, _ = jax_backend.tick(a, st, ext)
        ref += [(t, int(i)) for i in np.nonzero(np.asarray(spk))[0]]
    assert native_spikes(cli, net, 200, tmp_path, ext) == ref


def test_ngb_round_trip_keeps_every_field(tmp_path):
    net = MorphogeneticEngine.generate_cortical_column(50, seed=6)
    f = tmp_path / "n.ngb"
    ngbridge.write_network(net, f)
    back = ngbridge.read_network(f)
    assert [vars(n) for n in back.neurons] == [vars(n) for n in net.neurons]
    assert [vars(s) for s in back.synapses] == [vars(s) for s in net.synapses]
