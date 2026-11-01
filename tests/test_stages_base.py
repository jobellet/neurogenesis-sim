import numpy as np
from typing import Dict, Any

from neurogenesis.stages.base import Stage, register_stage, run_schedule
from neurogenesis.tissue import Tissue
from neurogenesis.params import Const

@register_stage("mock_stage")
class MockStage:
    @staticmethod
    def cost(N: int, E: int, params: Dict[str, Any]) -> tuple[int, int]:
        return (N * 10, E * 5)
        
    def __call__(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        tissue.add_cells(1)
        return tissue

def test_stage_cost():
    stage = Stage(name="test", operator="mock_stage", params={"p1": Const(1.0)})
    bytes_cost, ops_cost = stage.cost(100, 200)
    assert bytes_cost == 1000
    assert ops_cost == 1000

def test_run_schedule_rng_isolation():
    drawn = []
    
    @register_stage("rng_stage")
    class RNGStage:
        def __call__(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
            drawn.append(rng.random())
            return tissue
            
    project2 = {
        "schedule": [
            {"operator": "rng_stage", "repeat": 1},
            {"operator": "rng_stage", "repeat": 1}
        ]
    }
    run_schedule(project2, {}, 42)
    assert len(drawn) == 2
    d1, d2 = drawn
    
    drawn.clear()
    
    project3 = {
        "schedule": [
            {"operator": "rng_stage", "repeat": 1},
            {"operator": "mock_stage", "repeat": 1},
            {"operator": "rng_stage", "repeat": 1}
        ]
    }
    run_schedule(project3, {}, 42)
    
    d1_new, d3_new = drawn
    assert d1 == d1_new
    # Since d3_new is drawn in stage_idx=2 (3rd stage), it's not equal to d2 which was drawn in stage_idx=1
    assert d3_new != d2 

def test_run_schedule_checkpoints():
    @register_stage("count_stage")
    class CountStage:
        def __call__(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
            tissue.add_cells(1)
            return tissue
            
    project = {
        "schedule": [
            {"operator": "count_stage", "repeat": 2}
        ]
    }
    
    checkpoints = run_schedule(project, {}, 42, checkpoints=True)
    
    assert len(checkpoints) == 2
    # At checkpoint 0 (repeat 0), there should be 1 cell
    assert len(checkpoints[0].positions) == 1
    # At checkpoint 1 (repeat 1), there should be 2 cells
    assert len(checkpoints[1].positions) == 2
    
    # ensure copy works and they are separate
    assert checkpoints[0] is not checkpoints[1]


def test_schedule_cost():
    from neurogenesis.stages.base import schedule_cost
    project = {
        "schedule": [
            {"operator": "mock_stage", "repeat": 2},
            {"operator": "mock_stage", "repeat": 1}
        ]
    }
    # mock_stage cost: (N * 10, E * 5)
    # Total repeat = 3
    # N=100, E=200 => (1000, 1000) * 3 = (3000, 3000)
    bytes_cost, ops_cost = schedule_cost(project, 100, 200)
    assert bytes_cost == 3000
    assert ops_cost == 3000
import sys
import importlib
import neurogenesis.stages
from neurogenesis.stages.base import STAGE_REGISTRY

def test_auto_discovery():
    # If the __init__.py executes properly, any modules in the directory
    # would be imported. We don't have modules by default, but we can check it ran.
    # We can also mock write a module to disk, reload, and verify.
    with open("neurogenesis/stages/mock_stage_discovery.py", "w") as f:
        f.write('from neurogenesis.stages.base import register_stage\n')
        f.write('@register_stage("mock_discovery")\n')
        f.write('class MockDiscoveryStage:\n')
        f.write('    pass\n')
    
    importlib.invalidate_caches()
    importlib.reload(neurogenesis.stages)
    
    assert "mock_discovery" in STAGE_REGISTRY
    
    # cleanup
    import os
    os.remove("neurogenesis/stages/mock_stage_discovery.py")
