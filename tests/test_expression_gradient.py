"""The `expression_gradient` target rule: a topographic map read from graded expression (C8)."""
import numpy as np
import pytest

from neurogenesis.development.rules import RULES, GuidanceContext
from neurogenesis.params import Const
from neurogenesis.stages.base import Stage
from neurogenesis.tissue import Tissue

N_SIDE = 20
NAMES = ["fate", "EphA", "EphB"]
GRADIENT = [{"gene": "EphA", "axis": 0, "gain": 2.0}, {"gene": "EphB", "axis": 1, "gain": 2.0}]


def _tissue(epha=1.0):
    """Two 20 x 20 sheets, region 0 at z = 0 and region 1 at z = 10, both spanning [0, 1]^2 in local units. Source cells
    express EphA ~ x and EphB ~ y (times `epha` for EphA); the target sheet expresses nothing."""
    g = (np.arange(N_SIDE) + 0.5) / N_SIDE
    xy = np.stack(np.meshgrid(g, g, indexing="ij"), -1).reshape(-1, 2)
    n = len(xy)
    pos = np.concatenate([np.c_[xy, np.zeros(n)], np.c_[xy, np.full(n, 10.0)]])
    t = Tissue.empty()
    t.add_cells(2 * n, positions=pos, K=3, region=np.repeat([0, 1], n))
    t.expression[:n, 1] = epha * xy[:, 0]
    t.expression[:n, 2] = xy[:, 1]
    t.expression_names = list(NAMES)
    return t


def _grow(t, gd, exact=True, seed=0, rules=("expression_gradient",)):
    params = dict(projections=["0->1"], exact=exact, rules_target=list(rules),
                  bounds_min={"0": [0, 0, 0], "1": [0, 0, 9.5]}, bounds_size={"0": [1, 1, 1], "1": [1, 1, 1]},
                  guidance={"0->1": dict(dict(B=np.zeros((3, 3)).tolist(), sigma=0.08, p0=0.9), **gd)})
    return Stage(name="g", operator="grow_axons", params={k: Const(v) for k, v in params.items()}).run(
        t, {}, {}, np.random.default_rng(seed))


def _map(t):
    """Per-source centroid of its targets in (u, v), and the source positions, for sources with a synapse."""
    c = t.connectivity
    n = N_SIDE * N_SIDE
    cnt = np.bincount(c.pre, minlength=n).astype(float)
    cen = np.stack([np.bincount(c.pre, t.positions[c.post, k], n) for k in (0, 1)], 1) / np.maximum(cnt, 1)[:, None]
    has = cnt > 0
    return cen[has], t.positions[:n, :2][has]


def _r(a, b):
    return float(np.corrcoef(a, b)[0, 1])


def test_map_from_expression_gradients():
    cen, src = _map(_grow(_tissue(), dict(expression_gradient=GRADIENT)))
    assert len(src) > 0.95 * N_SIDE ** 2
    assert _r(src[:, 0], cen[:, 0]) > 0.95 and _r(src[:, 1], cen[:, 1]) > 0.95
    ideal = 1.0 / (1.0 + np.exp(-8.0 * (src - 0.5)))
    assert np.abs(cen - ideal).mean() < 0.05


def test_repulsion_reverses_the_axis():
    gd = dict(expression_gradient=[dict(GRADIENT[0], sign="repel"), GRADIENT[1]])
    cen, src = _map(_grow(_tissue(), gd))
    assert _r(src[:, 0], cen[:, 0]) < -0.95 and _r(src[:, 1], cen[:, 1]) > 0.95


def test_zero_expression_loses_its_axis_only():
    cen, src = _map(_grow(_tissue(epha=0.0), dict(expression_gradient=GRADIENT)))
    assert abs(_r(src[:, 0], cen[:, 0])) < 0.2
    assert abs(cen[:, 0].mean() - 0.5) < 0.05          # constant gene: targets at the centre of the axis
    assert _r(src[:, 1], cen[:, 1]) > 0.95


def test_knockout_in_express_zeroes_the_gene():
    t = _tissue()
    stage = Stage(name="e", operator="express", params={"K": Const(3), "decay": Const(0.0), "dt": Const(0.0),
                                                       "names": Const(NAMES), "knockout": Const(["EphA"])})
    t = stage.run(t, {}, {}, np.random.default_rng(0))
    assert t.expression_names == NAMES and not t.expression[:, 1].any() and t.expression[:400, 2].any()
    cen, src = _map(_grow(t, dict(expression_gradient=GRADIENT)))
    assert abs(_r(src[:, 0], cen[:, 0])) < 0.2 and _r(src[:, 1], cen[:, 1]) > 0.95


