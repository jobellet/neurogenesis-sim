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


from neurogenesis.fields import AnalyticField, LayerStackField
from neurogenesis.stages.migration import _neighbour_pairs


def _random_tissue(N, side, seed=0, types=1):
    rng = np.random.default_rng(seed)
    t = Tissue.empty()
    t.add_cells(N, positions=rng.uniform(0, side, (N, 3)), cell_type=(np.arange(N) % types).astype(np.int32))
    return t


def test_migrate_neutral_params_are_a_no_op():
    t = _random_tissue(50, 1.0)
    before = t.positions.copy()
    MigrateStage().run(t, {"speed": Const(0.0), "chemotaxis": Const(0.0), "min_distance": Const(0.0),
                           "steps": Const(3)}, {}, {}, np.random.default_rng(0))
    np.testing.assert_array_equal(t.positions, before)


def test_migrate_chemotaxis_moves_cells_up_and_down_the_gradient():
    fields = {"cue": AnalyticField("x * x + 2 * y")}  # gradient (2x, 2, 0)
    t = _random_tissue(30, 1.0)
    before = t.positions.copy()
    params = {"chemotaxis_field": Const("cue"), "chemotaxis": Const(0.05), "steps": Const(4)}
    MigrateStage().run(t, params, {}, fields, np.random.default_rng(0))
    cue = fields["cue"].values
    assert np.all(cue(t.positions) > cue(before))
    np.testing.assert_allclose(np.linalg.norm(t.positions - before, axis=1), 0.2, atol=1e-3)  # 4 steps of 0.05
    t2 = _random_tissue(30, 1.0)
    MigrateStage().run(t2, dict(params, chemotaxis=Const(-0.05)), {}, fields, np.random.default_rng(0))
    assert np.all(cue(t2.positions) < cue(before))


def test_migrate_stops_at_target_layer():
    layers = LayerStackField(AnalyticField("z"), thicknesses=[1.0, 1.0, 1.0], labels=[0, 1, 2])
    t = Tissue.empty()
    t.add_cells(3, positions=np.array([[0.0, 0.0, 0.05], [0.0, 0.0, 0.5], [0.0, 0.0, 1.5]]))
    params = {"speed": Const(0.1), "direction": Const(np.array([0.0, 0.0, 1.0])), "steps": Const(40),
              "layer_field": Const("layers"), "target_layer": Const(1)}
    MigrateStage().run(t, params, {}, {"layers": layers}, np.random.default_rng(0))
    labels = layers.values(t.positions)[:, 0]
    np.testing.assert_array_equal(labels, [1, 1, 1])
    assert t.positions[2, 2] == 1.5  # already in the target layer: did not move
    assert np.all(t.positions[:2, 2] < 1.1)  # stopped on entering it


def test_migrate_min_distance_spaces_cells_and_skips_dead_cells():
    t = _random_tissue(500, 1.0)
    t.alive[0] = False
    dead_pos = t.positions[0].copy()
    MigrateStage().run(t, {"min_distance": Const(0.1), "steps": Const(50)}, {}, {}, np.random.default_rng(0))
    alive = np.flatnonzero(t.alive)
    _, _, d, _ = _neighbour_pairs(t.positions[alive], 0.1)
    assert d.min() >= 0.1 * 0.99
    np.testing.assert_array_equal(t.positions[0], dead_pos)


def test_migrate_min_distance_separates_coincident_cells():
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    MigrateStage().run(t, {"min_distance": Const(0.2), "steps": Const(2)}, {}, {}, np.random.default_rng(0))
    np.testing.assert_allclose(np.linalg.norm(t.positions[0] - t.positions[1]), 0.2)


def test_migrate_and_sort_new_modes_are_deterministic():
    fields = {"cue": AnalyticField("x + y")}
    mparams = {"speed": Const(0.01), "chemotaxis_field": Const("cue"), "chemotaxis": Const(0.02),
               "min_distance": Const(0.08), "steps": Const(5)}
    sparams = {"adhesion": Const([[1.0, 0.2], [0.2, 1.0]]), "radius": Const(0.15), "steps": Const(5)}
    for stage, params in ((MigrateStage(), mparams), (SortStage(), sparams)):
        a = stage.run(_random_tissue(300, 1.0, types=2), params, {}, fields, np.random.default_rng(1))
        b = stage.run(_random_tissue(300, 1.0, types=2), params, {}, fields, np.random.default_rng(2))
        np.testing.assert_array_equal(a.positions, b.positions)


def _same_type_fraction(t, radius):
    src, dst, _, _ = _neighbour_pairs(t.positions, radius)
    return np.mean(t.cell_type[src] == t.cell_type[dst])


@pytest.mark.parametrize("cross,gain", [(0.2, 0.08), (-0.5, 0.15)])  # weaker heterotypic adhesion, or repulsion
def test_sort_differential_adhesion_segregates_mixed_types(cross, gain):
    t = _random_tissue(400, 1.0, types=2)
    before = _same_type_fraction(t, 0.15)
    params = {"adhesion": Const([[1.0, cross], [cross, 1.0]]), "radius": Const(0.15), "rate": Const(0.05),
              "steps": Const(60)}
    SortStage().run(t, params, {}, {}, np.random.default_rng(0))
    after = _same_type_fraction(t, 0.15)
    assert before < 0.55 and after > before + gain


def test_sort_uniform_adhesion_does_not_segregate():
    t = _random_tissue(400, 1.0, types=2)
    before = _same_type_fraction(t, 0.15)
    SortStage().run(t, {"adhesion": Const(np.ones((2, 2))), "radius": Const(0.15), "rate": Const(0.05),
                        "steps": Const(60)}, {}, {}, np.random.default_rng(0))
    assert abs(_same_type_fraction(t, 0.15) - before) < 0.08


def test_sort_adhesion_rejects_matrix_not_covering_cell_types():
    t = _random_tissue(10, 1.0, types=3)
    with pytest.raises(ValueError, match="adhesion"):
        SortStage().run(t, {"adhesion": Const([[1.0, 0.0], [0.0, 1.0]])}, {}, {}, np.random.default_rng(0))


@pytest.mark.parametrize("stage,params", [
    (MigrateStage(), {"min_distance": Const(1.0)}),
    (SortStage(), {"adhesion": Const([[1.0, 0.0], [0.0, 1.0]]), "radius": Const(1.0)}),
])
def test_neighbour_interaction_cost_within_factor_three_of_measured_memory(stage, params):
    import tracemalloc
    N = 4000
    side = (N / 27 * (4 / 3 * np.pi)) ** (1 / 3)  # density giving ~27 neighbours per cell within radius 1, as costed
    t = _random_tissue(N, side, types=2)
    tracemalloc.start()
    stage.run(t, params, {}, {}, np.random.default_rng(0))
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared = type(stage).cost(N, 0, params)[0]
    assert declared / 3 <= peak <= declared * 3


def test_cost_grows_with_steps_and_neighbour_terms():
    base = MigrateStage.cost(1000, 0, {})
    assert MigrateStage.cost(1000, 0, {"min_distance": Const(0.1)})[0] > base[0]
    assert MigrateStage.cost(1000, 0, {"steps": Const(4)})[1] == 4 * base[1]
    adh = {"adhesion": Const([[1.0]])}
    assert SortStage.cost(1000, 0, dict(adh, steps=Const(10)))[1] > SortStage.cost(1000, 0, adh)[1]
