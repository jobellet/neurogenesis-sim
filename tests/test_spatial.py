import numpy as np
import pytest
import tracemalloc
from neurogenesis.spatial import CellList

def test_query_radius_brute_force():
    np.random.seed(42)
    N = 300
    positions = np.random.rand(N, 3).astype(np.float32)
    cutoff = 0.2
    
    cl = CellList(positions, cutoff)
    
    # self-queries
    src, dst, dists = cl.query_radius(positions, cutoff, return_distances=True)
    
    # Brute force
    diffs = positions[:, np.newaxis, :] - positions[np.newaxis, :, :]
    dist_sq = np.sum(diffs * diffs, axis=2)
    bf_src, bf_dst = np.where(dist_sq <= cutoff * cutoff)
    
    # Sort brute force results
    sort_idx = np.lexsort((bf_dst, bf_src))
    bf_src = bf_src[sort_idx]
    bf_dst = bf_dst[sort_idx]
    bf_dists = np.sqrt(dist_sq[bf_src, bf_dst])
    
    assert np.array_equal(src, bf_src)
    assert np.array_equal(dst, bf_dst)
    assert np.allclose(dists, bf_dists)
    
    # Cross queries
    M = 150
    queries = np.random.rand(M, 3).astype(np.float32)
    src_c, dst_c, dists_c = cl.query_radius(queries, cutoff, return_distances=True)
    
    diffs_c = queries[:, np.newaxis, :] - positions[np.newaxis, :, :]
    dist_sq_c = np.sum(diffs_c * diffs_c, axis=2)
    bf_src_c, bf_dst_c = np.where(dist_sq_c <= cutoff * cutoff)
    
    sort_idx_c = np.lexsort((bf_dst_c, bf_src_c))
    bf_src_c = bf_src_c[sort_idx_c]
    bf_dst_c = bf_dst_c[sort_idx_c]
    bf_dists_c = np.sqrt(dist_sq_c[bf_src_c, bf_dst_c])
    
    assert np.array_equal(src_c, bf_src_c)
    assert np.array_equal(dst_c, bf_dst_c)
    assert np.allclose(dists_c, bf_dists_c)

def test_query_knn_brute_force():
    np.random.seed(43)
    N = 300
    positions = np.random.rand(N, 3).astype(np.float32)
    cutoff = 0.2
    
    cl = CellList(positions, cutoff)
    k = 5
    
    # Self queries
    idx, dists = cl.query_knn(positions, k)
    
    # Brute force
    diffs = positions[:, np.newaxis, :] - positions[np.newaxis, :, :]
    dist_sq = np.sum(diffs * diffs, axis=2)
    bf_dists = np.sqrt(dist_sq)
    
    for i in range(N):
        row = bf_dists[i]
        # sort row
        sort_idx = np.argsort(row)
        assert np.array_equal(idx[i], sort_idx[:k])
        assert np.allclose(dists[i], row[sort_idx[:k]])

