"""Tests for F5: Kernel delay limits (delay in [1, 31]), clipping warnings, and index validation."""
import warnings
import numpy as np
import pytest

from neurogenesis.stages.base import Stage
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.params import Const


def test_grow_axons_clips_delays_to_31_and_warns():
    """grow_axons on distant populations must clip delay to 31 and warn with count."""
    tissue = Tissue.empty()
    # Source at origin (x=0), Target far away (x=100)
    tissue.add_cells(5, positions=np.array([[0, 0, 0]] * 5), region=np.zeros(5, dtype=int))
    tissue.add_cells(5, positions=np.array([[100, 0, 0]] * 5), region=np.ones(5, dtype=int))

    guidance = {
        "0->1": {
            "B": np.eye(3).tolist(),
            "c": [0, 0, 0],
            "sigma": 0.5,
            "p0": 1.0,
            "w": 50
        }
    }

    stage = Stage(
        name="grow",
        operator="grow_axons",
        params={
            "projections": Const(["0->1"]),
            "guidance": Const(guidance),
            "conduction_velocity": Const(1.0),  # Distance 100 / cv 1.0 = raw delay 100 > 31
            "max_delay": Const(31),  # user-set limit: clips and warns
        }
    )

    with pytest.warns(UserWarning, match="clipped to maximum delay 31 ticks") as record:
        t_out = stage.run(tissue, {}, {}, np.random.default_rng(42))

    assert len(record) == 1
    assert len(t_out.connectivity.delay) > 0
    # Every delay must be clipped to <= 31
    assert np.all(t_out.connectivity.delay <= 31)
    assert np.all(t_out.connectivity.delay >= 1)
    assert np.all(t_out.connectivity.delay == 31)


def test_myelinate_clips_delays_and_warns_if_exceeding_31():
    """myelinate clips delays to [1, 31] and warns if any unclipped delay > 31."""
    tissue = Tissue.empty()
    tissue.add_cells(4)
    # Delays of 20 ticks
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0, 1], dtype=np.int32),
        post=np.array([2, 3], dtype=np.int32),
        weight=np.array([100, 100], dtype=np.int32),
        delay=np.array([20, 25], dtype=np.int32)
    )

    # Factor 2.0 scales 20 -> 40 and 25 -> 50 (both > 31)
    stage = Stage(name="myelinate_up", operator="myelinate", params={"factor": Const(2.0), "max_delay": Const(31)})
    with pytest.warns(UserWarning, match="myelinate: 2 synapses clipped to maximum delay 31"):
        t_out = stage.run(tissue, {}, {}, np.random.default_rng(0))

    assert np.all(t_out.connectivity.delay == 31)

    # Factor 0.05 scales 31 -> 1.55 -> rounds to 2 >= 1
    stage_down = Stage(name="myelinate_down", operator="myelinate", params={"factor": Const(0.01)})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        t_down = stage_down.run(t_out, {}, {}, np.random.default_rng(0))
    assert np.all(t_down.connectivity.delay >= 1)


def test_connect_by_hand_validates_indices_and_delays():
    """connect_by_hand must reject pre/post >= N or < 0 and delay outside [1, 31]."""
    tissue = Tissue.empty()
    tissue.add_cells(10)  # N = 10, valid indices [0, 9]

    # Valid connection works
    stage_valid = Stage(
        name="valid",
        operator="connect_by_hand",
        params={"pre": Const([0, 5]), "post": Const([1, 9]), "delay": Const(15), "weight": Const(50)}
    )
    t = stage_valid.run(tissue, {}, {}, np.random.default_rng(0))
    assert len(t.connectivity.pre) == 2

    # Reject out-of-bounds pre >= N
    stage_bad_pre = Stage(name="bad_pre", operator="connect_by_hand", params={"pre": Const([10]), "post": Const([1])})
    with pytest.raises(ValueError, match="pre index out of range"):
        stage_bad_pre.run(t, {}, {}, np.random.default_rng(0))

    # Reject negative pre
    stage_neg_pre = Stage(name="neg_pre", operator="connect_by_hand", params={"pre": Const([-1]), "post": Const([1])})
    with pytest.raises(ValueError, match="pre index out of range"):
        stage_neg_pre.run(t, {}, {}, np.random.default_rng(0))

    # Reject out-of-bounds post >= N
    stage_bad_post = Stage(name="bad_post", operator="connect_by_hand", params={"pre": Const([0]), "post": Const([15])})
    with pytest.raises(ValueError, match="post index out of range"):
        stage_bad_post.run(t, {}, {}, np.random.default_rng(0))

    # Reject delay > 31
    stage_delay_high = Stage(
        name="delay_high",
        operator="connect_by_hand",
        params={"pre": Const([0]), "post": Const([1]), "delay": Const(256)}
    )
    with pytest.raises(ValueError, match="delay out of kernel limit"):
        stage_delay_high.run(t, {}, {}, np.random.default_rng(0))

    # Reject delay < 1 (e.g. 0)
    stage_delay_zero = Stage(
        name="delay_zero",
        operator="connect_by_hand",
        params={"pre": Const([0]), "post": Const([1]), "delay": Const(0)}
    )
    with pytest.raises(ValueError, match="delay out of kernel limit"):
        stage_delay_zero.run(t, {}, {}, np.random.default_rng(0))


