import copy

import numpy as np

from neurogenesis.stages.partner import PartnerSelectStage
from neurogenesis.tissue import Tissue, SparseConnectivity


def _tissue(n=60, seed=0):
    t = Tissue.empty()
    t.add_cells(n, positions=np.zeros((n, 3)), cell_type=(np.arange(n) % 2).astype(np.int32))
    pre, post = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    keep = pre != post
    pre, post = pre[keep].astype(np.int32), post[keep].astype(np.int32)
    t.connectivity = SparseConnectivity(pre, post, np.full(len(pre), 5, np.int32), np.ones(len(pre), np.int32))
    return t


def _run(t, params, seed=0):
    return PartnerSelectStage().run(t, params, {}, {}, np.random.default_rng(seed))


def test_neutral_is_noop():
    t = _tissue(10)
    out = _run(copy.deepcopy(t), {})
    assert np.array_equal(out.connectivity.pre, t.connectivity.pre)
    assert PartnerSelectStage.cost(0, 0, {}) == (0, 0)


def test_identity_matrix_keeps_only_same_channel_pairs():
    t = _tissue()
    out = _run(t, {"compat": [[1, 0], [0, 1]]})
    ct = t.cell_type
    assert len(out.connectivity.pre) > 0
    assert np.all(ct[out.connectivity.pre] == ct[out.connectivity.post])


def test_probabilities_are_respected():
    t = _tissue(80)
    n0 = len(t.connectivity.pre)
    out = _run(t, {"compat": [[0.5, 0.1], [0.9, 0.0]]})
    c = out.connectivity
    ct = t.cell_type
    frac = {(i, j): np.mean((ct[c.pre] == i) & (ct[c.post] == j)) * len(c.pre) / (n0 / 4) for i in (0, 1) for j in (0, 1)}
    assert abs(frac[(0, 0)] - 0.5) < 0.05 and abs(frac[(0, 1)] - 0.1) < 0.05
    assert abs(frac[(1, 0)] - 0.9) < 0.05 and frac[(1, 1)] == 0.0


def test_explicit_channels_expression_and_determinism():
    t = _tissue(20)
    a = _run(copy.deepcopy(t), {"compat": [[1, 0], [0, 1]], "channels": [0] * 10 + [1] * 10}, seed=3)
    b = _run(copy.deepcopy(t), {"compat": [[1, 0], [0, 1]], "channels": [0] * 10 + [1] * 10}, seed=3)
    assert np.array_equal(a.connectivity.pre, b.connectivity.pre)
    assert np.all((a.connectivity.pre < 10) == (a.connectivity.post < 10))
    out = _run(copy.deepcopy(t), {"compat": [[1, 0], [0, 1]], "channels": [5] * 20})   # outside the matrix: kept
    assert len(out.connectivity.pre) == len(t.connectivity.pre)


def test_cost_linear():
    b1, o1 = PartnerSelectStage.cost(100, 1000, {})
    b2, o2 = PartnerSelectStage.cost(200, 2000, {})
    assert b2 == 2 * b1 and o2 == 2 * o1
