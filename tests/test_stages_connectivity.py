import numpy as np
import pytest

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import Stage
from neurogenesis.params import Const

def test_connectivity_hand_remap():
    t = Tissue.empty()
    # add cells
    stage_place = Stage(name="p", operator="place_by_hand", params={"positions": Const([[0,0,0], [1,1,1], [2,2,2]])})
    t = stage_place.run(t, {}, {}, np.random.default_rng(0))
    assert len(t.alive) == 3
    
    stage_conn = Stage(name="c", operator="connect_by_hand", params={"pre": Const([0, 1]), "post": Const([1, 2]), "weight": Const(100), "delay": Const(2)})
    t = stage_conn.run(t, {}, {}, np.random.default_rng(0))
    
    assert len(t.connectivity.pre) == 2
    assert t.connectivity.pre[0] == 0
    assert t.connectivity.post[0] == 1
    
    # kill middle cell
    t.kill(np.array([False, True, False]))
    t.compact()
    
    assert len(t.alive) == 2
    # Only synapse should be dead
    assert len(t.connectivity.pre) == 0

def test_cost_declarations():
    stage = Stage(name="p", operator="place_by_hand", params={})
    assert stage.cost(10, 0)[0] > 0
    
    stage2 = Stage(name="g", operator="grow_axons", params={})
    assert stage2.cost(10, 5)[0] > 0

def test_determinism_grow_axons():
    rng = np.random.default_rng(42)
    pos = rng.uniform(0.0, 0.2, (10, 3))
    t1 = Tissue.empty()
    t1.add_cells(10, positions=pos, region=np.array([0,0,0,0,0,1,1,1,1,1]))
    
    t2 = Tissue.empty()
    t2.add_cells(10, positions=pos, region=np.array([0,0,0,0,0,1,1,1,1,1]))
    
    genome = {
        "guidance": {
            (0, 1): {"c": [0,0,0], "B": np.eye(3).tolist(), "sigma": 0.2, "p0": 0.8, "w": 50, "wc": 100, "inh": 1.0}
        }
    }
    
    stage = Stage(name="g", operator="grow_axons", params={"projections": Const([[0, 1]]), "region_map": Const({0: 0, 1: 1})})
    
    res1 = stage.run(t1, genome, {}, np.random.default_rng(42))
    res2 = stage.run(t2, genome, {}, np.random.default_rng(42))
    
    assert np.array_equal(res1.connectivity.pre, res2.connectivity.pre)
    assert np.array_equal(res1.connectivity.weight, res2.connectivity.weight)
    
    res3 = stage.run(Tissue.empty().subset([]), genome, {}, np.random.default_rng(42))
    res3.add_cells(10, positions=pos, region=np.array([0,0,0,0,0,1,1,1,1,1]))
    res3 = stage.run(res3, genome, {}, np.random.default_rng(43))
    
    assert not np.array_equal(res1.connectivity.pre, res3.connectivity.pre) or not np.array_equal(res1.connectivity.weight, res3.connectivity.weight)

