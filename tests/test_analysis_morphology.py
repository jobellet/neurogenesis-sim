"""N6 morphometry: known answers on hand-made trees, grown arbors, degenerate inputs."""
import numpy as np
import pytest

from neurogenesis.analysis import morphology as mo
from neurogenesis.arbors import ArborStore


def _y_tree(cell=0, offset=(0.0, 0.0, 0.0)):
    xyz = np.array([[0, 0, 0], [0, 0, 1], [0, 0, 2], [0, 0, 4], [1, 0, 2]], float) + np.asarray(offset)
    return ArborStore(xyz, np.ones(5), [-1, 0, 1, 2, 2], [1, 3, 3, 3, 3], [cell] * 5)


def test_node_kinds_and_branch_order():
    s = _y_tree()
    k = mo.node_kinds(s)
    assert np.flatnonzero(k["branch_point"]).tolist() == [2]
    assert np.flatnonzero(k["tip"]).tolist() == [3, 4]
    assert np.flatnonzero(k["stem"]).tolist() == [1]
    assert mo.branch_order(s).tolist() == [0, 0, 0, 1, 1]


def test_morphometrics_known_answers():
    m = mo.morphometrics(_y_tree())
    assert m["n_nodes"][0] == 5 and m["n_tips"][0] == 2 and m["n_branch_points"][0] == 1 and m["n_stems"][0] == 1
    assert m["total_length"][0] == pytest.approx(5.0)
    assert m["max_path_length"][0] == pytest.approx(4.0)
    assert m["max_radial_distance"][0] == pytest.approx(4.0)
    assert m["mean_radial_distance"][0] == pytest.approx((4 + np.sqrt(5)) / 2)
    assert (m["width"][0], m["depth"][0], m["height"][0]) == pytest.approx((1.0, 0.0, 4.0))
    assert m["max_branch_order"][0] == 1
    assert m["n_branches"][0] == 3
    assert m["mean_branch_length"][0] == pytest.approx(5 / 3)
    assert m["median_tortuosity"][0] == pytest.approx(1.0) and m["max_tortuosity"][0] == pytest.approx(1.0)
    assert m["mean_branch_angle"][0] == pytest.approx(np.pi / 2)


def test_tortuosity_of_a_bent_branch():
    s = ArborStore([[0, 0, 0], [1, 1, 0], [2, 0, 0]], np.ones(3), [-1, 0, 1], [1, 3, 3], [0, 0, 0])
    m = mo.morphometrics(s)
    assert m["n_branches"][0] == 1
    assert m["max_tortuosity"][0] == pytest.approx(2 * np.sqrt(2) / 2)


def test_morphometrics_several_cells_and_missing_cell():
    s = ArborStore.concatenate([_y_tree(0), _y_tree(3, (5, 5, 5))])
    m = mo.morphometrics(s, cells=[0, 1, 3])
    assert m["n_nodes"].tolist() == [5, 0, 5]
    assert m["total_length"][0] == pytest.approx(m["total_length"][2])
    assert np.isnan(m["mean_branch_length"][1])


def test_sholl_profile():
    assert mo.sholl(_y_tree(), 0, [0.5, 1.5, 2.1, 3.0, 5.0]).tolist() == [1, 1, 2, 1, 0]
    assert mo.sholl(_y_tree(), 9, [1.0]).tolist() == [0]


def test_tmd_barcode_known_answer_and_one_bar_per_tip():
    bars = mo.tmd_barcodes(_y_tree())[0]
    assert np.allclose(bars, [[4.0, 0.0], [np.sqrt(5), 2.0]])
    path_bars = mo.tmd_barcodes(_y_tree(), "path")[0]
    assert np.allclose(path_bars, [[4.0, 0.0], [3.0, 2.0]])
    with pytest.raises(ValueError):
        mo.tmd_barcodes(_y_tree(), "volume")


def test_tmd_is_translation_invariant_and_lone_soma_has_no_bar():
    a = mo.tmd_barcodes(_y_tree())[0]
    b = mo.tmd_barcodes(_y_tree(offset=(3, -2, 7)))[0]
    assert np.allclose(a, b)
    lone = ArborStore([[0, 0, 0]], [1.0], [-1], [1], [0])
    assert mo.tmd_barcodes(lone)[0].shape == (0, 2)
    assert mo.tmd_barcodes(ArborStore(), cells=[0])[0].shape == (0, 2)


