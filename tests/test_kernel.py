"""Spiking kernel: network generation, JSON round trip, CSR, determinism; the JAX and browser kernels equal the reference bit for bit."""
import numpy as np
import pytest

from neurogenesis.spiking import SNNNetwork
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.reference import IntegerSNNSimulator


def test_round_trip_and_csr(tmp_path):
    net = MorphogeneticEngine.generate_microcircuit(60, seed=1)
    net.save_json(tmp_path / "n.json")
    net2 = SNNNetwork.load_json(tmp_path / "n.json")
    assert net2.num_neurons == 60 and net2.num_synapses == net.num_synapses
    row_ptr, col, w, d = net2.to_csr()
    assert row_ptr[-1] == net.num_synapses and np.all(d >= 1) and np.all(d <= 31)


def test_simulation_is_deterministic():
    net = MorphogeneticEngine.generate_cortical_column(80, seed=3)
    a = IntegerSNNSimulator(net, seed=7).run(200)
    b = IntegerSNNSimulator(net, seed=7).run(200)
    assert a["spikes_per_tick"] == b["spikes_per_tick"]


def test_poisson_threshold_does_not_overflow():
    net = MorphogeneticEngine.generate_microcircuit(10, seed=0)
    net.neurons[0].mode, net.neurons[0].poisson_hz = 1, 2000.0
    sim = IntegerSNNSimulator(net)
    assert int(sim.poisson_thresh[0]) == 4294967295


def test_csr_handles_many_neurons():
    net = SNNNetwork(neurons=[MorphogeneticEngine.generate_microcircuit(1, seed=0).neurons[0]] * 65536)
    # Shouldn't raise ValueError anymore
    row_ptr, col, w, d = net.to_csr()
    assert len(row_ptr) == 65537
    assert row_ptr.dtype == np.uint32
    assert col.dtype == np.uint32


# ---------------------------------------------------------------- refractory period and JAX port
import jax  # noqa: E402

from neurogenesis.spiking import jax_backend as jax_sim  # noqa: E402


def _reference_raster(net, seed, ticks):
    sim = IntegerSNNSimulator(net, seed=seed)
    sim.run(ticks)
    r = np.zeros((ticks, net.num_neurons), np.uint8)
    for t, i in sim.spike_history:
        r[t, i] = 1
    return r


@pytest.mark.parametrize("gen,kw", [("generate_microcircuit", dict(num_neurons=60)),
                                    ("generate_cortical_column", dict(num_neurons=150)),
                                    ("generate_cortical_column", dict(num_neurons=150, weight_scale=0.25, inh_scale=2.0, refractory=3)),
                                    ("generate_layered_network", dict(num_neurons=120))])
def test_jax_kernel_bit_identical(gen, kw):
    net = getattr(MorphogeneticEngine, gen)(seed=5, **kw)
    ref = _reference_raster(net, 99, 300)
    n_pois = sum(x.mode == 1 for x in net.neurons)
    packed = jax_sim.pack(net, n_pad=net.num_neurons + 7, e_pad=net.num_synapses + 13, p_pad=n_pois + 3)  # padding must not matter
    _, spk = jax.jit(lambda: jax_sim.run(packed, jax_sim.init_state(packed, 99), 300))()
    assert np.array_equal(np.asarray(spk)[:, :net.num_neurons], ref)
    assert ref.sum() > 0


def test_refractory_blocks_firing():
    net = MorphogeneticEngine.generate_cortical_column(100, seed=2, refractory=5)
    r = _reference_raster(net, 1, 400)
    for i in range(net.num_neurons):
        t = np.nonzero(r[:, i])[0]
        if len(t) > 1:
            assert np.diff(t).min() >= 6
    assert np.array_equal(_reference_raster(MorphogeneticEngine.generate_cortical_column(100, seed=2), 1, 50),
                          _reference_raster(MorphogeneticEngine.generate_cortical_column(100, seed=2, refractory=0), 1, 50))


def test_browser_kernel_matches_python(tmp_path):
    """viz/src/sim/kernel.ts (compiled to scripts/js/build) gives the same spikes as the Python reference (needs node)."""
    import shutil
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if shutil.which("node") is None or not (root / "scripts/js/build/kernel.js").exists():
        pytest.skip("node or the compiled kernel (npx tsc, see scripts/js/check_kernel_equivalence.mjs) not available")
    net = MorphogeneticEngine.generate_cortical_column(150, seed=8, weight_scale=0.2, refractory=3)
    f = tmp_path / "n.json"
    net.save_json(f)
    sim = IntegerSNNSimulator(SNNNetwork.load_json(f))
    sim.run(300)
    py = "\n".join(f"{t} {i}" for t, i in sim.spike_history)
    js = subprocess.run(["node", str(root / "scripts/js/check_kernel_equivalence.mjs"), str(f), "300"],
                        capture_output=True, text=True, cwd=root).stdout.strip()
    assert py == js


