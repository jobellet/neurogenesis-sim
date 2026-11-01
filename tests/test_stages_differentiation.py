import pytest
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.differentiation import Express, Differentiate
from neurogenesis.params import Const

def test_express_neutral():
    stage = Express()
    t = Tissue.empty(K=2)
    t.add_cells(10, expression=np.zeros((10, 2), dtype=np.float32), K=2)
    
    # Neutral params (no K)
    t_out = stage.run(t, {}, {}, {}, np.random.default_rng(42))
    assert t_out.expression.shape == (10, 2)
    assert np.allclose(t_out.expression, 0.0)
    
def test_express_morphogen():
    stage = Express()
    t = Tissue.empty(K=2)
    t.add_cells(3, positions=np.array([[0,0,0], [1,0,0], [2,0,0]]), expression=np.zeros((3, 2), dtype=np.float32), K=2)
    
    # K=2, morphogen field is just a constant 2.0 everywhere for simplicity
    params = {
        "K": Const(2),
        "weights": Const(np.zeros((2, 2)).tolist()),
        "dt": Const(1.0),
        "decay": Const(0.0),
        "morphogens": [
            {
                "field": Const(2.0),
                "weights": [1.0, -1.0]
            }
        ]
    }
    
    t_out = stage.run(t, params, {}, {}, np.random.default_rng(42))
    assert t_out.expression.shape == (3, 2)
    
    # morphogen input = 2.0 * [1.0, -1.0] = [2.0, -2.0]
    # activation = sigmoid([2.0, -2.0])
    expected_act = 1.0 / (1.0 + np.exp(-np.array([2.0, -2.0])))
    
    assert np.allclose(t_out.expression[0], expected_act)

def test_express_cost():
    bytes_cost, ops_cost = Express.cost(100, 0, {"K": Const(5)})
    assert bytes_cost == 100 * 5 * 8
    assert ops_cost == 100 * 25 * 4

def test_differentiate_neutral():
    stage = Differentiate()
    t = Tissue.empty(K=2)
    t.add_cells(3, cell_type=np.zeros(3, dtype=np.int32))
    
    t_out = stage.run(t, {}, {}, {}, np.random.default_rng(42))
    assert np.allclose(t_out.cell_type, 0)

def test_differentiate_basic():
    stage = Differentiate()
    t = Tissue.empty(K=2)
    
    # We want expression based matching.
    # We will test two cell types based on expression of gene 0 and 1
    expr = np.array([[0.1, 0.9], [0.8, 0.2], [0.5, 0.5]], dtype=np.float32)
    t.add_cells(3, expression=expr)
    
    params = {
        "types": Const([
            {
                "type_id": 1,
                "condition": "expr[0] > 0.6",
                "sign": 1,
                "base_weight": 5,
                "mode": 1
            },
            {
                "type_id": 2,
                "condition": "expr[1] > 0.6",
                "sign": -1,
                "base_weight": 2,
                "mode": 2
            }
        ])
    }
    
    t_out = stage.run(t, params, {}, {}, np.random.default_rng(42))
    
    # Cell 0: expr=[0.1, 0.9] -> matches type 2
    # Cell 1: expr=[0.8, 0.2] -> matches type 1
    # Cell 2: expr=[0.5, 0.5] -> matches none -> retains type 0, default sign? Or just leaves it alone
    
    assert t_out.cell_type[0] == 2
    assert t_out.sign[0] == -1
    assert t_out.base_weight[0] == -2  # Sign is -1, base_weight is 2
    assert t_out.mode[0] == 2
    
    assert t_out.cell_type[1] == 1
    assert t_out.sign[1] == 1
    assert t_out.base_weight[1] == 5
    assert t_out.mode[1] == 1
    
    assert t_out.cell_type[2] == 0  # untouched
    assert t_out.sign[2] == 1 # default is 1
    assert t_out.base_weight[2] == 1 # default
    assert t_out.mode[2] == 0

def test_differentiate_cost():
    bytes_cost, ops_cost = Differentiate.cost(100, 0, {"types": Const([{}, {}, {}])})
    assert bytes_cost == 100 * 4
    assert ops_cost == 100 * 3 * 5

def test_differentiate_updates_base_weight_sign():
    stage = Differentiate()
    t = Tissue.empty(K=2)
    t.add_cells(1)
    # Default is exc, sign=1, base_weight=1
    assert t.sign[0] == 1
    assert t.base_weight[0] == 1
    
    params = {
        "types": Const([
            {
                "type_id": 1,
                "condition": "True",
                "sign": -1
            }
        ])
    }
    
    t_out = stage.run(t, params, {}, {}, np.random.default_rng(42))
    assert t_out.cell_type[0] == 1
    assert t_out.sign[0] == -1
    assert t_out.base_weight[0] == -1

def test_express_determinism():
    stage = Express()
    t1 = Tissue.empty(K=2)
    t1.add_cells(5, positions=np.random.default_rng(1).uniform(0, 1, (5, 3)), expression=np.zeros((5, 2), dtype=np.float32), K=2)
    
    t2 = Tissue.empty(K=2)
    t2.add_cells(5, positions=t1.positions.copy(), expression=np.zeros((5, 2), dtype=np.float32), K=2)
    
    params = {
        "K": Const(2),
        "weights": Const([[0.5, -0.2], [0.1, 0.9]]),
        "radius": Const(0.5),
        "neighbor_weights": Const([[0.2, 0.0], [0.0, 0.2]])
    }
    
    rng1 = np.random.default_rng(123)
    rng2 = np.random.default_rng(123)
    
    t1_out = stage.run(t1, params, {}, {}, rng1)
    t2_out = stage.run(t2, params, {}, {}, rng2)
    
    assert np.array_equal(t1_out.expression, t2_out.expression)

def test_differentiate_determinism():
    stage = Differentiate()
    t1 = Tissue.empty(K=2)
    t1.add_cells(5, expression=np.random.default_rng(1).uniform(0, 1, (5, 2)).astype(np.float32), K=2)
    
    t2 = Tissue.empty(K=2)
    t2.add_cells(5, expression=t1.expression.copy(), K=2)
    
    params = {
        "types": Const([
            {
                "type_id": 1,
                "condition": "expr[0] > 0.5",
                "sign": 1
            },
            {
                "type_id": 2,
                "condition": "expr[0] <= 0.5",
                "sign": -1
            }
        ])
    }
    
    rng1 = np.random.default_rng(123)
    rng2 = np.random.default_rng(123)
    
    t1_out = stage.run(t1, params, {}, {}, rng1)
    t2_out = stage.run(t2, params, {}, {}, rng2)
    
    assert np.array_equal(t1_out.cell_type, t2_out.cell_type)
    assert np.array_equal(t1_out.sign, t2_out.sign)

