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


def _c2_tissue(N=20, K=3, seed=7):
    t = Tissue.empty(K=K)
    rng0 = np.random.default_rng(seed)
    t.add_cells(N, positions=rng0.random((N, 3)), cell_type=np.arange(N, dtype=np.int32) % 3,
                expression=rng0.random((N, K)).astype(np.float32))
    return t


def _fingerprint(t):
    import hashlib
    h = hashlib.sha256()
    for name in ["positions", "cell_id", "parent_id", "clone_id", "cell_type", "region", "expression", "sign",
                 "mode", "shift_v", "base_weight", "threshold", "alive"]:
        a = getattr(t, name)
        if name == "base_weight":  # recorded when add_cells still widened base_weight to int64; values unchanged
            a = a.astype(np.int64)
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def test_proliferate_neutral_defaults_match_previous_implementation():
    """Fingerprint recorded with the implementation on main before C2 options were added (same seed)."""
    from neurogenesis.params import Const
    t = _c2_tissue()
    rng = np.random.default_rng(2024)
    stage = Proliferate()
    for _ in range(3):
        t = stage.run(t, {"prob": Const(0.4), "jitter": Const(0.05)}, {}, {}, rng)
    t = stage.run(t, {"prob": Const(0.3), "new_type": Const(5)}, {}, {}, rng)
    neutral = {"prob": Const(0.0), "max_cells": None, "asymmetric_prob": Const(0.0), "expression_noise": Const(0.0)}
    t = stage.run(t, neutral, {}, {}, rng)
    assert len(t.alive) == 90
    assert _fingerprint(t) == "155ea33f54a749f6ddba0b444f6b9696efdcf71d927926a5b777553fc07c6e19"


def test_proliferate_generation_and_birth_stage():
    t = Tissue.empty()
    t.add_cells(1)
    stage = Proliferate()
    rng = np.random.default_rng(0)
    for _ in range(3):
        t = stage.run(t, {"prob": 1.0}, {}, {}, rng)
    assert len(t.alive) == 8
    # Every cell has gone through all three divisions (the parent row is one of the daughters).
    assert t.generation.tolist() == [3] * 8
    # birth_stage is birth order: one more per proliferate call, founders at 0.
    assert t.birth_stage.tolist() == [0, 1, 2, 2, 3, 3, 3, 3]
    t = stage.run(t, {"prob": 1.0, "birth_stage": 7}, {}, {}, rng)
    assert t.birth_stage[8:].tolist() == [7] * 8
    assert t.generation.tolist() == [4] * 16


def test_proliferate_skips_dead_cells():
    t = Tissue.empty()
    t.add_cells(4)
    t.kill(np.array([True, False, True, False]))
    t = Proliferate().run(t, {"prob": 1.0}, {}, {}, np.random.default_rng(0))
    assert t.parent_id[4:].tolist() == [1, 3]


def test_proliferate_divides_only_cycling_cells_and_matches_all_cycling_bit_for_bit():
    # With every cell cycling (the default), behaviour is bit-for-bit identical.
    t_all = _c2_tissue(N=25, K=2, seed=9)
    assert np.all(t_all.cycling)
    t_explicit = _c2_tissue(N=25, K=2, seed=9)
    t_explicit.cycling = np.ones(25, dtype=bool)
    a = Proliferate().run(t_all, {"prob": 0.65, "jitter": 0.1}, {}, {}, np.random.default_rng(77))
    b = Proliferate().run(t_explicit, {"prob": 0.65, "jitter": 0.1}, {}, {}, np.random.default_rng(77))
    assert _fingerprint(a) == _fingerprint(b)
    assert np.all(a.cycling)

    # Non-cycling cells (including cells placed by place_by_hand) never divide and keep their generation.
    from neurogenesis.stages.connectivity import PlaceByHand
    t = Tissue.empty()
    t.add_cells(4, cycling=np.array([True, False, True, False]))
    t = PlaceByHand().run(t, {"positions": [[5.0, 0.0, 0.0]]}, {}, {}, np.random.default_rng(0))
    assert t.cycling.tolist() == [True, False, True, False, False]
    t = Proliferate().run(t, {"prob": 1.0}, {}, {}, np.random.default_rng(0))
    assert len(t.alive) == 7
    assert t.parent_id[5:].tolist() == [0, 2]
    assert t.generation.tolist() == [1, 0, 1, 0, 0, 1, 1]
    assert t.cycling.tolist() == [True, False, True, False, False, True, True]


def test_proliferate_max_cells_bound_exact():
    from neurogenesis.params import Const
    stage = Proliferate()
    t = Tissue.empty()
    t.add_cells(100)
    t.kill(np.arange(100) < 10)
    t = stage.run(t, {"prob": 1.0, "max_cells": Const(150)}, {}, {}, np.random.default_rng(3))
    assert int(np.sum(t.alive)) == 150
    parents = t.parent_id[100:]
    assert len(np.unique(parents)) == 60 and np.all(parents >= 10)
    # Already at the bound: no division.
    n = len(t.alive)
    t = stage.run(t, {"prob": 1.0, "max_cells": 150}, {}, {}, np.random.default_rng(4))
    assert len(t.alive) == n
    # Bound not reached: identical to the unbounded run.
    a = stage.run(_c2_tissue(), {"prob": 0.5, "max_cells": 1000}, {}, {}, np.random.default_rng(5))
    b = stage.run(_c2_tissue(), {"prob": 0.5}, {}, {}, np.random.default_rng(5))
    assert _fingerprint(a) == _fingerprint(b)


