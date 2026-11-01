import numpy as np
import pytest

from neurogenesis.tissue import Tissue
from neurogenesis.params import Const
from neurogenesis.stages.migration import MigrateStage, SortStage
from neurogenesis.stages.base import STAGE_REGISTRY

def test_migrate_stage_registration():
    assert "migrate" in STAGE_REGISTRY
    assert STAGE_REGISTRY["migrate"] == MigrateStage

def test_sort_stage_registration():
    assert "sort" in STAGE_REGISTRY
    assert STAGE_REGISTRY["sort"] == SortStage

def test_migrate_cost():
    N = 100
    E = 0
    params = {}
    bytes_cost, ops_cost = MigrateStage.cost(N, E, params)
    assert bytes_cost > 0
    assert ops_cost > 0

def test_sort_cost():
    N = 100
    E = 0
    params = {}
    bytes_cost, ops_cost = SortStage.cost(N, E, params)
    assert bytes_cost > 0
    assert ops_cost > 0

def test_migrate_determinism():
    tissue = Tissue.empty()
    positions = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    tissue.add_cells(2, positions=positions)
    
    stage = MigrateStage()
    rng1 = np.random.default_rng(42)
    tissue1 = stage.run(tissue.subset(np.arange(2)), {"speed": Const(0.5), "direction": Const(np.array([1.0, 0.0, 0.0]))}, {}, {}, rng1)
    
    rng2 = np.random.default_rng(42)
    tissue2 = stage.run(tissue.subset(np.arange(2)), {"speed": Const(0.5), "direction": Const(np.array([1.0, 0.0, 0.0]))}, {}, {}, rng2)
    
    np.testing.assert_allclose(tissue1.positions, tissue2.positions)

def test_migrate_linear():
    tissue = Tissue.empty()
    tissue.add_cells(1, positions=np.array([[0.0, 0.0, 0.0]]))
    
    stage = MigrateStage()
    rng = np.random.default_rng(42)
    
    tissue = stage.run(
        tissue,
        {"speed": Const(2.0), "direction": Const(np.array([0.0, 1.0, 0.0]))},
        {}, {}, rng
    )
    
    np.testing.assert_allclose(tissue.positions[0], [0.0, 2.0, 0.0])

def test_migrate_radial():
    tissue = Tissue.empty()
    tissue.add_cells(1, positions=np.array([[2.0, 0.0, 0.0]]))
    
    stage = MigrateStage()
    rng = np.random.default_rng(42)
    
    tissue = stage.run(
        tissue,
        {"speed": Const(1.0), "radial": Const(True), "target": Const(np.array([0.0, 0.0, 0.0]))},
        {}, {}, rng
    )
    
    # Target is origin. Diff is position - target = (2,0,0) - (0,0,0) = (2,0,0)
    # Direction is (1,0,0). Step is 1.0 * (1,0,0). New pos = (3,0,0).
    np.testing.assert_allclose(tissue.positions[0], [3.0, 0.0, 0.0])

def test_sort_inside_out():
    tissue = Tissue.empty()
    # 3 cells born at stage 3, 1, 2
    # They are at z = 0, 1, 2
    tissue.add_cells(3, 
                     positions=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 2.0]]),
                     birth_stage=np.array([3, 1, 2]))
    
    stage = SortStage()
    rng = np.random.default_rng(42)
    
    tissue = stage.run(
        tissue,
        {"axis": Const(np.array([0.0, 0.0, 1.0])), "key": Const("birth_stage")},
        {}, {}, rng
    )
    
    # Sort values (birth_stage): [3, 1, 2]
    # sort_idx: [1, 2, 0] (i.e. cell 1 has smallest birth_stage, then cell 2, then cell 0)
    # projections: [0, 1, 2]
    # sorted_projections: [0, 1, 2]
    # new_positions:
    # cell 1 gets sorted_projections[0] (z=0)
    # cell 2 gets sorted_projections[1] (z=1)
    # cell 0 gets sorted_projections[2] (z=2)
    
    np.testing.assert_allclose(tissue.positions[1], [0.0, 0.0, 0.0], atol=1e-7)
    np.testing.assert_allclose(tissue.positions[2], [0.0, 0.0, 1.0], atol=1e-7)
    np.testing.assert_allclose(tissue.positions[0], [0.0, 0.0, 2.0], atol=1e-7)
