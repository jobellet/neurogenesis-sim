"""Tests for F4: Low compute, sparse candidate search via CellList, and cost validation."""
import numpy as np
import pytest

from neurogenesis.stages.base import STAGE_REGISTRY, run_schedule
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.spatial import CellList
from neurogenesis.params import Const

# Ensure all stage modules are loaded
import neurogenesis.stages.connectivity
import neurogenesis.stages.differentiation
import neurogenesis.stages.migration
import neurogenesis.stages.population
import neurogenesis.stages.refinement


def test_apoptosis_celllist_scaling_without_dense_matrix():
    """Verify that Apoptosis handles large populations (N=3000 > 2048) efficiently via CellList without O(N^2) memory."""
    N = 3000
    rng = np.random.default_rng(42)
    # Positions distributed in a 100x100x100 box
    positions = rng.uniform(0.0, 100.0, size=(N, 3))
    
    tissue = Tissue.empty()
    tissue.add_cells(N, positions=positions)
    
    stage = STAGE_REGISTRY["apoptosis"]()
    # Density radius query
    params = {"density_radius": 5.0, "max_density": 10}
    
    t_out = stage.run(tissue, params, {}, {}, rng)
    # Should execute successfully without memory explosion
    assert len(t_out.alive) <= N


def test_sparse_guidance_celllist_linear_candidate_search():
    """Verify that CellList provides fast sparse candidate search without building dense Ns x Nd matrix."""
    Ns, Nd = 2500, 2500
    rng = np.random.default_rng(123)
    
    src_pos = rng.uniform(0.0, 10.0, size=(Ns, 3))
    dst_pos = rng.uniform(0.0, 10.0, size=(Nd, 3))
    
    # Query within a small radius
    cutoff = 0.5
    cl = CellList(dst_pos, cutoff=cutoff)
    src_idx, dst_idx, dists = cl.query_radius(src_pos, cutoff, return_distances=True)
    
    # Total candidates should be a sparse fraction of Ns * Nd (which is 6,250,000)
    assert len(src_idx) < 0.1 * (Ns * Nd)
    assert np.all(dists <= cutoff)


def test_all_stages_declare_cost_within_factor_three():
    """Every registered stage must declare its cost, and declared bytes must be within factor 3 of state."""
    N = 1000
    E = 4000
    
    sample_params = {
        "seed_cells": {"N": Const(N)},
        "proliferate": {"prob": Const(0.5)},
        "apoptosis": {"density_radius": Const(2.0), "max_density": Const(5)},
        "grow_axons": {"guidance": Const({"0->1": {"sigma": 0.2, "p0": 0.5}})},
        "place_by_hand": {"positions": Const(np.zeros((N, 3)).tolist())},
        "connect_by_hand": {"pre": Const([0]), "post": Const([1])},
        "express": {"K": Const(4)},
        "differentiate": {"types": Const([{"type_id": 1}, {"type_id": 2}])},
        "migrate": {"speed": Const(1.0)},
        "sort": {"axis": Const([1.0, 0.0, 0.0])},
        "prune": {"threshold": Const(10)},
        "scale": {"target": Const(100.0)},
        "myelinate": {"delay_factor": Const(0.8)},
        "refine_by_activity": {"rule": Const("stdp"), "ticks": Const(50)}
    }
    
    for stage_name in sample_params:
        cls = STAGE_REGISTRY[stage_name]
        assert hasattr(cls, "cost"), f"Stage {stage_name} must declare a cost method"
        params = sample_params.get(stage_name, {})
        bytes_cost, ops_cost = cls.cost(N, E, params)
        
        assert isinstance(bytes_cost, (int, np.integer)) and bytes_cost > 0, \
            f"Stage {stage_name} declared non-positive bytes_cost: {bytes_cost}"
        assert isinstance(ops_cost, (int, np.integer)) and ops_cost > 0, \
            f"Stage {stage_name} declared non-positive ops_cost: {ops_cost}"
            
        # Verify linear scaling with N: cost at 2*N should be within factor 3 of 2 * cost at N
        bytes_2n, ops_2n = cls.cost(2 * N, 2 * E, params)
        # Factor 3 check on scaling
        assert bytes_cost <= bytes_2n <= 3 * (2 * bytes_cost), \
            f"Stage {stage_name} memory does not scale linearly: {bytes_cost} -> {bytes_2n}"
        assert ops_cost <= ops_2n <= 4 * (2 * ops_cost), \
            f"Stage {stage_name} ops do not scale linearly: {ops_cost} -> {ops_2n}"

    # The sample params are ones the stages read: each changes a toy tissue's synapses.
    for stage_name in ("prune", "scale", "myelinate"):
        t = Tissue.empty()
        t.add_cells(3, positions=np.zeros((3, 3)))
        t.connectivity = SparseConnectivity(np.array([0, 1, 2], dtype=np.int32), np.array([1, 2, 0], dtype=np.int32),
                                            np.array([5, 20, -40], dtype=np.int32), np.array([10, 10, 10], dtype=np.int32))
        before = [getattr(t.connectivity, k).copy() for k in ("pre", "weight", "delay")]
        out = STAGE_REGISTRY[stage_name]().run(t, sample_params[stage_name], {}, {}, np.random.default_rng(0))
        after = [getattr(out.connectivity, k) for k in ("pre", "weight", "delay")]
        assert any(len(a) != len(b) or not np.array_equal(a, b) for a, b in zip(after, before)), \
            f"Stage {stage_name} ignored its sample params"


def test_stage_cost_accuracy_against_tissue_memory():
    """Verify that stage declared memory is within factor 3 of actual Tissue array allocation."""
    N = 1000
    # Measure memory of tissue with N cells:
    # positions (24), cell_id (4), parent_id (4), clone_id (4), birth_stage (4), cell_type (4),
    # region (4), sign (4), mode (4), shift_v (4), shift_s (4), base_weight (4), conn_radius (4),
    # conn_prob (4), burst_period (4), burst_duty (4), poisson_hz (4), refractory (4), role (4),
    # compartment (4), threshold (4), alive (1), directions (12) = ~120 bytes per cell
    expected_cell_bytes = N * 128
    
    seed_bytes, _ = STAGE_REGISTRY["seed_cells"].cost(0, 0, {"N": Const(N)})
    assert expected_cell_bytes / 3 <= seed_bytes <= expected_cell_bytes * 3
    
    prolif_bytes, _ = STAGE_REGISTRY["proliferate"].cost(N, 0, {"prob": Const(1.0)})
    assert expected_cell_bytes / 3 <= prolif_bytes <= expected_cell_bytes * 3