def test_long_projection_keeps_distance_delay_and_default_does_not_warn():
    """Default max_delay is unlimited (storage bound 255): a 100-tick projection keeps its delay, silently."""
    tissue = Tissue.empty()
    tissue.add_cells(5, positions=np.array([[0, 0, 0]] * 5), region=np.zeros(5, dtype=int))
    tissue.add_cells(5, positions=np.array([[100, 0, 0]] * 5), region=np.ones(5, dtype=int))
    guidance = {"0->1": {"B": np.eye(3).tolist(), "c": [0, 0, 0], "sigma": 0.5, "p0": 1.0, "w": 50}}
    stage = Stage(name="grow", operator="grow_axons",
                  params={"projections": Const(["0->1"]), "guidance": Const(guidance), "conduction_velocity": Const(1.0)})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        t = stage.run(tissue, {}, {}, np.random.default_rng(42))
    assert len(t.connectivity.delay) > 0 and np.all(t.connectivity.delay == 100)
    # myelinate, connect_by_hand and the dendritic stage keep long delays too
    stage_m = Stage(name="m", operator="myelinate", params={"factor": Const(2.0)})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        t = stage_m.run(t, {}, {}, np.random.default_rng(0))
    assert np.all(t.connectivity.delay == 200)
    t2 = Tissue.empty(); t2.add_cells(2)
    Stage(name="c", operator="connect_by_hand",
          params={"pre": Const([0]), "post": Const([1]), "delay": Const(200), "weight": Const(50)}).run(t2, {}, {}, np.random.default_rng(0))
    assert t2.connectivity.delay[0] == 200


def test_long_grown_projection_simulates_identically_in_all_kernels(tmp_path):
    """A grown projection with delays > 31 gives identical spikes in Python, JAX, the browser kernel and nglif."""
    import shutil, subprocess
    from pathlib import Path
    import jax
    from neurogenesis.spiking.reference import IntegerSNNSimulator
    from neurogenesis.spiking import jax_backend as jax_sim
    tissue = Tissue.empty()
    rng = np.random.default_rng(3)
    tissue.add_cells(20, positions=rng.uniform(0, 1, (20, 3)) * [1, 1, 1], region=np.zeros(20, dtype=int))
    tissue.add_cells(20, positions=rng.uniform(0, 1, (20, 3)) * [1, 1, 1] + [60, 0, 0], region=np.ones(20, dtype=int))
    tissue.add_cells(20, positions=rng.uniform(0, 1, (20, 3)) * [1, 1, 1] + [120, 0, 0], region=np.full(20, 2))
    gd = lambda w: {"B": np.eye(3).tolist(), "c": [0, 0, 0], "sigma": 1e3, "p0": 0.6, "w": w}
    t = Stage(name="g", operator="grow_axons", params={
        "projections": Const(["0->1", "1->2", "2->0"]),
        "guidance": Const({"0->1": gd(900), "1->2": gd(900), "2->0": gd(900)}),
        "conduction_velocity": Const(1.0)}).run(tissue, {}, {}, np.random.default_rng(5))
    d = t.connectivity.delay
    assert d.max() > 100 and d.min() > 31
    net = t.to_network()
    for n in net.neurons[:10]:  # bursting pacemakers drive the chain
        n.mode, n.burst_period, n.burst_duty = 2, 40, 12
    sim = IntegerSNNSimulator(net, seed=42)
    sim.run(300)
    ref = np.zeros((300, net.num_neurons), np.uint8)
    for tt, i in sim.spike_history:
        ref[tt, i] = 1
    assert ref.sum() > 0
    packed = jax_sim.pack(net)
    _, spk = jax.jit(lambda: jax_sim.run(packed, jax_sim.init_state(packed, 42), 300))()
    assert np.array_equal(np.asarray(spk)[:, :net.num_neurons], ref)
    root = Path(__file__).resolve().parents[1]
    if shutil.which("node") is not None and (root / "scripts/js/build/kernel.js").exists():
        f = tmp_path / "n.json"
        net.save_json(f)
        s2 = IntegerSNNSimulator(net, seed=12345); s2.run(300)
        py2 = "\n".join(f"{a} {b}" for a, b in s2.spike_history)
        js = subprocess.run(["node", str(root / "scripts/js/check_kernel_equivalence.mjs"), str(f), "300"], capture_output=True, text=True, cwd=root).stdout.strip()
        assert py2 == js
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is not None:
        from neurogenesis.bridge.ngb import write_network
        nd = root / "desktop" / "common" / "native" / "nglif"
        fd = tmp_path / "nglif_grown"; fd.mkdir()
        write_network(net, fd / "grown_long.ngb")
        (fd / "grown_long.spikes.i32").write_bytes(np.asarray(sim.spike_history, dtype="<i4").reshape(-1).tobytes())
        (fd / "MANIFEST.txt").write_text("grown_long 300 42 -\n")
        exe = tmp_path / "nglif_test_grown"
        subprocess.run([cc, "-std=c11", "-O2", str(nd / "nglif.c"), str(nd / "nglif_test.c"), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe), str(fd)], capture_output=True, text=True)
        assert r.returncode == 0 and "0 failures" in r.stdout, r.stdout + r.stderr
