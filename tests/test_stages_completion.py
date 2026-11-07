"""Phase C completion: seed density and point sets (C1), tangential migration (C4), mosaic (C5), Hill expression (C6),
positions in differentiation conditions (C7), connection matrices and rules (C9), activity pruning and scaling rate
(C10), selective myelination (C12) and freeze (C13)."""
import tracemalloc

import numpy as np
import pytest

import neurogenesis.stages  # noqa: F401
from neurogenesis.geometry import geometry_from_dict
from neurogenesis.params import Const, Field
from neurogenesis.stages.base import STAGE_REGISTRY, run_schedule
from neurogenesis.stages.freeze import FreezeError, develop, freeze, validate
from neurogenesis.stages.population import geometry_volume
from neurogenesis.stages.refinement import coactivity
from neurogenesis.fields.core import AnalyticField
from neurogenesis.tissue import SparseConnectivity, Tissue


def _run(op, tissue, params, fields=None, seed=0):
    return STAGE_REGISTRY[op]().run(tissue, params, {}, fields or {}, np.random.default_rng(seed))


def _box():
    return geometry_from_dict({"type": "Box", "center": [5.0, 5.0, 5.0], "size": [10.0, 10.0, 10.0]})


def _random_tissue(n, side, seed=0, types=1):
    rng = np.random.default_rng(seed)
    t = Tissue.empty()
    t.add_cells(n, positions=rng.uniform(0, side, (n, 3)), cell_type=rng.integers(0, types, n))
    return t


def _nnri(pos):
    """Nearest-neighbour regularity index: mean / std of nearest-neighbour distances."""
    d = np.linalg.norm(pos[:, None] - pos[None], axis=-1)
    np.fill_diagonal(d, np.inf)
    nn = d.min(1)
    return nn.mean() / nn.std()


# C1 ---------------------------------------------------------------------------------------------------------------
def test_geometry_volume_of_box():
    assert geometry_volume(_box(), np.random.default_rng(0)) == pytest.approx(1000.0, rel=0.01)


def test_seed_density_constant_gives_density_times_volume():
    t = _run("seed_cells", Tissue.empty(), {"geometry": Const(_box()), "density": Const(0.5)})
    assert abs(len(t.alive) - 500) <= 10
    assert np.all(_box().contains(t.positions))


def test_seed_density_field_follows_the_field():
    fields = {"grad": AnalyticField("x / 10")}
    params = {"geometry": Const(_box()), "density": Field("grad"), "max_density": Const(1.0)}
    t = _run("seed_cells", Tissue.empty(), params, fields)
    assert abs(len(t.alive) - 500) < 60                     # integral of x/10 over the box = 500
    assert np.mean(t.positions[:, 0] > 5) > 0.7             # density 3x higher on the high side
    t2 = _run("seed_cells", Tissue.empty(), params, fields)
    np.testing.assert_array_equal(t.positions, t2.positions)


def test_seed_density_field_needs_max_density():
    with pytest.raises(ValueError, match="max_density"):
        _run("seed_cells", Tissue.empty(), {"geometry": Const(_box()), "density": Field("g")},
             {"g": AnalyticField("x")})


def test_seed_points_list_and_pattern():
    t = _run("seed_cells", Tissue.empty(), {"points": Const([[0, 0], [1, 2]]), "cell_type": Const(3)})
    np.testing.assert_array_equal(t.positions, [[0, 0, 0], [1, 2, 0]])
    assert list(t.cell_type) == [3, 3]
    spec = {"pattern": "poisson_disc", "bounds": [[0, 0], [10, 10]], "radius": 1.0}
    t = _run("seed_cells", Tissue.empty(), {"points": Const(spec)})
    d = np.linalg.norm(t.positions[:, None] - t.positions[None], axis=-1)
    np.fill_diagonal(d, np.inf)
    assert len(t.alive) > 30 and d.min() >= 1.0 - 1e-9
    reg = _run("seed_cells", Tissue.empty(), {"points": Const({"pattern": "regular", "bounds": [[0, 0, 0], [2, 2, 2]], "spacing": 1.0})})
    assert len(reg.alive) == 8


# C4 ---------------------------------------------------------------------------------------------------------------
def test_tangential_migration_keeps_the_radius():
    t = Tissue.empty()
    t.add_cells(2, positions=np.array([[1.0, 0, 0], [0, 2.0, 0]]))
    params = {"speed": Const(0.01), "steps": Const(50), "tangential": Const(True), "direction": Const([1.0, 1.0, 0.0]),
              "target": Const([0.0, 0.0, 0.0])}
    out = _run("migrate", t, params)
    r = np.linalg.norm(out.positions, axis=1)
    np.testing.assert_allclose(r, [1.0, 2.0], rtol=0.02)
    assert np.linalg.norm(out.positions[0] - [1, 0, 0]) > 0.3      # it moved, along the circle


