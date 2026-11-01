import pytest
import numpy as np
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.stages.refinement import PruneStage, ScaleStage, MyelinateStage, RefineByActivityStage

@pytest.fixture
def base_tissue():
    t = Tissue.empty()
    t.add_cells(3, positions=np.array([[0,0,0], [1,0,0], [2,0,0]], dtype=np.float64))
    
    pre = np.array([0, 0, 1, 1], dtype=np.int32)
    post = np.array([1, 2, 0, 2], dtype=np.int32)
    weight = np.array([10, -5, 20, -15], dtype=np.int32)
    delay = np.array([10, 10, 10, 10], dtype=np.int32)
    
    t.connectivity = SparseConnectivity(pre, post, weight, delay)
    return t

def test_prune_stage(base_tissue):
    stage = PruneStage()
    rng = np.random.default_rng(0)
    
    # threshold 10 -> -5 is pruned, but what about 10? keep_mask is abs_weights >= threshold.
    # So 10 is kept, -5 is removed.
    params = {"threshold": 10}
    t = stage.run(base_tissue, params, {}, {}, rng)
    
    assert len(t.connectivity.pre) == 3
    assert list(t.connectivity.weight) == [10, 20, -15]

def test_scale_stage(base_tissue):
    stage = ScaleStage()
    rng = np.random.default_rng(0)
    
    # post 0: incoming 20 (from 1)
    # post 1: incoming 10 (from 0)
    # post 2: incoming -5 (from 0), -15 (from 1) -> sum abs = 20
    
    params = {"target": 40}
    t = stage.run(base_tissue, params, {}, {}, rng)
    
    # scale factor post 0: 40/20 = 2 -> 20 * 2 = 40
    # scale factor post 1: 40/10 = 4 -> 10 * 4 = 40
    # scale factor post 2: 40/20 = 2 -> -5 * 2 = -10, -15 * 2 = -30. Sum of abs = 40.
    
    w = list(t.connectivity.weight)
    assert w == [40, -10, 40, -30]

def test_myelinate_stage(base_tissue):
    stage = MyelinateStage()
    rng = np.random.default_rng(0)
    
    params = {"factor": 0.5}
    t = stage.run(base_tissue, params, {}, {}, rng)
    
    assert list(t.connectivity.delay) == [5, 5, 5, 5]

def test_refine_by_activity_stage(base_tissue):
    # just run it to make sure it doesn't crash and actually modifies weights
    stage = RefineByActivityStage()
    rng = np.random.default_rng(0)
    
    # Need to make sure cells can spike, set mode=1 (poisson) so they fire
    base_tissue.mode = np.array([1, 1, 1], dtype=np.int32)
    base_tissue.poisson_hz = np.array([1000.0, 1000.0, 1000.0], dtype=np.float64)
    
    params = {"ticks": 10, "rule": "stdp", "A_plus": 1.0, "A_minus": 1.0, "w_max": 100.0}
    
    # Store original weights
    orig_w = base_tissue.connectivity.weight.copy()
    
    t = stage.run(base_tissue, params, {}, {}, rng)
    
    assert len(t.connectivity.weight) == len(orig_w)
    
    # Check cost declarations
    c1, c2 = stage.cost(3, 4, {"ticks": 10})
    assert c1 > 0 and c2 > 0