def _heterogeneous(seed=11):
    net = MorphogeneticEngine.generate_cortical_column(150, seed=seed, weight_scale=0.25, refractory=3)
    rng = np.random.default_rng(seed)
    for n in net.neurons:
        n.threshold = int(rng.integers(500, 1900))
    for n in net.neurons[:6]:
        n.mode, n.burst_period, n.burst_duty = 2, int(rng.integers(30, 90)), 12
    return net


def test_per_neuron_threshold_jax_equals_reference():
    net = _heterogeneous()
    ref = _reference_raster(net, 7, 300)
    packed = jax_sim.pack(net, n_pad=net.num_neurons + 9, e_pad=net.num_synapses + 5, p_pad=sum(x.mode == 1 for x in net.neurons) + 2)
    _, spk = jax.jit(lambda: jax_sim.run(packed, jax_sim.init_state(packed, 7), 300))()
    assert np.array_equal(np.asarray(spk)[:, :net.num_neurons], ref) and ref.sum() > 0
    default = MorphogeneticEngine.generate_cortical_column(100, seed=2)
    assert all(n.threshold == 1024 for n in default.neurons)


def test_per_neuron_threshold_browser_equals_reference(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if shutil.which("node") is None or not (root / "scripts/js/build/kernel.js").exists():
        pytest.skip("node or the compiled kernel not available")
    net = _heterogeneous(12)
    f = tmp_path / "n.json"
    net.save_json(f)
    sim = IntegerSNNSimulator(SNNNetwork.load_json(f))
    sim.run(300)
    py = "\n".join(f"{t} {i}" for t, i in sim.spike_history)
    js = subprocess.run(["node", str(root / "scripts/js/check_kernel_equivalence.mjs"), str(f), "300"], capture_output=True, text=True, cwd=root).stdout.strip()
    assert py == js and len(py) > 0


def test_long_delays(tmp_path):
    """Test that max_delay > 31 correctly triggers W > 1 and multi-word bitshifts and propagation."""
    import shutil
    import subprocess
    from pathlib import Path
    import platform
    import ctypes
    
    net = MorphogeneticEngine.generate_microcircuit(20, seed=42)
    rng = np.random.default_rng(42)
    for s in net.synapses:
        s.delay = int(rng.integers(1, 150))
        
    # Check Python Reference
    sim = IntegerSNNSimulator(net, seed=42)
    sim.run(200)
    ref = np.zeros((200, net.num_neurons), np.uint8)
    for t, i in sim.spike_history:
        ref[t, i] = 1
        
    # Check JAX backend
    packed = jax_sim.pack(net)
    _, spk = jax.jit(lambda: jax_sim.run(packed, jax_sim.init_state(packed, 42), 200))()
    assert np.array_equal(np.asarray(spk)[:, :net.num_neurons], ref)
    assert ref.sum() > 0
    
    # Check Browser kernel
    root = Path(__file__).resolve().parents[1]
    if shutil.which("node") is not None and (root / "scripts/js/build/kernel.js").exists():
        f = tmp_path / "n.json"
        net.save_json(f)
        py = "\n".join(f"{t} {i}" for t, i in sim.spike_history)
        # Note JS kernel defaults to 12345, so we need to run reference with seed 12345 to compare JS
        sim2 = IntegerSNNSimulator(net, seed=12345)
        sim2.run(200)
        py2 = "\n".join(f"{t} {i}" for t, i in sim2.spike_history)
        js = subprocess.run(["node", str(root / "scripts/js/check_kernel_equivalence.mjs"), str(f), "200"], capture_output=True, text=True, cwd=root).stdout.strip()
        assert py2 == js and len(py2) > 0

    # Check C nglif kernel
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is not None:
        from neurogenesis.bridge.ngb import write_network
        nglif_dir = root / "desktop" / "common" / "native" / "nglif"
        fix_dir = tmp_path / "nglif_long"
        fix_dir.mkdir(exist_ok=True)
        write_network(net, fix_dir / "long_delays.ngb")
        spikes_arr = np.asarray(sim.spike_history, dtype="<i4").reshape(-1)
        (fix_dir / "long_delays.spikes.i32").write_bytes(spikes_arr.tobytes())
        (fix_dir / "MANIFEST.txt").write_text("long_delays 200 42 -\n")
        exe = tmp_path / "nglif_test_long"
        subprocess.run([cc, "-std=c11", "-O2", str(nglif_dir / "nglif.c"), str(nglif_dir / "nglif_test.c"), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe), str(fix_dir)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0 failures" in r.stdout

