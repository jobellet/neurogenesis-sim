import copy

import numpy as np

from neurogenesis.stages.expansion import TissueExpandStage
from neurogenesis.stages.population import Proliferate
from neurogenesis.tissue import Tissue, SparseConnectivity


def _sheet(n=10, seed=0):
    t = Tissue.empty()
    pos = np.random.default_rng(seed).uniform(0, 1, (n, 3)) * [1, 1, 0]
    t.add_cells(n, positions=pos)
    return t


def _grow(seed, kappa, cycles=8):
    t = _sheet(10, seed)
    rng = np.random.default_rng(seed)
    expand = TissueExpandStage()
    p = {"kappa": kappa, "axes": [1, 1, 0]}
    t = expand.run(t, p, {}, {}, rng)                       # records the founder count
    for _ in range(cycles):
        t = Proliferate().run(t, {"prob": 0.5}, {}, {}, rng)
        t = expand.run(t, p, {}, {}, rng)
    return t


def _density_and_extent(t):
    xy = t.positions[t.alive][:, :2]
    ext = xy.max(axis=0) - xy.min(axis=0)
    return len(xy) / float(np.prod(ext)), ext


def test_neutral_is_noop():
    t = _sheet()
    out = TissueExpandStage().run(copy.deepcopy(t), {}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(out.positions, t.positions)
    assert TissueExpandStage.cost(0, 0, {}) == (0, 0)


def test_dilation_by_new_cell_fraction_about_centre():
    t = _sheet(4)
    c = t.positions.mean(axis=0)
    out = TissueExpandStage().run(t, {"kappa": 1.0, "n_prev": 2, "axes": [1, 0, 0]}, {}, {}, np.random.default_rng(0))
    # 2 of 4 cells are new: factor 1 + 1.0 * 2 / 4 = 1.5 along x only
    ref = _sheet(4)
    assert np.allclose(out.positions[:, 0], c[0] + (ref.positions[:, 0] - c[0]) * 1.5)
    assert np.array_equal(out.positions[:, 1:], ref.positions[:, 1:])


def test_density_bounded_while_count_grows_and_x5_per_axis():
    kappa = 0.668                                           # (1 + kappa / 3) ** 8 = 5 for growth x1.5 per cycle
    d0, e0 = _density_and_extent(_sheet(10, 0))
    ratios, dens, counts = [], [], []
    for seed in range(8):
        t = _grow(seed, kappa)
        d, e = _density_and_extent(t)
        ratios.append(e)
        dens.append(d / d0)
        counts.append(t.alive.sum() / 10)
    assert np.mean(counts) > 15                              # the count grows about 25-fold
    assert 3.5 < np.mean(np.array(ratios) / e0) < 6.5        # about x5 per tangential axis
    assert 0.3 < np.mean(dens) < 3.0                         # density stays bounded (unexpanded: x25 or more)
    flat = []
    for seed in range(8):
        t = _grow(seed, 1e-9)
        d, _ = _density_and_extent(t)
        flat.append(d / d0)
    assert np.mean(flat) > 5 * np.mean(dens)


def test_determinism_and_delay_recompute():
    a, b = _grow(3, 0.5), _grow(3, 0.5)
    assert np.array_equal(a.positions, b.positions)
    t = _sheet(3)
    t.connectivity = SparseConnectivity(np.array([0], np.int32), np.array([1], np.int32),
                                        np.array([5], np.int32), np.array([2], np.int32))
    keep = TissueExpandStage().run(copy.deepcopy(t), {"kappa": 1.0, "n_prev": 1}, {}, {}, np.random.default_rng(0))
    assert keep.connectivity.delay[0] == 2                   # delays kept by default
    out = TissueExpandStage().run(t, {"kappa": 1.0, "n_prev": 1, "recompute_delays": True, "conduction_velocity": 0.01},
                                  {}, {}, np.random.default_rng(0))
    assert out.connectivity.delay[0] > 2


def test_cost_linear():
    b1, o1 = TissueExpandStage.cost(1000, 0, {})
    b2, o2 = TissueExpandStage.cost(2000, 0, {})
    assert b2 == 2 * b1 and o2 == 2 * o1
