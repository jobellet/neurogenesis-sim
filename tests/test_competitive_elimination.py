import time
import tracemalloc
import numpy as np

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.stages.base import STAGE_REGISTRY

STAGE = STAGE_REGISTRY["competitive_elimination"]


def _tissue(pre, post, plastic=None):
    n = max(max(pre), max(post)) + 1
    t = Tissue.empty()
    t.add_cells(n, positions=np.zeros((n, 3)))
    E = len(pre)
    t.connectivity = SparseConnectivity(np.array(pre, np.int32), np.array(post, np.int32),
                                        np.full(E, 50, np.int32), np.ones(E, np.int32))
    if plastic is not None:
        t.connectivity.plastic = np.array(plastic, bool)
    return t


def _raster(T, n, firing):
    """firing: {cell: ticks}"""
    s = np.zeros((T, n), np.uint8)
    for c, ts in firing.items():
        s[ts, c] = 1
    return s


def _run(t, spikes, **p):
    return STAGE().run(t, {"spikes": spikes, **p}, {}, {}, np.random.default_rng(0))


# Inputs 0 (active), 1 and 2 (inactive) onto target 3; target fires 1 tick after input 0.
ACT = {0: np.arange(0, 100, 10), 3: np.arange(1, 100, 10)}


def test_neutral_default_noop():
    t = _tissue([0, 1, 2], [3, 3, 3])
    out = _run(t, _raster(100, 4, ACT))
    assert np.array_equal(out.connectivity.weight, [50, 50, 50])


def test_silent_target_no_elimination():
    t = _tissue([0, 1, 2], [3, 3, 3])
    out = _run(t, _raster(100, 4, {0: np.arange(0, 100, 10)}), fraction=0.5, remove=True)
    assert len(out.connectivity.pre) == 3


def test_active_input_wins():
    out = _run(_tissue([0, 1, 2], [3, 3, 3]), _raster(100, 4, ACT), fraction=0.5, remove=True)
    assert out.connectivity.pre.tolist() == [0]
    out = _run(_tissue([0, 1, 2], [3, 3, 3]), _raster(100, 4, ACT), fraction=0.5, delta=20)
    assert out.connectivity.weight.tolist() == [50, 30, 30]


def test_synchronous_inputs_kept():
    act = {0: np.arange(0, 100, 10), 1: np.arange(0, 100, 10), 3: np.arange(1, 100, 10)}
    out = _run(_tissue([0, 1], [3, 3]), _raster(100, 4, act), fraction=0.9, remove=True)
    assert len(out.connectivity.pre) == 2


def test_non_plastic_untouched():
    out = _run(_tissue([0, 1, 2], [3, 3, 3], plastic=[True, False, True]), _raster(100, 4, ACT), fraction=0.5, remove=True)
    assert out.connectivity.pre.tolist() == [0, 1]
    out = _run(_tissue([0, 1, 2], [3, 3, 3], plastic=[True, False, True]), _raster(100, 4, ACT), fraction=0.5, delta=20)
    assert out.connectivity.weight.tolist() == [50, 50, 30]


def test_recorded_by_refine_by_activity():
    t = _tissue([0, 1, 2], [3, 3, 3])
    spikes = _raster(100, 4, ACT)
    t = STAGE_REGISTRY["refine_by_activity"]().run(t, {"rule": "hebbian", "eta": 0.0, "spikes": spikes, "ticks": 100,
                                                       "record": True}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(t._activity_spikes, spikes)
    out = STAGE().run(t, {"fraction": 0.5, "remove": True}, {}, {}, np.random.default_rng(0))
    assert out.connectivity.pre.tolist() == [0]
    # off by default
    t2 = STAGE_REGISTRY["refine_by_activity"]().run(_tissue([0], [3]), {"rule": "hebbian", "eta": 0.0, "spikes": spikes,
                                                                       "ticks": 100}, {}, {}, np.random.default_rng(0))
    assert not hasattr(t2, "_activity_spikes")


def _big(seed, N=2000, E=20000, T=50):
    rng = np.random.default_rng(seed)
    t = Tissue.empty()
    t.add_cells(N, positions=np.zeros((N, 3)))
    t.connectivity = SparseConnectivity(rng.integers(0, N, E).astype(np.int32), rng.integers(0, N, E).astype(np.int32),
                                        np.full(E, 50, np.int32), rng.integers(1, 4, E).astype(np.int32))
    return t, (rng.random((T, N)) < 0.1).astype(np.uint8)


def test_determinism():
    outs = []
    for _ in range(2):
        t, s = _big(1)
        outs.append(_run(t, s, fraction=0.7, delta=10).connectivity.weight)
    assert np.array_equal(*outs)
    assert not np.all(outs[0] == 50)


def test_cost_within_factor_three():
    t, s = _big(2)
    N, E, T = len(t.alive), len(t.connectivity.pre), s.shape[0]
    tracemalloc.start()
    _run(t, s, fraction=0.7, remove=True)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    declared, ops = STAGE.cost(N, E, {"ticks": T})
    assert declared / 3 <= peak <= declared * 3, (declared, peak)
    assert ops >= T * E
