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
