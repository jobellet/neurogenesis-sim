"""N1 ArborStore and SWC, N2 grow_arbors, N3 arbor_synapses with path-length delays."""
import tracemalloc
import warnings

import numpy as np
import pytest

import neurogenesis.stages  # noqa: F401
from neurogenesis.arbors import AXON, DENDRITE, SOMA, ArborStore, read_swc, write_swc
from neurogenesis.geometry import geometry_from_dict
from neurogenesis.fields.core import AnalyticField
from neurogenesis.stages.base import STAGE_REGISTRY
from neurogenesis.tissue import Tissue

SWC = """# toy neuron
1 1 0 0 0 2.0 -1
2 3 1 0 0 0.5 1
3 3 2 0 0 0.5 2
4 3 3 1 0 0.5 3
5 3 3 -1 0 0.5 3
6 2 -1 0 0 0.3 1
7 2 -2 0 0 0.3 6
"""


def _run(op, t, params, fields=None, seed=0):
    return STAGE_REGISTRY[op]().run(t, params, {}, fields or {}, np.random.default_rng(seed))


def _cells(n=20, side=10.0, seed=0):
    t = Tissue.empty()
    t.add_cells(n, positions=np.random.default_rng(seed).uniform(0, side, (n, 3)))
    return t


# N1 ---------------------------------------------------------------------------------------------------------------
def test_swc_round_trip_and_path_lengths(tmp_path):
    (tmp_path / "a.swc").write_text(SWC)
    s = read_swc(tmp_path / "a.swc")
    assert s.n_nodes == 7 and list(np.bincount(s.compartment)) == [0, 1, 2, 4]
    pl = s.path_length_to_root()
    by_pos = {tuple(np.round(x, 3)): d for x, d in zip(s.xyz, pl)}
    assert by_pos[(3.0, 1.0, 0.0)] == pytest.approx(2 + np.sqrt(2))
    assert by_pos[(-2.0, 0.0, 0.0)] == pytest.approx(2.0)
    write_swc(s, tmp_path / "b.swc")
    s2 = read_swc(tmp_path / "b.swc")
    np.testing.assert_allclose(s2.xyz, s.xyz)
    np.testing.assert_array_equal(s2.parent, s.parent)
    np.testing.assert_array_equal(s2.compartment, s.compartment)


def test_ordered_accepts_any_node_order_and_rejects_cycles():
    s = ArborStore.ordered(np.arange(12).reshape(4, 3), np.ones(4), [2, 0, -1, 1], [3, 3, 1, 3], [0] * 4)
    assert s.parent[0] == -1 and np.all(s.parent[1:] < np.arange(1, 4))
    with pytest.raises(ValueError, match="cycle"):
        ArborStore.ordered(np.zeros((2, 3)), np.ones(2), [1, 0], [3, 3], [0, 0])


def test_downsample_keeps_topology_and_length_of_straight_stretches():
    n = 41                                                     # a straight neurite of 40 unit segments
    s = ArborStore(np.stack([np.arange(n), np.zeros(n), np.zeros(n)], 1), np.ones(n), np.arange(n) - 1,
                   [SOMA] + [DENDRITE] * (n - 1), np.zeros(n))
    d = s.downsample(8)
    assert d.n_nodes == 7 and d.path_length_to_root().max() == pytest.approx(40.0)   # root, compartment change, 8, 16, ...
    assert s.to_budget(10).n_nodes <= 10


def test_tissue_compact_and_subset_remap_arbors():
    t = _cells(4)
    t = _run("grow_arbors", t, {"steps": 3, "n_neurites": 1})
    t.alive[1] = False
    t.compact()
    assert set(t.morphology.cell.tolist()) == {0, 1, 2}
    s = t.subset(np.array([2]))
    assert set(s.morphology.cell.tolist()) == {0} and s.morphology.n_nodes == 4


