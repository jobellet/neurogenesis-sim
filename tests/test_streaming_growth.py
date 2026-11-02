import pytest
import numpy as np
from pathlib import Path

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.streaming import (
    grow_axons_streaming,
    assemble_shards,
    stream_stats,
    streaming_growth_cost,
    SynapseShardManifest
)

def test_streaming_growth_basic(tmp_path):
    # Setup simple tissue
    N = 100
    tissue = Tissue.empty()
    tissue.add_cells(
        N,
        positions=np.random.default_rng(42).uniform(0, 1, (N, 3)),
        region=np.zeros(N, dtype=np.int32),
        sign=np.ones(N, dtype=np.int8)
    )

    params = {
        "projections": ["0->0"],
        "guidance": {
            "0->0": {
                "sigma": 0.2,
                "p0": 1.0,
                "w": 5.0
            }
        },
        "exact": True
    }
    
    rng = np.random.default_rng(123)
    
    out_dir = tmp_path / "shards"
    manifest = grow_axons_streaming(
        tissue, params, {}, {}, rng, out_dir, chunk_size=20
    )
    
    assert isinstance(manifest, SynapseShardManifest)
    assert manifest.num_synapses > 0
    assert len(manifest.shards) > 0
    
    # Check that we can stream stats
    stats = stream_stats(manifest)
    assert stats["total_synapses"] == manifest.num_synapses
    assert "weight_mean" in stats
    assert "delay_mean" in stats
    
    # Check that we can assemble
    c = assemble_shards(manifest)
    assert isinstance(c, SparseConnectivity)
    assert len(c.pre) == manifest.num_synapses
    assert len(c.weight) == manifest.num_synapses
    
    # Check save/load manifest
    manifest_path = out_dir / "manifest.json"
    manifest.save(manifest_path)
    
    loaded_manifest = SynapseShardManifest.load(manifest_path)
    assert loaded_manifest.num_synapses == manifest.num_synapses
    assert len(loaded_manifest.shards) == len(manifest.shards)

    stats2 = stream_stats(loaded_manifest)
    assert stats2["total_synapses"] == stats["total_synapses"]
    assert np.allclose(stats2["weight_mean"], stats["weight_mean"])

def test_streaming_growth_determinism(tmp_path):
    N = 50
    tissue = Tissue.empty()
    tissue.add_cells(
        N,
        positions=np.random.default_rng(42).uniform(0, 1, (N, 3)),
        region=np.zeros(N, dtype=np.int32),
        sign=np.ones(N, dtype=np.int8)
    )

    params = {
        "projections": ["0->0"],
        "guidance": {
            "0->0": {
                "sigma": 0.2,
                "p0": 0.5,
                "w": 5.0
            }
        },
        "exact": False
    }

    dir1 = tmp_path / "shards1"
    dir2 = tmp_path / "shards2"
    
    rng1 = np.random.default_rng(456)
    m1 = grow_axons_streaming(tissue, params, {}, {}, rng1, dir1, chunk_size=10)
    
    rng2 = np.random.default_rng(456)
    m2 = grow_axons_streaming(tissue, params, {}, {}, rng2, dir2, chunk_size=10)
    
    assert m1.num_synapses == m2.num_synapses
    
    c1 = assemble_shards(m1)
    c2 = assemble_shards(m2)
    
    assert np.array_equal(c1.pre, c2.pre)
    assert np.array_equal(c1.post, c2.post)
    assert np.array_equal(c1.weight, c2.weight)
    assert np.array_equal(c1.delay, c2.delay)

def test_peak_shard_memory_scaling(tmp_path):
    N = 200
    tissue = Tissue.empty()
    tissue.add_cells(
        N,
        positions=np.random.default_rng(42).uniform(0, 1, (N, 3)),
        region=np.zeros(N, dtype=np.int32),
        sign=np.ones(N, dtype=np.int8)
    )

    params = {
        "projections": ["0->0"],
        "guidance": {
            "0->0": {
                "sigma": 0.5,
                "p0": 1.0,
                "w": 1.0
            }
        },
        "exact": False
    }

    dir1 = tmp_path / "shards_small"
    rng = np.random.default_rng(42)
    m1 = grow_axons_streaming(tissue, params, {}, {}, rng, dir1, chunk_size=10)
    
    # Check max shard size directly from manifest
    max_shard_size = max(shard['num_synapses'] for shard in m1.shards)
    
    # It should be constrained by chunk_size (10) * N (200) = 2000 max, but likely much smaller
    # as p0=1.0 and sigma=0.5 will yield many connections. 
    # But total synapses is around N * N = 40,000 max.
    assert max_shard_size <= 10 * N

    # Check assembled and streamed match
    c = assemble_shards(m1)
    stats = stream_stats(m1)
    
    assert len(c.pre) == stats["total_synapses"]
    if len(c.pre) > 0:
        assert stats["weight_max"] == float(np.max(c.weight))
        assert stats["weight_min"] == float(np.min(c.weight))
        assert stats["delay_max"] == float(np.max(c.delay))
        assert stats["delay_min"] == float(np.min(c.delay))
        
        # Verify histogram against actual
        actual_out_degree = np.bincount(c.pre, minlength=N)
        actual_histogram = np.bincount(actual_out_degree)
        assert np.array_equal(stats["out_degree_histogram"], actual_histogram)

    cost = streaming_growth_cost(N, len(c.pre), params, chunk_size=10)
    assert cost["bytes"] > 0
    assert cost["ops"] > 0
    # Cost bytes scales with chunk_size, not N^2
    cost_large_e = streaming_growth_cost(N, 10_000_000, params, chunk_size=10)
    assert cost_large_e["bytes"] == cost["bytes"]


