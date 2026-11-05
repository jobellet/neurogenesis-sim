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

from neurogenesis.morphometry.features import features, features_cost, stratification_peaks


def _layered(n_cells=3, seed=0):
    """Cells with dendrites that reach two depth bands (z = +0.3 and z = -0.5) from the soma."""
    rng = np.random.default_rng(seed)
    parts = []
    for c in range(n_cells):
        xyz = [[0, 0, 0]]
        par = [-1]
        for z in (0.3, -0.5):
            for _ in range(4):
                a = rng.uniform(0, 2 * np.pi)
                xyz.append([0.05 * np.cos(a), 0.05 * np.sin(a), z])
                par.append(0)
        parts.append(ArborStore(xyz, np.ones(len(xyz)), par, [1] + [3] * 8, np.full(len(xyz), c)))
    return ArborStore.concatenate(parts)


def test_features_shapes_normalisation_and_empty_cells():
    s = _layered()
    f = features(s, n_cells=5)
    assert all(v.dtype == np.float32 for v in f.values())
    assert f["density3d"].shape == (5, 512) and f["radial"].shape == (5, 16)
    assert f["angle_given_distance"].shape == (5, 16 * 6)
    assert np.allclose(f["radial"][:3].sum(1), 1, atol=1e-5) and f["radial"][3:].sum() == 0
    assert features(s, compartment="axon")["radial"].sum() == 0          # no axon: all zeros


def test_stratification_peaks_are_the_layers():
    f = features(_layered(), n_cells=3, extent=1.0, bins=20, sigma=0.5)
    peaks = stratification_peaks(f["stratification"][0])
    assert len(peaks) == 2
    z = (peaks + 0.5) / 20 * 2 - 1
    assert np.allclose(sorted(z), [-0.5, 0.3], atol=0.11)


def test_features_translation_invariant_and_deterministic():
    s = _layered()
    t = ArborStore(s.xyz + np.array([3, -2, 1], np.float32), s.radius, s.parent, s.compartment, s.cell)
    a, b = features(s), features(t)
    assert all(np.allclose(a[k], b[k], atol=1e-4) for k in a)
    assert all(np.array_equal(a[k], features(s)[k]) for k in a)


def test_branch_angle_of_a_right_angle_fork():
    s = ArborStore([[0, 0, 0], [0, 0, 0.1], [0.1, 0, 0.1], [0, 0.1, 0.1]], np.ones(4), [-1, 0, 1, 1], [1, 3, 3, 3], np.zeros(4))
    f = features(s, angle_bins=6, bins=4, extent=1.0)
    row = f["angle_given_distance"][0].reshape(4, 6)
    assert row[0, 3] == 1.0          # fork at path distance 0.1 (bin 0 of 4), angle pi/2 (bin 3 of 6)


from neurogenesis.fitting import METRICS
from neurogenesis.morphometry.metrics import (
    embed_2d,
    fasano_franceschini_2d,
    laminar_density_profile_ks,
    morphology_wasserstein_to_reference,
    population_wasserstein_squared,
)
from neurogenesis.tissue import Tissue


def test_fasano_franceschini_2d():
    rng = np.random.default_rng(42)
    s1 = rng.normal(0, 1, (60, 2))
    s2 = rng.normal(0, 1, (60, 2))
    s3 = rng.normal(8, 1, (60, 2))
    D_same, p_same = fasano_franceschini_2d(s1, s1)
    assert D_same == 0.0 and p_same == 1.0
    _, p_sim = fasano_franceschini_2d(s1, s2)
    assert p_sim > 0.05
    D_diff, p_diff = fasano_franceschini_2d(s1, s3)
    assert p_diff < 0.01 and D_diff > 0.8
    assert fasano_franceschini_2d(np.zeros((0, 2)), s1) == (0.0, 1.0)


def test_embed_2d():
    rng = np.random.default_rng(0)
    a = rng.normal(size=(20, 10))
    b = rng.normal(size=(25, 10))
    ea, eb = embed_2d(a, b, method="pca")
    assert ea.shape == (20, 2) and eb.shape == (25, 2)
    # Lazy UMAP fallback test (when umap is not installed, falls back with warning)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ua, ub = embed_2d(a, b, method="umap")
        assert ua.shape == (20, 2) and ub.shape == (25, 2)


def test_population_wasserstein_squared():
    rng = np.random.default_rng(123)
    a = rng.normal(0, 1, (10, 8))
    assert population_wasserstein_squared(a, a) == 0.0
    b = rng.normal(5, 1, (10, 8))
    d2 = population_wasserstein_squared(a, b)
    assert d2 > 10.0
    # Unequal sizes (Sinkhorn transport)
    c = rng.normal(0, 1, (15, 8))
    d_unequal = population_wasserstein_squared(a, c)
    assert d_unequal >= 0.0
    assert population_wasserstein_squared(np.zeros((0, 8)), np.zeros((0, 8))) == 0.0


def test_registered_morphology_metrics_with_tissue():
    # Construct a toy Tissue with arbors
    s = _layered(n_cells=4)
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3)))
    t.arbors = s

    # 1. morphology_wasserstein_to_reference
    bars = barcodes(s)
    imgs = persistence_images(bars, cells=[0, 1, 2, 3], grid=10, bounds=(0, 2.0))
    opt = {"metric": "morphology_wasserstein_to_reference", "reference_vectors": imgs, "grid": 10, "bounds": (0, 2.0)}
    # Direct and registered metric
    dist = morphology_wasserstein_to_reference(t, opt)
    assert dist == 0.0
    assert METRICS["morphology_wasserstein_to_reference"](t, opt) == 0.0

    # Non-matching reference
    opt_far = {"metric": "morphology_wasserstein_to_reference", "reference_vectors": imgs + 5.0, "grid": 10, "bounds": (0, 2.0)}
    assert morphology_wasserstein_to_reference(t, opt_far) > 0.0

    # 2. laminar_density_profile_ks
    f = features(s, n_cells=4, extent=1.0, bins=16)
    ref_prof = f["stratification"]
    opt_ks = {"metric": "laminar_density_profile_ks", "reference_profile": ref_prof, "bins": 16, "extent": 1.0}
    p_val = laminar_density_profile_ks(t, opt_ks)
    assert p_val > 0.05
    assert METRICS["laminar_density_profile_ks"](t, opt_ks) > 0.05


def test_features_cost_within_factor_three():
    rng = np.random.default_rng(2)
    n = 30000
    parent = np.concatenate([[-1], [rng.integers(max(0, i - 25), i) for i in range(1, n)]])
    xyz = np.cumsum(rng.normal(size=(n, 3)), 0).astype(np.float32)
    s = ArborStore(xyz, np.ones(n, np.float32), parent.astype(np.int32), np.full(n, 3, np.int8), np.zeros(n, np.int32))
    tracemalloc.start()
    features(s, normalise=False)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared_bytes, _ = features_cost(n)
    assert declared_bytes / 3 <= peak <= declared_bytes * 3