# N2 ---------------------------------------------------------------------------------------------------------------
def test_grow_arbors_neutral_and_deterministic():
    t = _cells()
    assert _run("grow_arbors", t, {}).morphology is None
    a = _run("grow_arbors", _cells(), {"steps": 10, "n_neurites": 2, "branch_prob": 0.2}, seed=5)
    b = _run("grow_arbors", _cells(), {"steps": 10, "n_neurites": 2, "branch_prob": 0.2}, seed=5)
    np.testing.assert_array_equal(a.morphology.xyz, b.morphology.xyz)
    m = a.morphology
    assert np.sum(m.compartment == SOMA) == 20 and np.all(m.children_count()[m.compartment == SOMA] >= 1)


def test_grow_arbors_branching_attraction_and_boundary():
    no_branch = _run("grow_arbors", _cells(), {"steps": 10, "n_neurites": 1, "stop_prob": 0.0}).morphology
    assert no_branch.n_nodes == 20 + 20 * 10                    # one node per step and tip
    branched = _run("grow_arbors", _cells(), {"steps": 10, "n_neurites": 1, "branch_prob": 0.3}).morphology
    assert branched.n_nodes > no_branch.n_nodes
    up = _run("grow_arbors", _cells(), {"steps": 20, "n_neurites": 1, "attractor_field": "height", "attraction": 5.0,
                                        "angle_noise": 0.1, "step_length": 0.5}, {"height": AnalyticField("z")}).morphology
    tips = up.children_count() == 0
    somas = up.xyz[up.compartment == SOMA]
    assert np.mean(up.xyz[tips][:, 2]) > np.mean(somas[:, 2]) + 5
    box = geometry_from_dict({"type": "Box", "center": [5, 5, 5], "size": [10, 10, 10]})
    inside = _run("grow_arbors", _cells(), {"steps": 30, "n_neurites": 2, "boundary": "box"}, {"box": box}).morphology
    assert np.all(box.contains(inside.xyz.astype(np.float64)))


def test_grow_arbors_declared_memory_within_factor_three():
    params = {"steps": 20, "n_neurites": 3, "branch_prob": 0.05}
    t = _cells(2000, 100.0)
    tracemalloc.start()
    out = _run("grow_arbors", t, params)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared = STAGE_REGISTRY["grow_arbors"].cost(2000, 0, params)[0]
    assert declared / 3 <= peak <= declared * 3
    assert out.morphology.n_nodes > 2000 * 3 * 20


# N3 ---------------------------------------------------------------------------------------------------------------
def _two_cells():
    """Cell 0's axon runs along +x through cell 1's dendrite; cell 1 is inhibitory."""
    t = Tissue.empty()
    t.add_cells(2, positions=np.array([[0.0, 0, 0], [10.0, 5, 0]]), sign=np.array([1, -1]))
    xs = np.arange(0, 13)
    ax = np.stack([xs, np.zeros(13), np.zeros(13)], 1)
    dend = np.stack([np.full(6, 10.0), 5.0 - np.arange(6), np.zeros(6)], 1)
    xyz = np.concatenate([ax, dend])
    parent = np.concatenate([np.arange(13) - 1, [-1], 13 + np.arange(5)])
    comp = [SOMA] + [AXON] * 12 + [SOMA] + [DENDRITE] * 5
    t.morphology = ArborStore(xyz, np.ones(19), parent, comp, [0] * 13 + [1] * 6)
    return t


def test_arbor_synapses_path_length_delays_and_records():
    t = _run("arbor_synapses", _two_cells(), {"contact_distance": 0.6, "axon_velocity": 2.0, "dendrite_velocity": 5.0,
                                              "weight": 30})
    c = t.connectivity
    assert list(zip(c.pre, c.post)) == [(0, 1)]                # one synapse per cell pair (max_per_pair = 1)
    assert c.path_length[0] == pytest.approx(10.0) and c.dendritic_distance[0] == pytest.approx(5.0)
    assert c.delay[0] == 6                                      # 10 / 2 + 5 / 5
    assert t.morphology.xyz[c.pre_node[0]].tolist() == [10, 0, 0] and c.weight[0] == 30
    none = _run("arbor_synapses", _two_cells(), {})
    assert len(none.connectivity.pre) == 0


