"""J10 connectome measures: known answers, brute-force checks on small graphs, degenerate inputs."""
import itertools

import numpy as np
import pytest

from neurogenesis.analysis import connectome as cx


def _random_graph(n=25, p=0.2, seed=0):
    rng = np.random.default_rng(seed)
    A = rng.random((n, n)) < p
    np.fill_diagonal(A, False)
    pre, post = np.nonzero(A)
    return A, pre, post


def test_edges_deduplicates_and_drops_self_loops():
    a, b, n = cx.edges([0, 0, 1, 2, 2], [1, 1, 1, 0, 0], n=4)
    assert n == 4 and a.tolist() == [0, 2] and b.tolist() == [1, 0]
    with pytest.raises(ValueError):
        cx.edges([0], [5], n=3)


def test_degrees_and_skewness():
    # a star: cell 0 projects to 1..5
    k_in, k_out = cx.degrees([0] * 5, [1, 2, 3, 4, 5], n=6)
    assert k_out.tolist() == [5, 0, 0, 0, 0, 0] and k_in.tolist() == [0, 1, 1, 1, 1, 1]
    s = cx.degree_stats([0] * 5, [1, 2, 3, 4, 5], n=6)
    assert s["out_skew"] > s["in_skew"]
    assert s["out_mean"] == pytest.approx(5 / 6)
    assert np.isnan(cx.degree_stats([], [], n=0)["in_mean"])


def test_reciprocity_known_answers():
    # all reciprocal: r = 1
    r = cx.reciprocity([0, 1, 1, 2], [1, 0, 2, 1], n=3)
    assert r["fraction"] == 1.0 and r["pairs"] == 2
    # a pure chain has no reciprocal pairs: r < 0
    r = cx.reciprocity([0, 1, 2], [1, 2, 3], n=4)
    assert r["fraction"] == 0.0 and r["r"] < 0
    assert np.isnan(cx.reciprocity([], [], n=3)["fraction"])


def test_reciprocity_matches_pearson_brute_force():
    A, pre, post = _random_graph(30, 0.15, 3)
    n = len(A)
    off = ~np.eye(n, dtype=bool)
    expected = np.corrcoef(A[off].astype(float), A.T[off].astype(float))[0, 1]
    assert cx.reciprocity(pre, post, n)["r"] == pytest.approx(expected, abs=1e-12)


def test_reciprocity_of_random_graph_is_near_zero():
    _, pre, post = _random_graph(300, 0.05, 1)
    r = cx.reciprocity(pre, post, 300)
    assert abs(r["r"]) < 0.03 and r["overrepresentation"] == pytest.approx(1.0, abs=0.3)


def _brute_simplices(A, max_dim):
    n = len(A)
    out = [n]
    for k in range(1, max_dim + 1):
        c = 0
        for seq in itertools.permutations(range(n), k + 1):
            if all(A[seq[i], seq[j]] for i in range(k + 1) for j in range(i + 1, k + 1)):
                c += 1
        out.append(c)
    return out


def test_directed_simplices_match_brute_force():
    A, pre, post = _random_graph(9, 0.45, 7)
    assert cx.directed_simplices(pre, post, 9, 3).tolist() == _brute_simplices(A, 3)


def test_directed_simplices_of_a_transitive_tournament():
    # all i -> j for i < j on 5 cells: every ordered subset in increasing order is a simplex: C(5, k + 1)
    pre, post = np.triu_indices(5, 1)
    assert cx.directed_simplices(pre, post, 5, 5).tolist() == [5, 10, 10, 5, 1, 0]


def test_directed_simplices_cycle_has_no_2_simplex():
    assert cx.directed_simplices([0, 1, 2], [1, 2, 0], 3, 3).tolist() == [3, 3, 0, 0]
    assert cx.directed_simplices([], [], 4, 2).tolist() == [4, 0, 0]
    with pytest.raises(ValueError):
        pre, post = np.triu_indices(12, 1)
        cx.directed_simplices(pre, post, 12, 6, max_simplices=10)


def test_distance_dependent_probability_brute_force():
    rng = np.random.default_rng(2)
    pos = rng.random((60, 3)) * 10
    D = np.linalg.norm(pos[:, None] - pos[None], axis=-1)
    A = (rng.random((60, 60)) < np.exp(-D / 3)) & ~np.eye(60, dtype=bool)
    pre, post = np.nonzero(A)
    bins = [0, 2, 4, 6]
    r = cx.distance_dependent_probability(pos, pre, post, bins)
    off = ~np.eye(60, dtype=bool)
    for k in range(3):
        m = off & (D >= bins[k]) & (D < bins[k + 1])
        assert r["pairs"][k] == m.sum()
        assert r["connected"][k] == (A & m).sum()
    assert r["probability"][0] > r["probability"][2]
    with pytest.raises(ValueError):
        cx.distance_dependent_probability(pos, pre, post, [0, np.inf])


def test_common_neighbour_probability_brute_force():
    A, pre, post = _random_graph(20, 0.2, 5)
    n = len(A)
    U = A | A.T
    CN = (U.astype(int) @ U.astype(int))
    off = ~np.eye(n, dtype=bool)
    r = cx.common_neighbour_probability(pre, post, n, max_cn=4)
    for c in range(5):
        m = off & ((CN == c) if c < 4 else (CN >= 4))
        assert r["pairs"][c] == m.sum(), c
        assert r["connected"][c] == (A & m).sum(), c
    assert r["pairs"].sum() == n * (n - 1)


def test_common_neighbour_probability_with_distance():
    rng = np.random.default_rng(4)
    pos = rng.random((40, 3)) * 5
    A, pre, post = _random_graph(40, 0.15, 6)
    D = np.linalg.norm(pos[:, None] - pos[None], axis=-1)
    U = A | A.T
    CN = U.astype(int) @ U.astype(int)
    m0 = ~np.eye(40, dtype=bool) & (D < 2.0)
    r = cx.common_neighbour_probability(pre, post, 40, positions=pos, d_max=2.0, max_cn=30)
    assert r["pairs"].sum() == m0.sum()
    for c in range(4):
        assert r["connected"][c] == (A & m0 & (CN == c)).sum()


def test_summary_is_deterministic_and_does_not_modify_inputs():
    _, pre, post = _random_graph(40, 0.1, 9)
    pre0 = pre.copy()
    s1 = cx.summary(pre, post, 40, max_dim=3)
    s2 = cx.summary(pre, post, 40, max_dim=3)
    assert s1["simplices"].tolist() == s2["simplices"].tolist()
    assert np.array_equal(pre, pre0)


def test_fit_metrics_on_a_tissue():
    from neurogenesis.fitting import METRICS
    from neurogenesis.tissue import SparseConnectivity, Tissue
    t = Tissue.empty()
    t.add_cells(5, positions=np.zeros((5, 3)), cell_type=np.array([0, 0, 0, 0, 1], np.int32))
    pre, post = np.triu_indices(5, 1)
    t.connectivity = SparseConnectivity(pre.astype(np.int32), post.astype(np.int32), np.ones(len(pre), np.int32),
                                        np.ones(len(pre), np.int32))
    assert METRICS["simplex_count"](t, {"dim": 3}) == 5.0
    assert METRICS["simplex_count"](t, {"dim": 3, "cell_type": 0}) == 1.0     # 4 cells: one 3-simplex
    assert METRICS["reciprocity"](t, {"measure": "fraction"}) == 0.0
    assert METRICS["degree_skewness"](t, {"direction": "out"}) == pytest.approx(0.0)