def test_proliferate_asymmetric_division():
    stage = Proliferate()
    t = Tissue.empty()
    t.add_cells(2000, cell_type=np.full(2000, 1, dtype=np.int32))
    t = stage.run(t, {"prob": 1.0, "asymmetric_prob": 0.3, "daughter_type": 9}, {}, {}, np.random.default_rng(1))
    assert np.all(t.cell_type[:2000] == 1)  # the parent row keeps the progenitor type
    new_types = t.cell_type[2000:]
    assert set(np.unique(new_types).tolist()) == {1, 9}
    assert abs(np.mean(new_types == 9) - 0.3) < 0.04
    t = Tissue.empty()
    t.add_cells(50, cell_type=np.full(50, 1, dtype=np.int32))
    t = stage.run(t, {"prob": 1.0, "asymmetric_prob": 1.0, "daughter_type": 4}, {}, {}, np.random.default_rng(1))
    assert np.all(t.cell_type[50:] == 4) and np.all(t.cell_type[:50] == 1)
    with pytest.raises(ValueError):
        stage.run(_c2_tissue(), {"prob": 1.0, "asymmetric_prob": 0.5}, {}, {}, np.random.default_rng(1))


def test_proliferate_expression_noise():
    stage = Proliferate()
    t = _c2_tissue(N=3000, K=2)
    t.expression[:] = 0.05
    t = stage.run(t, {"prob": 1.0, "expression_noise": 0.2}, {}, {}, np.random.default_rng(2))
    assert t.expression.dtype == np.float32 and np.all(t.expression >= 0.0)
    # Both daughters perturbed independently; clipping at 0 leaves a point mass there.
    assert not np.array_equal(t.expression[:3000], t.expression[3000:])
    assert 0.3 < np.mean(t.expression == 0.0) < 0.5
    hi = _c2_tissue(N=3000, K=2)
    hi.expression[:] = 10.0
    hi = stage.run(hi, {"prob": 1.0, "expression_noise": 0.2}, {}, {}, np.random.default_rng(2))
    assert abs(np.std(hi.expression) - 0.2) < 0.01 and abs(np.mean(hi.expression) - 10.0) < 0.01


def test_proliferate_options_deterministic():
    params = {"prob": 0.6, "max_cells": 30, "asymmetric_prob": 0.5, "daughter_type": 7, "expression_noise": 0.1}
    a = Proliferate().run(_c2_tissue(), params, {}, {}, np.random.default_rng(11))
    b = Proliferate().run(_c2_tissue(), params, {}, {}, np.random.default_rng(11))
    assert len(a.alive) == 30
    assert _fingerprint(a) == _fingerprint(b)
    assert np.array_equal(a.generation, b.generation) and np.array_equal(a.birth_stage, b.birth_stage)


@pytest.mark.parametrize("params", [{"prob": 1.0}, {"prob": 0.5}, {"prob": 0.5, "max_cells": 25000},
                                    {"prob": 0.5, "asymmetric_prob": 0.5, "daughter_type": 2, "expression_noise": 0.1}])
def test_proliferate_cost_within_factor_3(params):
    import time
    import tracemalloc
    from neurogenesis.params import Const

    def run(N):
        t = _c2_tissue(N=N, K=2)
        p = {k: Const(v) for k, v in params.items()}
        tracemalloc.start()
        t0 = time.perf_counter()
        Proliferate().run(t, p, {}, {}, np.random.default_rng(1))
        dt = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        return peak, dt, Proliferate.cost(N, 0, p)

    peak, _, (declared_bytes, _) = run(20000)
    assert declared_bytes / 3 <= peak <= declared_bytes * 3
    # Time scales like the declared ops (O(N)) within a factor 3.
    small = min(run(50000)[1] for _ in range(3))
    big = min(run(200000)[1] for _ in range(3))
    ratio_ops = Proliferate.cost(200000, 0, params)[1] / Proliferate.cost(50000, 0, params)[1]
    assert ratio_ops / 3 <= big / small <= ratio_ops * 3


def test_population_costs_use_const_or_gene_upper_bound():
    from neurogenesis.params import Const, Gene, Fit
    assert SeedCells.cost(0, 0, {"N": Gene(path=("n",), lo=10, hi=5000, integer=True)}) == \
        SeedCells.cost(0, 0, {"N": Const(5000)})
    assert SeedCells.cost(0, 0, {"N": {"type": "Gene", "path": ["n"], "lo": 1, "hi": 300}}) == \
        SeedCells.cost(0, 0, {"N": 300})
    assert Proliferate.cost(1000, 0, {"prob": Gene(path=("p",), lo=0.0, hi=0.9)}) == \
        Proliferate.cost(1000, 0, {"prob": Const(0.9)})
    assert Proliferate.cost(1000, 0, {"prob": Fit(target="x", init=0.1, lo=0.0, hi=1.0)}) == \
        Proliferate.cost(1000, 0, {"prob": 1.0})
    assert Proliferate.cost(1000, 0, {"prob": 1.0, "max_cells": Gene(path=("m",), lo=1000, hi=1200)}) == \
        Proliferate.cost(1000, 0, {"prob": 1.0, "max_cells": 1200})
    assert Proliferate.cost(1000, 0, {"prob": 1.0, "max_cells": 1200}) < Proliferate.cost(1000, 0, {"prob": 1.0})