# C5 ---------------------------------------------------------------------------------------------------------------
def test_mosaic_regularises_same_type_cells_and_ignores_others():
    t = _random_tissue(300, 10.0, types=2)
    before = [_nnri(t.positions[t.cell_type == k]) for k in (0, 1)]
    out = _run("mosaic", t, {"radius": Const(1.2), "steps": Const(30), "types": Const([0])})
    after = [_nnri(out.positions[out.cell_type == k]) for k in (0, 1)]
    assert after[0] > before[0] + 1.0                       # type 0 becomes a regular mosaic
    assert after[1] == pytest.approx(before[1])             # type 1 not selected: unchanged


def test_mosaic_determinism_with_jitter():
    a = _run("mosaic", _random_tissue(100, 5.0), {"radius": Const(0.5), "jitter": Const(0.01)}, seed=3)
    b = _run("mosaic", _random_tissue(100, 5.0), {"radius": Const(0.5), "jitter": Const(0.01)}, seed=3)
    np.testing.assert_array_equal(a.positions, b.positions)


def test_mosaic_declared_memory_within_factor_three():
    N = 4000
    side = (N / 27 * (4 / 3 * np.pi)) ** (1 / 3)
    t = _random_tissue(N, side)
    params = {"radius": Const(1.0)}
    tracemalloc.start()
    _run("mosaic", t, params)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared = STAGE_REGISTRY["mosaic"].cost(N, 0, params)[0]
    assert declared / 3 <= peak <= declared * 3


# C6 ---------------------------------------------------------------------------------------------------------------
def test_express_hill_activation():
    t = Tissue.empty(K=1)
    t.add_cells(3, positions=np.zeros((3, 3)), expression=np.array([[0.0], [1.0], [3.0]], dtype=np.float32), K=1)
    out = _run("express", t, {"K": Const(1), "weights": Const([[1.0]]), "activation": Const("hill"),
                              "hill_n": Const(2.0), "hill_k": Const(1.0), "decay": Const(1.0)})
    np.testing.assert_allclose(out.expression[:, 0], [0.0, 0.5, 0.9], rtol=1e-6)
    with pytest.raises(ValueError, match="activation"):
        _run("express", t, {"K": Const(1), "activation": Const("relu")})


def test_express_weight_matrices_accept_genes():
    """Entries of `weights` and `neighbor_weights` may be Genes (as `morphogens` weights already could)."""
    gene = lambda name: {"type": "Gene", "path": [name], "lo": -5.0, "hi": 5.0}
    t = Tissue.empty(K=1)
    t.add_cells(2, positions=np.array([[0.0, 0, 0], [0.05, 0, 0]]), expression=np.array([[1.0], [0.0]], np.float32),
                K=1)
    params = {"K": Const(1), "weights": Const([[gene("w")]]), "decay": Const(1.0), "radius": Const(0.1),
              "neighbor_weights": Const([[gene("n")]])}
    out = STAGE_REGISTRY["express"]().run(t, params, {"w": 2.0, "n": -3.0}, {}, np.random.default_rng(0))
    sig = lambda x: 1 / (1 + np.exp(-x))
    np.testing.assert_allclose(out.expression[:, 0], [sig(2.0 * 1 - 3.0 * 0), sig(2.0 * 0 - 3.0 * 1)], rtol=1e-5)


# C7 ---------------------------------------------------------------------------------------------------------------
def test_differentiate_conditions_see_positions_and_birth_order():
    t = Tissue.empty()
    t.add_cells(3, positions=np.array([[0, 0, 0.1], [0, 0, 0.9], [0, 0, 0.5]]), birth_stage=np.array([0, 2, 1]))
    out = _run("differentiate", t, {"types": Const([{"type_id": 1, "condition": "z > 0.4"},
                                                    {"type_id": 2, "condition": "birth_stage == 2"}])})
    assert list(out.cell_type) == [0, 2, 1]


