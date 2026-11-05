"""Tests for stage instantiate_morphologies (Phase M2)."""
from pathlib import Path
import tracemalloc
import numpy as np
import pytest

import neurogenesis.stages  # noqa: F401
from neurogenesis.stages.base import STAGE_REGISTRY
from neurogenesis.stages.morphologies import InstantiateMorphologies
from neurogenesis.tissue import Tissue, SparseConnectivity

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "morphology"


def _make_tissue(n=6):
    t = Tissue.empty()
    positions = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [2.0, 2.0, 0.0],
        [3.0, 0.0, 1.0],
        [0.0, 3.0, 1.0]
    ], dtype=np.float64)[:n]
    t.add_cells(n, positions=positions)
    # Set dummy connectivity
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 1], dtype=np.int32),
        post=np.array([1, 2], dtype=np.int32),
        weight=np.array([1.5, -0.5], dtype=np.float32),
        delay=np.array([1, 2], dtype=np.int32)
    )
    return t


def test_instantiate_morphologies_attaches_and_preserves_connectivity():
    stage = STAGE_REGISTRY["instantiate_morphologies"]()
    t = _make_tissue(4)
    init_pre = t.connectivity.pre.copy()
    init_post = t.connectivity.post.copy()

    params = {
        "catalogue": FIXTURES_DIR,
        "attachment_prob": 1.0,
        "n_neurites": 1,
        "max_nodes": 500
    }
    rng = np.random.default_rng(42)
    out = stage.run(t, params, {}, {}, rng)

    assert out.morphology is not None
    assert out.morphology.n_nodes > 0
    # Roots must be positioned at cell somas
    somas = out.positions
    roots = np.flatnonzero(out.morphology.parent < 0)
    for r in roots:
        c = out.morphology.cell[r]
        assert np.allclose(out.morphology.xyz[r], somas[c], atol=1e-5)

    # Connectivity is completely preserved
    assert np.array_equal(out.connectivity.pre, init_pre)
    assert np.array_equal(out.connectivity.post, init_post)


def test_instantiate_morphologies_neutral_noop():
    stage = STAGE_REGISTRY["instantiate_morphologies"]()
    t = _make_tissue(3)

    # No catalogue
    res = stage.run(t, {"catalogue": None}, {}, {}, np.random.default_rng(0))
    assert getattr(res, "morphology", None) is None

    # Zero attachment probability
    res2 = stage.run(t, {"catalogue": FIXTURES_DIR, "attachment_prob": 0.0}, {}, {}, np.random.default_rng(0))
    assert getattr(res2, "morphology", None) is None


def test_instantiate_morphologies_determinism():
    stage = STAGE_REGISTRY["instantiate_morphologies"]()
    params = {"catalogue": FIXTURES_DIR, "attachment_prob": 1.0}

    t1 = _make_tissue(3)
    out1 = stage.run(t1, params, {}, {}, np.random.default_rng(123))

    t2 = _make_tissue(3)
    out2 = stage.run(t2, params, {}, {}, np.random.default_rng(123))

    assert np.allclose(out1.morphology.xyz, out2.morphology.xyz)

    # Different seed -> different coordinates
    t3 = _make_tissue(3)
    out3 = stage.run(t3, params, {}, {}, np.random.default_rng(456))
    diff = (out1.morphology.xyz.shape != out3.morphology.xyz.shape) or not np.allclose(out1.morphology.xyz, out3.morphology.xyz)
    assert diff


def test_instantiate_morphologies_declared_cost():
    N = 100
    params = {"attachment_prob": 1.0, "n_neurites": 1, "max_nodes": 10000}
    declared_bytes, declared_ops = InstantiateMorphologies.cost(N, 0, params)

    t = _make_tissue(6)
    # Scale up positions to N cells
    t_large = Tissue.empty()
    t_large.add_cells(N, positions=np.zeros((N, 3)))
    stage = STAGE_REGISTRY["instantiate_morphologies"]()
    run_params = {"catalogue": FIXTURES_DIR, "attachment_prob": 1.0, "n_neurites": 1}

    tracemalloc.start()
    stage.run(t_large, run_params, {}, {}, np.random.default_rng(0))
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    assert declared_bytes / 3 <= peak <= declared_bytes * 3
