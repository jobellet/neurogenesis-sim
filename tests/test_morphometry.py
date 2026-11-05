"""Phase M1: TMD barcodes, persistence images, Wasserstein distance, SWC adapter."""
import tracemalloc
import warnings

import numpy as np

from neurogenesis.arbors import ArborStore, read_swc
from neurogenesis.morphometry import tmd
from neurogenesis.morphometry.tmd import (barcodes, barcodes_cost, persistence_images, to_swc_bytes,
                                          wasserstein_squared)


def _y(cell=0, shift=(0, 0, 0), rot=None):
    xyz = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [1, -3, 0]], float)
    if rot is not None:
        xyz = xyz @ rot.T
    xyz = xyz + np.asarray(shift, float)
    return ArborStore(xyz, np.ones(4), [-1, 0, 1, 1], [1, 3, 3, 3], np.full(4, cell))


def _bars(b):
    return sorted(map(tuple, np.stack([b.birth, b.death], 1).round(9)))


def test_y_arbor_exact_barcode():
    b = barcodes(_y())
    # root bar (0, 4): farthest tip at path 1 + 3; bifurcation at f = 1 releases the short branch (1, 2)
    assert _bars(b) == [(0.0, 4.0), (1.0, 2.0)]
    assert np.all(b.death >= b.birth)


def test_radial_filtration():
    b = barcodes(_y(), filtration="radial")
    assert np.allclose(_bars(b), [(0.0, np.hypot(1, 3)), (1.0, np.sqrt(2))], atol=1e-6)


def test_rotation_translation_invariance():
    th = 0.7
    rot = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    a = barcodes(_y())
    b = barcodes(_y(shift=(5, -2, 3), rot=rot))
    assert np.allclose(_bars(a), _bars(b), atol=1e-5)
    ia = persistence_images(a, 1, bounds=(0, 5.3))
    ib = persistence_images(b, 1, bounds=(0, 5.3))
    assert np.allclose(ia, ib, atol=1e-5)
    assert ia.shape == (1, 400) and ia.dtype == np.float32


def test_population_two_cells_and_compartment_filter():
    s = ArborStore.concatenate([_y(0), _y(1)])
    b = barcodes(s)
    assert len(b) == 4 and sorted(set(b.cell)) == [0, 1]
    assert np.allclose(b.of_cell(1), [[0, 4], [1, 2]])
    only_root = barcodes(s, compartments=["axon"])
    assert len(only_root) == 2                      # dendrite nodes dropped: one bar per root


def test_wasserstein():
    a = np.array([[0, 4.0], [1, 2.0]])
    assert wasserstein_squared(a, a) == 0.0
    assert wasserstein_squared(a, np.zeros((0, 2))) == (16 + 1) / 2.0
    c = np.array([[0, 5.0], [1, 2.0]])
    assert np.isclose(wasserstein_squared(a, c), 1.0)
    assert wasserstein_squared(a, c) > 0
    rng = np.random.default_rng(0)
    p, q = np.sort(rng.random((12, 2)), 1), np.sort(rng.random((9, 2)), 1)
    from scipy.optimize import linear_sum_assignment  # test-only cross-check, scipy is not used by the module
    n, m = 12, 9
    C = np.zeros((21, 21))
    C[:n, :m] = ((p[:, None] - q[None]) ** 2).sum(-1)
    C[:n, m:] = ((p[:, 1] - p[:, 0]) ** 2 / 2)[:, None]
    C[n:, :m] = ((q[:, 1] - q[:, 0]) ** 2 / 2)[None, :]
    r, c = linear_sum_assignment(C)
    assert np.isclose(wasserstein_squared(p, q), C[r, c].sum())


def test_wasserstein_refusal_is_counted(monkeypatch):
    monkeypatch.setattr(tmd, "MAX_WASSERSTEIN_PAIRS", 4)
    before = tmd.WASSERSTEIN_REFUSALS
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        out = wasserstein_squared(np.ones((3, 2)), np.ones((3, 2)))
    assert np.isnan(out) and tmd.WASSERSTEIN_REFUSALS == before + 1 and w


def test_deterministic_and_neutral_reference():
    assert _bars(barcodes(_y())) == _bars(barcodes(_y()))
    assert len(barcodes(ArborStore())) == 0
    assert wasserstein_squared(np.zeros((0, 2)), np.zeros((0, 2))) == 0.0


def test_declared_cost_within_factor_three():
    rng = np.random.default_rng(1)
    n = 40000
    parent = np.concatenate([[-1], [rng.integers(max(0, i - 30), i) for i in range(1, n)]])
    xyz = np.cumsum(rng.normal(size=(n, 3)), 0)
    s = ArborStore(xyz, np.ones(n), parent, np.full(n, 3), np.zeros(n))
    tracemalloc.start()
    barcodes(s)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared, _ = barcodes_cost(n)
    assert declared / 3 <= peak <= declared * 3


def test_swc_adapter_roundtrip(tmp_path):
    s = _y()
    p = tmp_path / "a.swc"
    p.write_bytes(to_swc_bytes(s, cells=[0]))
    back = read_swc(p)
    assert _bars(barcodes(back)) == _bars(barcodes(s))