# C9 ---------------------------------------------------------------------------------------------------------------
def test_connect_by_hand_matrix():
    t = _random_tissue(3, 1.0)
    W = [[0, 5, 0], [0, 0, -3], [7, 0, 0]]
    out = _run("connect_by_hand", t, {"matrix": Const(W), "delay": Const(2)})
    c = out.connectivity
    assert sorted(zip(c.pre, c.post, c.weight)) == [(0, 1, 5), (1, 2, -3), (2, 0, 7)]
    assert np.all(c.delay == 2)
    with pytest.raises(ValueError, match="shape"):
        _run("connect_by_hand", _random_tissue(2, 1.0), {"matrix": Const(W)})


def test_connect_by_hand_rules_probability_and_selectors():
    t = _random_tissue(400, 10.0, types=2)
    rule = {"pre": {"cell_type": 0}, "post": "cell_type == 1", "prob": 0.1, "weight": 30, "delay": 3}
    out = _run("connect_by_hand", t, {"rules": Const([rule])}, seed=1)
    c = out.connectivity
    n0, n1 = np.sum(t.cell_type == 0), np.sum(t.cell_type == 1)
    assert abs(len(c.pre) - 0.1 * n0 * n1) < 4 * np.sqrt(0.1 * n0 * n1)
    assert np.all(t.cell_type[c.pre] == 0) and np.all(t.cell_type[c.post] == 1)
    assert len(set(zip(c.pre, c.post))) == len(c.pre)                         # no duplicate pairs
    again = _run("connect_by_hand", _random_tissue(400, 10.0, types=2), {"rules": Const([rule])}, seed=1)
    np.testing.assert_array_equal(again.connectivity.pre, c.pre)


def test_connect_by_hand_rules_with_distance_velocity_and_dale():
    t = _random_tissue(300, 10.0)
    t.sign[:150] = -1
    rule = {"prob": 1.0, "max_distance": 1.5, "velocity": 0.5, "weight": 20, "dale": True}
    c = _run("connect_by_hand", t, {"rules": Const([rule])}).connectivity
    d = np.linalg.norm(t.positions[c.pre] - t.positions[c.post], axis=1)
    assert len(c.pre) > 0 and np.all(d <= 1.5) and np.all(c.pre != c.post)
    np.testing.assert_array_equal(c.delay, np.clip(np.round(d / 0.5), 1, 31))
    assert np.all((c.weight < 0) == (t.sign[c.pre] < 0))


# C10 --------------------------------------------------------------------------------------------------------------
def test_coactivity_counts_pre_then_post():
    spikes = np.zeros((20, 3), np.uint8)
    spikes[[2, 10], 0] = 1          # pre
    spikes[[5, 13], 1] = 1          # post fires 3 ticks after each pre spike
    pre, post = np.array([0, 0, 2]), np.array([1, 1, 1])
    delay = np.array([2, 8, 1])
    # delay 2: arrivals at 4, 12; post within [t, t+3) -> 5, 13 -> 2. delay 8: arrival at 10, 18 -> none in [18,21) and
    # 13 is in [10, 13)? no (13 excluded) -> 0. pre 2 never fires -> 0.
    np.testing.assert_array_equal(coactivity(spikes, pre, post, delay, 3), [2, 0, 0])


def test_prune_by_activity_removes_unused_synapses():
    t = Tissue.empty()
    t.add_cells(3, positions=np.zeros((3, 3)))
    t.connectivity = SparseConnectivity(np.array([0, 2], np.int32), np.array([1, 1], np.int32),
                                        np.array([50, 50], np.int32), np.array([2, 2], np.int32))
    spikes = np.zeros((30, 3), np.uint8)
    spikes[[2, 12, 22], 0] = 1
    spikes[[5, 15, 25], 1] = 1
    out = _run("prune", t, {"min_coactivity": Const(2), "spikes": Const(spikes), "window": Const(3)})
    assert list(out.connectivity.pre) == [0]


def test_prune_by_activity_with_simulation_is_deterministic():
    def tissue():
        t = Tissue.empty()
        t.add_cells(3, positions=np.zeros((3, 3)), mode=np.array([1, 0, 0]), poisson_hz=np.array([200.0, 0, 0]))
        t.connectivity = SparseConnectivity(np.array([0, 1], np.int32), np.array([1, 2], np.int32),
                                            np.array([2000, 5], np.int32), np.array([1, 1], np.int32))
        return t
    p = {"min_coactivity": Const(1), "ticks": Const(200)}
    a, b = _run("prune", tissue(), p, seed=4), _run("prune", tissue(), p, seed=4)
    np.testing.assert_array_equal(a.connectivity.pre, b.connectivity.pre)
    assert 0 in a.connectivity.pre and 1 not in a.connectivity.pre      # the driven synapse is used, the weak one not


