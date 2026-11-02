"""Defects found by the retina -> relay example (#80): Genes nested in guidance values, mosaic with a boundary, waves
restricted to some cells, and Poisson drivers restored after refine_by_activity."""
import numpy as np

import neurogenesis.stages  # noqa: F401
from neurogenesis.geometry import geometry_from_dict
from neurogenesis.params import Const
from neurogenesis.stages.base import STAGE_REGISTRY, run_schedule
from neurogenesis.tissue import SparseConnectivity, Tissue


def test_resolve_nested_reaches_genes_at_any_depth():
    from neurogenesis.params import resolve_nested
    g = {"a": 2.0, "b": 3.0}
    gene = lambda p: {"type": "Gene", "path": [p], "lo": 0.0, "hi": 5.0}
    v = {"B": [[gene("a"), 0.0], [0.0, gene("b")]], "sigma": 0.3, "nested": {"x": Const(gene("a"))}}
    assert resolve_nested(v, g, {}) == {"B": [[2.0, 0.0], [0.0, 3.0]], "sigma": 0.3, "nested": {"x": 2.0}}


def test_grow_axons_uses_genes_inside_the_guidance_matrix():
    def project(genes_in_b):
        diag = ([{"type": "Gene", "path": ["gx"], "lo": 0.0, "hi": 4.0}, 0, 0] if genes_in_b else [2.0, 0, 0])
        return {"schedule": [
            {"name": "src", "operator": "place_by_hand", "params": {"positions": [[i, 0, 0] for i in range(10)], "region": 0}},
            {"name": "dst", "operator": "place_by_hand", "params": {"positions": [[i, 0, 50] for i in range(10)], "region": 1}},
            {"name": "axons", "operator": "grow_axons", "params": {
                "projections": ["0->1"], "exact": True,
                "guidance": {"0->1": {"B": [diag, [0, 1, 0], [0, 0, 1]], "sigma": 0.1, "p0": 1.0, "w": 10.0}}}}]}
    with_gene = run_schedule(project(True), {"gx": 2.0}, 0).connectivity
    by_hand = run_schedule(project(False), {}, 0).connectivity
    np.testing.assert_array_equal(with_gene.pre, by_hand.pre)
    np.testing.assert_array_equal(with_gene.post, by_hand.post)
    assert len(with_gene.pre) > 0


def test_mosaic_moves_cells_that_start_outside_its_boundary():
    box = geometry_from_dict({"type": "Box", "center": [5, 5, 0], "size": [10, 10, 1]})
    rng = np.random.default_rng(0)
    pos = np.column_stack([rng.uniform(4, 6, 40), rng.uniform(4, 6, 40), rng.uniform(-2, 2, 40)])   # many outside |z| > 0.5
    t = Tissue.empty()
    t.add_cells(40, positions=pos)
    out = STAGE_REGISTRY["mosaic"]().run(t, {"radius": Const(2.0), "steps": Const(20), "boundary": Const("box")}, {},
                                         {"box": box}, np.random.default_rng(0))
    outside = ~box.contains(pos)
    assert outside.any() and np.all(np.any(out.positions[outside] != pos[outside], axis=1))
    inside = ~outside
    assert np.all(box.contains(out.positions[inside]))            # cells inside never leave


def _two_regions():
    t = Tissue.empty()
    t.add_cells(4, positions=np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1000], [1, 0, 1000]], float),
                region=np.array([0, 0, 1, 1]), threshold=np.full(4, 512))
    t.connectivity = SparseConnectivity(np.array([0, 2], np.int32), np.array([1, 3], np.int32),
                                        np.array([200, 200], np.int32), np.array([1, 1], np.int32))
    return t


def test_waves_can_be_restricted_to_some_cells():
    wave = {"sources": [[0, 0, 0]], "speed": 200.0, "interval": 2000, "duration": 2000, "amplitude": 3000}
    params = {"ticks": Const(30), "rule": Const("stdp"), "A_plus": Const(5.0), "A_minus": Const(1.0)}
    everywhere = STAGE_REGISTRY["refine_by_activity"]().run(_two_regions(), dict(params, waves=Const(wave)), {}, {},
                                                            np.random.default_rng(0)).connectivity.weight
    only_0 = STAGE_REGISTRY["refine_by_activity"]().run(_two_regions(), dict(params, waves=Const(dict(wave, cells={"region": [0]}))),
                                                        {}, {}, np.random.default_rng(0)).connectivity.weight
    assert everywhere[1] != 200                     # the far region is reached when nothing restricts the waves
    assert only_0[1] == 200 and only_0[0] == everywhere[0]


def test_restore_modes_removes_poisson_drivers_after_the_stage():
    params = {"ticks": Const(30), "rule": Const("stdp"), "sources": Const([0, 1]), "poisson_hz": Const(200.0)}
    kept = STAGE_REGISTRY["refine_by_activity"]().run(_two_regions(), params, {}, {}, np.random.default_rng(0))
    assert kept.mode[:2].tolist() == [1, 1]          # default: unchanged behaviour, drivers stay
    t = _two_regions()
    before = (t.mode.copy(), t.poisson_hz.copy())
    restored = STAGE_REGISTRY["refine_by_activity"]().run(t, dict(params, restore_modes=Const(True)), {}, {},
                                                          np.random.default_rng(0))
    np.testing.assert_array_equal(restored.mode, before[0])
    np.testing.assert_array_equal(restored.poisson_hz, before[1])
    np.testing.assert_array_equal(restored.connectivity.weight, kept.connectivity.weight)   # same plasticity