def test_linear_scaling():
    import time
    np.random.seed(44)
    cutoff = 0.05
    
    times = []
    Ns = [5_000, 10_000, 20_000, 40_000, 50_000]
    
    for N in Ns:
        # Scale volume with N to keep density roughly constant
        box_size = (N / 1000) ** (1/3)
        positions = np.random.rand(N, 3).astype(np.float32) * box_size
        
        t0 = time.perf_counter()
        cl = CellList(positions, cutoff)
        
        # Query 10% of points
        queries = positions[:max(1, N // 10)]
        src, dst = cl.query_radius(queries, cutoff)
        
        t1 = time.perf_counter()
        times.append(t1 - t0)
        
    # Check scaling roughly linear. time(50k) / time(5k) shouldn't be much larger than 10.
    # Allowing some margin for setup/overhead. O(N^2) would be 100x.
    ratio = times[-1] / times[0]
    assert ratio < 20, f"Scaling seems worse than O(N). Ratio: {ratio}"

def test_declared_cost():
    np.random.seed(45)
    N = 10_000
    positions = np.random.rand(N, 3).astype(np.float32)
    cutoff = 0.1
    
    tracemalloc.start()
    m0, _ = tracemalloc.get_traced_memory()
    
    cl = CellList(positions, cutoff)
    
    # queries
    queries = positions[:1000]
    src, dst = cl.query_radius(queries, cutoff)
    
    m1, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    measured_bytes = peak - m0
    
    # Estimate mean neighbours
    mean_neighbours = len(src) / 1000
    if mean_neighbours == 0:
        mean_neighbours = 1
        
    decl_bytes, decl_ops = CellList.declared_cost(N, 1000, mean_neighbours)
    
    # Should be within a factor of 3
    assert measured_bytes <= decl_bytes * 3
    assert decl_bytes <= measured_bytes * 3



def _legacy_query_radius(cl, query_points, radius):
    """Reference: the original per-cell loop of CellList.query_radius (before vectorisation)."""
    query_points = np.asarray(query_points, dtype=np.float64)
    gs = cl.grid_shape
    q_cells = np.clip(np.floor((query_points - cl.box_min) / cl.box_size * gs).astype(np.int32), 0, gs - 1)
    q_1d = q_cells[:, 0] * (gs[1] * gs[2]) + q_cells[:, 1] * gs[2] + q_cells[:, 2]
    q_sort = np.argsort(q_1d)
    cells, starts, counts = np.unique(q_1d[q_sort], return_index=True, return_counts=True)
    cell_size = cl.box_size / gs
    steps = [max(1, int(np.ceil(radius / cell_size[a]))) if gs[a] > 1 else 1 for a in range(3)]
    grids = np.meshgrid(*[np.arange(-r, r + 1) for r in steps], indexing='ij')
    stencil = np.stack([g.ravel() for g in grids], axis=1)
    src, dst, dist = [], [], []
    for cell, q0, nq in zip(cells, starts, counts):
        c = np.array([cell // (gs[1] * gs[2]), (cell // gs[2]) % gs[1], cell % gs[2]]) + stencil
        c = c[np.all((c >= 0) & (c < gs), axis=1)]
        t = c[:, 0] * (gs[1] * gs[2]) + c[:, 1] * gs[2] + c[:, 2]
        cand = np.concatenate([np.arange(s, e) for s, e in zip(cl.cell_ptr[t], cl.cell_ptr[t + 1])])
        if len(cand) == 0:
            continue
        diff = query_points[q_sort[q0:q0 + nq]][:, None, :] - cl.sorted_positions[cand][None, :, :]
        d2 = np.sum(diff * diff, axis=-1)
        qi, ci = np.nonzero(d2 <= radius * radius)
        src.append(q_sort[q0:q0 + nq][qi])
        dst.append(cl.sort_idx[cand[ci]])
        dist.append(np.sqrt(d2[qi, ci]))
    if not src:
        return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32), np.zeros(0)
    src, dst, dist = np.concatenate(src), np.concatenate(dst), np.concatenate(dist)
    order = np.lexsort((dst, src))
    return src[order], dst[order], dist[order]


def _legacy_query_knn(cl, query_points, k):
    """Reference: the original doubling-radius search with per-query selection and dense fallback."""
    query_points = np.asarray(query_points, dtype=np.float64)
    res_idx = np.full((len(query_points), k), -1, dtype=np.int32)
    res_dist = np.full((len(query_points), k), np.inf)
    if cl.n_points == 0 or len(query_points) == 0:
        return res_idx, res_dist
    density = cl.n_points / max(1e-8, float(np.prod(cl.box_size)))
    radius = max(cl.cutoff, float((k * 3 / (4 * np.pi * max(1e-8, density))) ** (1 / 3)) * 1.5)
    remaining = np.arange(len(query_points))
    while len(remaining) > 0 and radius < 2.0 * float(np.max(cl.box_size)):
        src, dst, dists = _legacy_query_radius(cl, query_points[remaining], radius)
        found = np.zeros(len(remaining), dtype=bool)
        if len(src):
            ids, starts, counts = np.unique(src, return_index=True, return_counts=True)
            for s, start, count in zip(ids, starts, counts):
                if count >= k or count == cl.n_points:
                    d_sub, dst_sub = dists[start:start + count], dst[start:start + count]
                    order = np.lexsort((dst_sub, d_sub))[:k]
                    res_idx[remaining[s], :len(order)] = dst_sub[order]
                    res_dist[remaining[s], :len(order)] = d_sub[order]
                found[s] = count >= k
        remaining = remaining[~found]
        radius *= 2.0
    for q in remaining:
        dists = np.linalg.norm(cl.positions - query_points[q], axis=-1)
        order = np.lexsort((np.arange(len(dists)), dists))[:k]
        res_idx[q, :len(order)] = order
        res_dist[q, :len(order)] = dists[order]
    return res_idx, res_dist


def _assert_identical(new, ref):
    for a, b in zip(new, ref):
        assert a.dtype == b.dtype and a.shape == b.shape
        assert np.array_equal(a, b)


@pytest.mark.parametrize("layout", ["uniform", "planar", "grid_boundaries", "clustered", "explicit_box"])
def test_vectorised_queries_identical_to_legacy(layout):
    """Vectorised radius and knn queries return exactly the legacy indices, order and distances."""
    rng = np.random.default_rng(7)
    box = None
    for n in (0, 1, 7, 250):
        pos = rng.random((n, 3))
        if layout == "planar":
            pos[:, 2] = 0.0
        elif layout == "grid_boundaries":
            pos = np.round(pos * 5) / 5  # on cell faces, with duplicates
        elif layout == "clustered":
            pos = rng.normal(size=(n, 3)) * rng.choice([0.05, 0.4], size=(n, 1))
        elif layout == "explicit_box":
            box = (np.zeros(3), np.full(3, 0.8))  # points beyond it are clipped into edge cells
        queries = np.concatenate([pos[:40], rng.random((30, 3)) * 1.6 - 0.3, np.full((2, 3), 50.0)])
        for cutoff in (0.07, 0.2, 1.5):
            cl = CellList(pos, cutoff, box)
            for radius in (cutoff, 0.5 * cutoff, 2.3 * cutoff):
                _assert_identical(cl.query_radius(queries, radius, return_distances=True),
                                  _legacy_query_radius(cl, queries, radius))
                assert all(np.array_equal(a, b) for a, b in zip(
                    cl.query_radius(queries, radius), cl.query_radius(queries, radius, return_distances=True)))
            for k in (1, 4, 30):
                _assert_identical(cl.query_knn(queries, k), _legacy_query_knn(cl, queries, k))


@pytest.mark.parametrize("n, box, cutoff", [(4000, 4 ** (1 / 3), 0.2), (4000, 1.0, 0.05), (20000, 1.0, 0.02)])
def test_declared_cost_dense_and_sparse(n, box, cutoff):
    """Declared bytes within a factor 3 of the measured peak, for dense and mostly empty grids."""
    positions = np.random.default_rng(46).random((n, 3)) * box
    tracemalloc.start()
    m0, _ = tracemalloc.get_traced_memory()
    src, _ = CellList(positions, cutoff).query_radius(positions, cutoff)
    measured = tracemalloc.get_traced_memory()[1] - m0
    tracemalloc.stop()
    declared, _ = CellList.declared_cost(n, n, max(1.0, len(src) / n))
    assert declared / 3 <= measured <= declared * 3


@pytest.mark.parametrize("layout", ["uniform", "grid_boundaries", "clustered"])
def test_jax_backend_matches_numpy(layout):
    """backend="jax" returns the same indices as NumPy and distances within floating-point tolerance."""
    rng = np.random.default_rng(11)
    box = None
    for n in (0, 1, 7, 120):
        pos = rng.random((n, 3))
        if layout == "grid_boundaries":
            pos = np.round(pos * 5) / 5
        elif layout == "clustered":
            pos = rng.normal(size=(n, 3)) * rng.choice([0.05, 0.4], size=(n, 1))
        queries = np.concatenate([pos[:40], rng.random((30, 3)) * 1.6 - 0.3, np.full((2, 3), 50.0)])
        for cutoff in (0.07, 0.2):
            ref = CellList(pos, cutoff, box)
            jax_cl = CellList(pos, cutoff, box, backend="jax")
            assert jax_cl.backend == "jax"
            for radius in (cutoff, 2.3 * cutoff):
                a = ref.query_radius(queries, radius, return_distances=True)
                b = jax_cl.query_radius(queries, radius, return_distances=True)
                assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
                assert np.allclose(a[2], b[2], rtol=1e-12, atol=1e-12)
            for k in (1, 30):
                a = ref.query_knn(queries, k)
                b = jax_cl.query_knn(queries, k)
                assert np.array_equal(a[0], b[0])
                assert np.allclose(a[1], b[1], rtol=1e-12, atol=1e-12)


def test_jax_backend_determinism_and_validation():
    rng = np.random.default_rng(3)
    pos = rng.random((50, 3))
    with pytest.raises(ValueError):
        CellList(pos, 0.2, backend="cuda")
    a = CellList(pos, 0.2, backend="jax")
    b = CellList(pos, 0.2, backend="jax")
    r1 = a.query_radius(pos, 0.2, return_distances=True)
    r2 = b.query_radius(pos, 0.2, return_distances=True)
    for x, y in zip(r1, r2):
        assert isinstance(x, np.ndarray)
        assert np.array_equal(x, y)
    k1 = a.query_knn(pos, 4)
    k2 = b.query_knn(pos, 4)
    assert np.array_equal(k1[0], k2[0]) and np.array_equal(k1[1], k2[1])


# backend="auto" ---------------------------------------------------------------------------------------------------
def test_auto_backend_is_numpy_on_a_cpu_or_without_jax(monkeypatch):
    from neurogenesis import spatial
    monkeypatch.delenv("NEUROGENESIS_SPATIAL_BACKEND", raising=False)
    monkeypatch.setattr(spatial, "_jax_platform", lambda: None)
    assert spatial.resolve_backend("auto") == "numpy"
    monkeypatch.setattr(spatial, "_jax_platform", lambda: "cpu")
    assert spatial.resolve_backend("auto") == "numpy"
    pos = np.random.default_rng(0).random((50, 3))
    assert CellList(pos, 0.2, backend="auto").backend == "numpy"
    assert spatial.resolve_backend("numpy") == "numpy" and spatial.resolve_backend("jax") == "jax"
    with pytest.raises(ValueError):
        spatial.resolve_backend("cuda")


def test_auto_backend_times_an_accelerator_once_and_honours_the_environment(monkeypatch):
    from neurogenesis import spatial
    monkeypatch.delenv("NEUROGENESIS_SPATIAL_BACKEND", raising=False)
    monkeypatch.setattr(spatial, "_AUTO_CHOICE", {})
    monkeypatch.setattr(spatial, "_jax_platform", lambda: "gpu")
    calls = []
    monkeypatch.setattr(spatial, "_jax_is_faster", lambda: calls.append(1) or True)
    assert spatial.resolve_backend("auto") == "jax" and spatial.resolve_backend("auto") == "jax"
    assert len(calls) == 1                                   # measured once per platform
    monkeypatch.setattr(spatial, "_AUTO_CHOICE", {})
    monkeypatch.setattr(spatial, "_jax_is_faster", lambda: False)
    assert spatial.resolve_backend("auto") == "numpy"
    monkeypatch.setenv("NEUROGENESIS_SPATIAL_BACKEND", "numpy")
    monkeypatch.setattr(spatial, "_jax_is_faster", lambda: True)
    assert spatial.resolve_backend("auto") == "numpy"        # the environment overrides auto ...
    assert spatial.resolve_backend("jax") == "jax"           # ... but never an explicit choice


def test_jax_timing_helper_runs_and_returns_a_bool():
    from neurogenesis import spatial
    assert spatial._jax_is_faster(n_points=300, n_queries=50) in (True, False)