def test_tmd_on_grown_arbors_has_one_bar_per_tip():
    from neurogenesis.stages.base import STAGE_REGISTRY
    from neurogenesis.tissue import Tissue
    t = Tissue.empty()
    t.add_cells(4, positions=np.random.default_rng(0).random((4, 3)) * 10)
    t = STAGE_REGISTRY["grow_arbors"]().run(t, dict(steps=12, n_neurites=2, branch_prob=0.3, step_length=0.5), {}, {},
                                            np.random.default_rng(1))
    m = mo.morphometrics(t.morphology)
    bars = mo.tmd_barcodes(t.morphology)
    for k, c in enumerate(m["cell"]):
        assert len(bars[int(c)]) == m["n_tips"][k]
        assert np.all(bars[int(c)][:, 0] >= bars[int(c)][:, 1])


def test_barcode_distance():
    a = mo.tmd_barcodes(_y_tree())[0]
    assert mo.barcode_distance(a, a) == 0.0
    b = np.array([[4.0, 0.0], [3.9, 3.5], [3.8, 3.0]])
    d = mo.barcode_distance(a, b)
    assert 0 < d <= 2
    assert mo.barcode_distance(a, b) == mo.barcode_distance(b, a)
    assert mo.persistence_image(np.zeros((0, 2))).sum() == 0


def test_fit_metrics_on_a_tissue():
    from neurogenesis.fitting import METRICS
    from neurogenesis.tissue import Tissue
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    assert METRICS["arbor"](t, {}) == 0.0
    t.morphology = ArborStore.concatenate([_y_tree(0), _y_tree(1)])
    assert METRICS["arbor"](t, {}) == pytest.approx(5.0)
    assert METRICS["arbor"](t, {"measure": "n_tips"}) == pytest.approx(2.0)
    ref = np.concatenate([mo.tmd_barcodes(_y_tree())[0]] * 2)
    assert METRICS["barcode_distance"](t, {"bars": ref.tolist()}) == pytest.approx(0.0)


def _grown(record=True, retraction=0.0, seed=1):
    from neurogenesis.stages.base import STAGE_REGISTRY
    from neurogenesis.tissue import Tissue
    t = Tissue.empty()
    t.add_cells(3, positions=np.random.default_rng(0).random((3, 3)) * 10)
    p = dict(steps=8, n_neurites=2, branch_prob=0.3, step_length=0.5, retraction_prob=retraction, record_history=record)
    return STAGE_REGISTRY["grow_arbors"]().run(t, p, {}, {}, np.random.default_rng(seed))


def test_record_history_is_off_by_default_and_does_not_change_growth():
    a, b = _grown(False), _grown(True)
    assert not hasattr(a, "_arbor_history")
    np.testing.assert_array_equal(a.morphology.xyz, b.morphology.xyz)


def test_temporal_barcodes_grow_and_end_with_the_final_tree():
    t = _grown(True, retraction=0.3)
    h = t._arbor_history
    series = mo.temporal_barcodes(h)
    final = mo.tmd_barcodes(t.morphology)
    for c, s in series.items():
        assert len(s) == h["steps"] + 2
        assert all(len(x) == 0 for x in s[:1])                     # step 0: somas only
        assert np.allclose(s[-1], final[c])                        # after retraction = the final tree
        n_bars = [len(x) for x in s[:-1]]
        assert n_bars[-1] >= n_bars[1] > 0
        assert all(np.all(x[:, 0] >= x[:, 1]) for x in s if len(x))
    assert len(mo.temporal_barcodes(h, every=3)[0]) == 5          # steps 0, 3, 6, the last (8), after retraction
    one = series[0]
    assert mo.barcode_series_distance(one, one) == 0.0
    assert mo.barcode_series_distance(one, series[1]) > 0
    assert mo.barcode_series_distance(one, one[:3]) > 0           # padded with its last barcode
    with pytest.raises(ValueError):
        mo.barcode_series_distance(one, [])
