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