def test_dense_and_sparse_agree():
    """The rule acts on the target before the dense / sparse branch: same targets, and maps within sampling noise."""
    targets = []
    rule = RULES["target"]["expression_gradient"]

    def spy(ctx):
        rule(ctx)
        targets.append(ctx.target.copy())

    RULES["target"]["spy"] = spy
    try:
        dense = _grow(_tissue(), dict(expression_gradient=GRADIENT), exact=True, rules=("spy",))
        sparse = _grow(_tissue(), dict(expression_gradient=GRADIENT), exact=False, rules=("spy",))
    finally:
        del RULES["target"]["spy"]
    assert np.array_equal(targets[0], targets[1])
    (cd, sd), (cs, ss) = _map(dense), _map(sparse)
    assert _r(sd[:, 0], cd[:, 0]) > 0.95 and _r(ss[:, 0], cs[:, 0]) > 0.95
    assert abs(len(dense.connectivity.pre) - len(sparse.connectivity.pre)) < 0.1 * len(dense.connectivity.pre)
    assert abs(cd.mean(0) - cs.mean(0)).max() < 0.02


def test_modulate_adds_to_the_b_map():
    gd = dict(B=np.diag([2.0, 2.0, 0.0]).tolist(),
              expression_gradient={"genes": [dict(GRADIENT[0], sign=-1, normalize="none")], "mode": "modulate"})
    cen, src = _map(_grow(_tissue(), gd))
    assert abs(_r(src[:, 0], cen[:, 0])) < 0.2          # B term cancelled by an equal repulsive expression term
    assert _r(src[:, 1], cen[:, 1]) > 0.95


def test_without_the_rule_networks_are_unchanged():
    base = _grow(_tissue(), dict(B=np.diag([2.0, 2.0, 0.0]).tolist()), rules=())
    listed = _grow(_tissue(), dict(B=np.diag([2.0, 2.0, 0.0]).tolist()))          # listed, but no gene: no-op
    for a in ("pre", "post", "weight", "delay"):
        assert np.array_equal(getattr(base.connectivity, a), getattr(listed.connectivity, a))


def test_determinism():
    a = _grow(_tissue(), dict(expression_gradient=GRADIENT), seed=3)
    b = _grow(_tissue(), dict(expression_gradient=GRADIENT), seed=3)
    assert np.array_equal(a.connectivity.pre, b.connectivity.pre)
    assert np.array_equal(a.connectivity.post, b.connectivity.post)


def test_missing_gene_raises():
    with pytest.raises(ValueError, match="not in expression_names"):
        _grow(_tissue(), dict(expression_gradient=[{"gene": "Robo", "axis": 0}]))


def test_no_expression_raises():
    t = _tissue()
    t.expression = np.zeros((len(t.alive), 0), np.float32)
    with pytest.raises(ValueError, match="no source expression"):
        _grow(t, dict(expression_gradient=GRADIENT))
    ctx = GuidanceContext("a", "b", np.zeros((2, 3)), np.zeros((2, 3)), np.zeros(2, bool), None,
                          dict(expression_gradient=GRADIENT), shift=np.zeros(3), target=np.full((2, 3), 0.5))
    with pytest.raises(ValueError, match="no source expression"):
        RULES["target"]["expression_gradient"](ctx)


@pytest.mark.parametrize("entry, match", [({"gene": "EphA", "axis": 3}, "axis"),
                                          ({"gene": "EphA", "axis": 0, "sign": "sideways"}, "sign"),
                                          ({"gene": "EphA", "axis": 0, "normalize": "zscore"}, "normalize"),
                                          ({"gene": 7, "axis": 0}, "column")])
def test_bad_entries_raise(entry, match):
    with pytest.raises(ValueError, match=match):
        _grow(_tissue(), dict(expression_gradient=[entry]))


def test_express_names_validation():
    stage = Stage(name="e", operator="express", params={"K": Const(3), "names": Const(["a", "a", "b"])})
    with pytest.raises(ValueError, match="distinct"):
        stage.run(_tissue(), {}, {}, np.random.default_rng(0))