def test_scale_rate_moves_part_of_the_way():
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    t.connectivity = SparseConnectivity(np.array([0], np.int32), np.array([1], np.int32), np.array([100], np.int32), np.array([1], np.int32))
    out = _run("scale", t, {"target": Const(200.0), "rate": Const(0.5)})
    assert out.connectivity.weight[0] == 150


# C12 --------------------------------------------------------------------------------------------------------------
def test_myelinate_selects_long_and_regional_projections():
    t = Tissue.empty()
    t.add_cells(3, positions=np.zeros((3, 3)), region=np.array([0, 1, 1]))
    t.connectivity = SparseConnectivity(np.array([0, 1, 0], np.int32), np.array([1, 2, 2], np.int32),
                                        np.array([5, 5, 5], np.int32), np.array([20, 20, 4], np.int32))
    out = _run("myelinate", t, {"factor": Const(0.5), "min_delay": Const(10), "pre_region": Const([0])})
    assert list(out.connectivity.delay) == [10, 20, 4]


def test_myelinate_selects_active_presynaptic_cells():
    t = Tissue.empty()
    t.add_cells(3, positions=np.zeros((3, 3)), mode=np.array([1, 0, 0]), poisson_hz=np.array([300.0, 0, 0]))
    t.connectivity = SparseConnectivity(np.array([0, 1], np.int32), np.array([1, 2], np.int32),
                                        np.array([1, 1], np.int32), np.array([20, 20], np.int32))
    out = _run("myelinate", t, {"factor": Const(0.5), "min_rate": Const(50.0), "ticks": Const(200)})
    assert list(out.connectivity.delay) == [10, 20]


# C13 --------------------------------------------------------------------------------------------------------------
def test_freeze_validates_and_compiles(tmp_path):
    t = _random_tissue(4, 1.0)
    t.connectivity = SparseConnectivity(np.array([0, 1], np.int32), np.array([1, 2], np.int32),
                                        np.array([5, -5], np.int32), np.array([1, 3], np.int32))
    assert validate(t) == []
    assert "Dale" in validate(t, dale=True)[0]                     # cell 1 is excitatory with a negative synapse
    net = freeze(t)
    assert net.num_neurons == 4 and net.num_synapses == 2
    _run("freeze", t, {"path": Const(str(tmp_path / "n.json"))})
    _run("freeze", t, {"path": Const(str(tmp_path / "n.ngb"))})
    assert (tmp_path / "n.json").exists() and (tmp_path / "n.ngb").exists()
    t.connectivity.delay[0] = 300
    t.connectivity.post[1] = 9
    with pytest.raises(FreezeError, match="delays.*indices|indices.*delays"):
        _run("freeze", t, {})


def test_develop_runs_and_freezes_a_project():
    project = {"schedule": [{"name": "seed", "operator": "seed_cells", "params": {"N": 5, "position": [0, 0, 0]}},
                            {"name": "freeze", "operator": "freeze", "params": {}}]}
    net = develop(project, {}, seed=0)
    assert net.num_neurons == 5
    assert run_schedule(project, {}, 0).positions.shape == (5, 3)


# C11 --------------------------------------------------------------------------------------------------------------
def _driven_pair():
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    t.connectivity = SparseConnectivity(np.array([0], np.int32), np.array([1], np.int32), np.array([100], np.int32),
                                        np.array([1], np.int32))
    spikes = np.zeros((40, 2), np.uint8)
    spikes[::4, 0] = 1
    spikes[1::4, 1] = 1                                      # post fires as each pre spike arrives (delay 1)
    return t, spikes


def test_refine_three_factor_needs_the_modulator():
    t, spikes = _driven_pair()
    base = {"rule": Const("three_factor"), "spikes": Const(spikes), "ticks": Const(40), "eta": Const(1.0)}
    off = _run("refine_by_activity", t, dict(base, modulator=Const(0.0)))
    assert off.connectivity.weight[0] == 100
    t, _ = _driven_pair()
    on = _run("refine_by_activity", t, dict(base, modulator=Const(1.0)))
    assert on.connectivity.weight[0] > 100
    t, _ = _driven_pair()
    neg = _run("refine_by_activity", t, dict(base, modulator=Const(-50.0)))
    assert neg.connectivity.weight[0] == 0                   # sign kept: the excitatory weight stops at 0
    t, _ = _driven_pair()
    cells = _run("refine_by_activity", t, dict(base, modulator_cells=Const([0])))
    assert cells.connectivity.weight[0] > 100                # the presynaptic cell itself carries the modulator
