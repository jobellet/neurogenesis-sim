import numpy as np
import pytest
from neurogenesis.tissue import Tissue
from neurogenesis.stages.population import SeedCells, Proliferate, Apoptosis
from neurogenesis.geometry.primitives import Box

def test_seed_cells():
    tissue = Tissue.empty()
    rng = np.random.default_rng(42)
    stage = SeedCells()
    
    # Test simple seed
    params = {"N": 10, "position": [1.0, 2.0, 3.0]}
    tissue = stage.run(tissue, params, {}, {}, rng)
    
    assert len(tissue.alive) == 10
    assert np.allclose(tissue.positions[0], [1.0, 2.0, 3.0])
    
    # Test neutral / 0 seed
    params_neutral = {"N": 0}
    tissue = stage.run(tissue, params_neutral, {}, {}, rng)
    assert len(tissue.alive) == 10 # unchanged
    
    # Test geometry seed
    tissue2 = Tissue.empty()
    box = Box([0, 0, 0], [2, 2, 2]) # extends -1 to 1
    params_geom = {"N": 5, "geometry": box}
    tissue2 = stage.run(tissue2, params_geom, {}, {}, rng)
    
    assert len(tissue2.alive) == 5
    assert np.all(tissue2.positions >= -1.0) and np.all(tissue2.positions <= 1.0)

def test_proliferate():
    tissue = Tissue.empty()
    rng = np.random.default_rng(42)
    
    # Seed 2 cells
    tissue.add_cells(2, positions=np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]))
    
    stage = Proliferate()
    
    # Test neutral params (prob 0)
    tissue = stage.run(tissue, {"prob": 0.0}, {}, {}, rng)
    assert len(tissue.alive) == 2
    
    # Test prob 1
    tissue = stage.run(tissue, {"prob": 1.0, "jitter": 1.0}, {}, {}, rng)
    assert len(tissue.alive) == 4
    
    # The new cells are added at the end. Their parent_ids should point to 0 and 1.
    assert tissue.parent_id[2] == 0
    assert tissue.parent_id[3] == 1
    
    # clone_ids should be preserved. founder clone_ids are 0 and 1.
    assert tissue.clone_id[2] == 0
    assert tissue.clone_id[3] == 1
    
    # New cell_ids are assigned
    assert tissue.cell_id[2] == 2
    assert tissue.cell_id[3] == 3
    # Generation increments via birth_stage
    assert tissue.birth_stage[2] == 1
    assert tissue.birth_stage[3] == 1

def test_apoptosis():
    tissue = Tissue.empty()
    rng = np.random.default_rng(42)
    
    tissue.add_cells(5, positions=np.zeros((5, 3)))
    
    stage = Apoptosis()
    
    # Neutral prob
    tissue = stage.run(tissue, {"prob": 0.0}, {}, {}, rng)
    assert len(tissue.alive) == 5
    
    # Prob 1
    tissue = stage.run(tissue, {"prob": 1.0}, {}, {}, rng)
    assert len(tissue.alive) == 0 # all dead and compacted
    assert len(tissue.positions) == 0

def test_determinism():
    tissue1 = Tissue.empty()
    tissue2 = Tissue.empty()
    
    seed = SeedCells()
    prolif = Proliferate()
    apopt = Apoptosis()
    
    def run_dev(t, rng):
        t = seed.run(t, {"N": 10, "position": [0,0,0]}, {}, {}, rng)
        t = prolif.run(t, {"prob": 0.5, "jitter": 0.1}, {}, {}, rng)
        t = apopt.run(t, {"prob": 0.2}, {}, {}, rng)
        return t
        
    rng1 = np.random.default_rng(123)
    t1 = run_dev(tissue1, rng1)
    
    rng2 = np.random.default_rng(123)
    t2 = run_dev(tissue2, rng2)
    
    assert len(t1.alive) == len(t2.alive)
    assert np.allclose(t1.positions, t2.positions)
    assert np.array_equal(t1.cell_id, t2.cell_id)

def test_cost_declarations():
    c_seed = SeedCells.cost(0, 0, {"N": 100})
    assert c_seed[0] > 0 and c_seed[1] > 0
    
    c_prolif = Proliferate.cost(100, 0, {})
    assert c_prolif[0] > 0 and c_prolif[1] > 0
    
    c_apopt = Apoptosis.cost(100, 0, {})
    assert c_apopt[0] > 0 and c_apopt[1] > 0


def test_apoptosis_density_trophic():
    tissue = Tissue.empty()
    rng = np.random.default_rng(42)
    
    # Add cells close to each other
    tissue.add_cells(3, positions=np.array([[0,0,0], [0.1,0,0], [0.2,0,0]]))
    tissue.add_cells(1, positions=np.array([[10,0,0]])) # far away
    
    stage = Apoptosis()
    # Density kill: radius 1.0, max_density 1
    tissue = stage.run(tissue, {"density_radius": 1.0, "max_density": 1}, {}, {}, rng)
    
    # The first 3 cells are within radius 1 of each other. They each have 2 neighbors.
    # The last cell has 0 neighbors.
    # So the first 3 should die, leaving only the 4th cell.
    assert len(tissue.alive) == 1
    assert tissue.positions[0, 0] == 10.0

    # Test trophic
    tissue = Tissue.empty()
    tissue.add_cells(2, positions=np.zeros((2, 3)))
    tissue.connectivity.pre = np.array([0], dtype=np.int32)
    tissue.connectivity.post = np.array([1], dtype=np.int32)
    tissue.connectivity.weight = np.array([1], dtype=np.int32)
    tissue.connectivity.delay = np.array([1], dtype=np.int32)
    
    # Cell 0 has 1 output, 0 input. Cell 1 has 0 output, 1 input.
    # Require 1 output
    t2 = stage.run(tissue.subset(np.arange(2)), {"min_outputs": 1}, {}, {}, rng)
    assert len(t2.alive) == 1
    assert t2.cell_id[0] == 0
    
    # Require 1 input
    t3 = stage.run(tissue.subset(np.arange(2)), {"min_inputs": 1}, {}, {}, rng)
    assert len(t3.alive) == 1
    assert t3.cell_id[0] == 1