def test_arbor_synapses_clip_delays_with_a_warning_and_keep_signs():
    t = _two_cells()
    t.morphology.compartment[14:] = AXON                        # swap roles: cell 1's axon onto cell 0's dendrite
    t.morphology.compartment[1:13] = DENDRITE
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        out = _run("arbor_synapses", t, {"contact_distance": 0.6, "axon_velocity": 0.1, "weight": 30})
    c = out.connectivity
    assert list(zip(c.pre, c.post)) == [(1, 0)] and c.weight[0] == -30 and c.delay[0] == 31
    assert any("clipped" in str(x.message) for x in w)


def test_arbor_synapses_max_delay_and_velocity_per_type():
    t = _two_cells()
    t.morphology.compartment[14:] = AXON
    t.morphology.compartment[1:13] = DENDRITE
    long = _run("arbor_synapses", t, {"contact_distance": 0.6, "axon_velocity": 0.1, "max_delay": 127})
    assert long.connectivity.delay[0] == 50                     # 5 / 0.1, no longer clipped at 31

    def typed():
        t = _two_cells()
        t.cell_type[:] = [0, 1]
        return t
    base = {"contact_distance": 0.6, "axon_velocity": 2.0}
    same = _run("arbor_synapses", _two_cells(), base).connectivity.delay[0]
    fast = _run("arbor_synapses", typed(), dict(base, axon_velocity_by_type=[5.0])).connectivity.delay[0]
    past = _run("arbor_synapses", typed(), dict(base, axon_velocity_by_type=[])).connectivity.delay[0]
    assert (same, fast, past) == (5, 2, 5)                      # 10 / 2, 10 / 5 for type 0; empty list = global
    with pytest.raises(ValueError):
        _run("arbor_synapses", _two_cells(), dict(base, max_delay=300))


def test_arbor_synapses_in_a_grown_tissue():
    t = _cells(40, 15.0)
    t = _run("grow_arbors", t, {"steps": 15, "n_neurites": 1, "compartment": "axon"}, seed=1)
    t = _run("grow_arbors", t, {"steps": 6, "n_neurites": 3, "compartment": "dendrite", "branch_prob": 0.2}, seed=2)
    t = _run("arbor_synapses", t, {"contact_distance": 1.0, "max_per_pair": 2})
    c = t.connectivity
    assert len(c.pre) > 0 and np.all(c.pre != c.post)
    d = np.linalg.norm(t.morphology.xyz[c.pre_node] - t.morphology.xyz[c.post_node], axis=1)
    assert np.all(d <= 1.0 + 1e-6)
    _, counts = np.unique(c.pre.astype(np.int64) * 40 + c.post, return_counts=True)
    assert counts.max() <= 2
    from neurogenesis.stages.freeze import validate
    assert validate(t) == []


# C21 coupling: chloride maturation slows arbor growth ---------------------------------------------------------------
def test_grow_arbors_maturation_gain_zero_is_noop():
    p = {"steps": 10, "n_neurites": 2, "branch_prob": 0.2}
    a = _run("grow_arbors", _cells(), p, seed=5).morphology
    b = _run("grow_arbors", _cells(), dict(p, maturation=1.0, maturation_gain=0.0), seed=5).morphology
    np.testing.assert_array_equal(a.xyz, b.xyz)


def test_grow_arbors_mature_cells_grow_less():
    from neurogenesis.analysis.morphology import morphometrics
    t = Tissue.empty()
    t.add_cells(40, positions=np.random.default_rng(0).uniform(0, 10, (40, 3)),
                birth_time=np.r_[np.zeros(20), np.full(20, 10.0)].astype(np.float32))     # first 20 born early: mature
    p = {"steps": 12, "n_neurites": 2, "branch_prob": 0.25, "stop_prob": 0.0, "maturation_gain": 1.0,
         "maturation_switch": {"midpoint": 5.0, "width": 0.5}}
    m = morphometrics(_run("grow_arbors", t, p, seed=1).morphology, cells=np.arange(40))
    assert m["total_length"][:20].mean() < 0.05 * m["total_length"][20:].mean()
    full = _run("grow_arbors", _cells(), {"steps": 5, "maturation": 1.0, "maturation_gain": 1.0}).morphology
    assert np.allclose(full.segment_lengths(), 0.0)                 # fully mature: no elongation
