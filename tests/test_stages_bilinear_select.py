"""C25 bilinear_select: neutral no-op, known probabilities, knockouts, determinism, cost."""
import copy
import time
import tracemalloc

import numpy as np
import pytest

from neurogenesis.stages.partner import BilinearSelectStage
from neurogenesis.tissue import SparseConnectivity, Tissue


def _tissue(n=80, K=2, seed=0):
    t = Tissue.empty(K)
    expr = np.zeros((n, K), np.float32)
    expr[np.arange(n) % 2 == 0, 0] = 1.0          # even cells express gene a, odd cells gene b
    expr[np.arange(n) % 2 == 1, 1 % K] = 1.0
    t.add_cells(n, positions=np.zeros((n, 3)), K=K, expression=expr)
    t.expression_names = ["a", "b"][:K]
    pre, post = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    keep = pre != post
    pre, post = pre[keep].astype(np.int32), post[keep].astype(np.int32)
    t.connectivity = SparseConnectivity(pre, post, np.full(len(pre), 5, np.int32), np.ones(len(pre), np.int32))
    return t


def _run(t, params, seed=0):
    return BilinearSelectStage().run(t, params, {}, {}, np.random.default_rng(seed))


def test_neutral_is_noop():
    t = _tissue(10)
    out = _run(copy.deepcopy(t), {})
    assert np.array_equal(out.connectivity.pre, t.connectivity.pre)
    assert BilinearSelectStage.cost(100, 1000, {}) == (0, 0)


def test_rank_one_rule_gives_the_expected_probabilities():
    # A = [[1], [0]], B = [[0], [1]]: score 1 only for a -> b pairs; gain 10, bias -5: p = sigmoid(5) or sigmoid(-5)
    t = _tissue()
    n0 = len(t.connectivity.pre)
    out = _run(t, {"A": [[1.0], [0.0]], "B": [[0.0], [1.0]], "gain": 10.0, "bias": -5.0})
    c = out.connectivity
    even = np.arange(80) % 2 == 0
    ab = np.sum(even[c.pre] & ~even[c.post]) / (n0 / 4 * 80 / 79)
    other = np.sum(~(even[c.pre] & ~even[c.post])) / (3 * n0 / 4)
    sig = lambda x: 1 / (1 + np.exp(-x))
    assert ab == pytest.approx(sig(5.0), abs=0.03)
    assert other == pytest.approx(sig(-5.0), abs=0.01)


def test_knockout_column_removes_its_term():
    t = _tissue()
    t.expression[:, 0] = 0.0                     # gene a knocked out
    out = _run(t, {"A": [[1.0], [0.0]], "B": [[0.0], [1.0]], "gain": 10.0, "bias": -5.0})
    c = out.connectivity
    even = np.arange(80) % 2 == 0
    assert np.mean(even[c.pre] & ~even[c.post]) < 0.5      # no longer enriched


def test_channels_by_name_and_shape_errors():
    t = _tissue()
    out = _run(copy.deepcopy(t), {"A": [[1.0]], "B": [[1.0]], "pre_channels": ["a"], "post_channels": ["b"],
                                  "gain": 10.0, "bias": -5.0})
    c = out.connectivity
    even = np.arange(80) % 2 == 0
    assert np.mean(even[c.pre] & ~even[c.post]) > 0.8
    with pytest.raises(ValueError):
        _run(copy.deepcopy(t), {"A": [[1.0, 0.0]], "B": [[1.0]]})
    with pytest.raises(ValueError):
        _run(copy.deepcopy(t), {"A": [[1.0]], "B": [[1.0]], "pre_channels": ["zz"]})


def test_symmetric_rule_and_determinism():
    t = _tissue(40)
    p = {"A": [[1.0], [-1.0]], "B": [[1.0], [-1.0]], "gain": 6.0}
    a = _run(copy.deepcopy(t), p, seed=4)
    b = _run(copy.deepcopy(t), p, seed=4)
    assert np.array_equal(a.connectivity.pre, b.connectivity.pre)
    even = np.arange(40) % 2 == 0
    same = even[a.connectivity.pre] == even[a.connectivity.post]
    assert same.mean() > 0.8                     # A = B: like connects to like


def test_cost_within_factor_3():
    params = {"A": np.ones((2, 2)).tolist(), "B": np.ones((2, 2)).tolist()}

    def run(N, E):
        rng = np.random.default_rng(0)
        t = Tissue.empty(2)
        t.add_cells(N, positions=np.zeros((N, 3)), K=2, expression=rng.random((N, 2)).astype(np.float32))
        t.connectivity = SparseConnectivity(rng.integers(0, N, E).astype(np.int32), rng.integers(0, N, E).astype(np.int32),
                                            np.full(E, 5, np.int32), np.ones(E, np.int32))
        tracemalloc.start()
        t0 = time.perf_counter()
        BilinearSelectStage().run(t, params, {}, {}, rng)
        dt = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        return peak, dt

    peak, _ = run(20000, 200000)
    declared = BilinearSelectStage.cost(20000, 200000, params)[0]
    assert declared / 3 <= peak <= declared * 3, (peak, declared)
    small = min(run(20000, 200000)[1] for _ in range(3))
    big = min(run(80000, 800000)[1] for _ in range(3))
    ratio = BilinearSelectStage.cost(80000, 800000, params)[1] / BilinearSelectStage.cost(20000, 200000, params)[1]
    assert ratio / 3 <= big / small <= ratio * 3
