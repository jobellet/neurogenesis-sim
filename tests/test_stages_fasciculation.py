import copy
import numpy as np
import pytest

from neurogenesis.stages.fasciculation import FasciculateStage, ChoicePointStage
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.geometry.primitives import Box
from neurogenesis.arbors import ArborStore


def test_fasciculate_neutral_is_noop():
    t = Tissue.empty()
    t.add_cells(5, positions=np.zeros((5, 3)))
    out = FasciculateStage().run(copy.deepcopy(t), {}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(out.positions, t.positions)
    assert FasciculateStage.cost(10, 20, {}) == (10 * 64 + 20 * 32, 10 * 50 + 20 * 20)


def test_choice_point_neutral_is_noop():
    t = Tissue.empty()
    t.add_cells(5, positions=np.zeros((5, 3)))
    out = ChoicePointStage().run(copy.deepcopy(t), {}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(out.positions, t.positions)
    assert ChoicePointStage.cost(10, 20, {}) == (10 * 32 + 20 * 16, 10 * 20 + 20 * 10)


def test_choice_point_switches_expression_in_geometry():
    t = Tissue.empty()
    t.add_cells(4, positions=np.array([[0, 0, 0], [0.5, 0.5, 0.5], [2, 2, 2], [3, 3, 3]], dtype=np.float32))
    t.expression = np.zeros((4, 2), dtype=np.float32)
    box = Box([0, 0, 0], [1, 1, 1])
    
    stage = ChoicePointStage()
    params = {"geometry": box, "switch_channel": 1, "switch_value": 0.9}
    out = stage.run(t, params, {}, {}, np.random.default_rng(0))
    
    # Cells 0 and 1 are inside Box, cells 2 and 3 are outside
    assert out.expression[0, 1] == pytest.approx(0.9)
    assert out.expression[1, 1] == pytest.approx(0.9)
    assert out.expression[2, 1] == 0.0
    assert out.expression[3, 1] == 0.0


def test_fasciculate_arbors_steers_towards_pioneers():
    t = Tissue.empty()
    t.add_cells(2, positions=np.array([[0, 0, 0], [0, 0.2, 0]], dtype=np.float32), cell_type=np.array([0, 1], dtype=np.int32))
    
    # Build a simple morphology:
    # Cell 0 (pioneer) goes along +x: node 0 at (0,0,0), node 1 at (1,0,0)
    # Cell 1 (follower) node 2 at (0, 0.2, 0), node 3 at (0.5, 0.2, 0)
    xyz = np.array([[0, 0, 0], [1.0, 0, 0], [0, 0.2, 0], [0.5, 0.2, 0]], dtype=np.float32)
    parent = np.array([-1, 0, -1, 2], dtype=np.int32)
    cell = np.array([0, 0, 1, 1], dtype=np.int32)
    compartment = np.array([1, 2, 1, 2], dtype=np.int8)
    radius = np.ones(4, dtype=np.float32)
    t.morphology = ArborStore(xyz=xyz, radius=radius, parent=parent, cell=cell, compartment=compartment)

    stage = FasciculateStage()
    params = {
        "adhesion_matrix": [[1.0, 1.0], [1.0, 1.0]],
        "radius": 0.6
    }
    
    init_pos = t.morphology.xyz.copy()
    out = stage.run(t, params, {}, {}, np.random.default_rng(0))
    # Node 3 is near node 1 and should be pulled in tangent direction (+x)
    assert out.morphology.xyz[3, 0] > init_pos[3, 0]
