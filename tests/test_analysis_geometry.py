"""Known-answer tests of neurogenesis.analysis.geometry."""
import numpy as np
import pytest

from neurogenesis.analysis import geometry as G


def test_participation_ratio_known_values():
    assert G.participation_ratio(np.ones(7)) == pytest.approx(7.0)
    assert G.participation_ratio([5.0, 0, 0, 0]) == pytest.approx(1.0)
    assert G.participation_ratio([1.0, 1.0, -3.0]) == pytest.approx(2.0)     # negative entries ignored
    assert G.participation_ratio([]) == 0.0 and G.participation_ratio([0.0, -1.0]) == 0.0


def test_cvpca_recovers_reliable_signal_and_its_dimension():
    """Signal of rank r shared by both repeats + independent noise: the reliable fraction is the signal's share of
    the variance, the dimension is about r; pure noise gives about 0."""
    rng = np.random.default_rng(0)
    S, N, r = 2000, 60, 4
    sig = rng.standard_normal((S, r)) @ rng.standard_normal((r, N))
    noise_sd = np.sqrt(sig.var(0).sum() / N)                 # noise variance = signal variance
    x1 = sig + noise_sd * rng.standard_normal((S, N))
    x2 = sig + noise_sd * rng.standard_normal((S, N))
    out = G.cvpca(x1, x2)
    assert out["fraction"] == pytest.approx(0.5, abs=0.03)
    assert out["reliable"] == pytest.approx(float(np.sum(out["spectrum"])))
    assert 2.5 < out["dim"] <= r + 0.5
    noise = G.cvpca(rng.standard_normal((S, N)), rng.standard_normal((S, N)))
    assert abs(noise["fraction"]) < 0.03
    same = G.cvpca(sig, sig)
    assert same["fraction"] == pytest.approx(1.0)


def test_cvpca_degenerate_inputs():
    z = np.zeros((5, 3))
    assert G.cvpca(z, z)["fraction"] == 0.0 and G.cvpca(z, z)["dim"] == 0.0
    with pytest.raises(ValueError):
        G.cvpca(np.zeros((1, 3)), np.zeros((1, 3)))
    with pytest.raises(ValueError):
        G.cvpca(np.zeros((4, 3)), np.zeros((4, 2)))


def test_connectivity_dimensionality_known_values():
    n = 10
    i = np.arange(n)
    assert G.connectivity_dimensionality(i, i, np.ones(n), n, n) == pytest.approx(n)          # identity: n dims
    pre, post = np.repeat(i, n), np.tile(i, n)
    assert G.connectivity_dimensionality(pre, post, np.ones(n * n), n, n) == pytest.approx(1.0)  # all-to-all, equal: 1
    assert G.connectivity_dimensionality(i + 100, i + 50, np.ones(n), n, n, 100, 50) == pytest.approx(n)
    assert G.connectivity_dimensionality([], [], [], 3, 3) == 0.0


def test_inputs_are_not_modified():
    rng = np.random.default_rng(1)
    x1, x2 = rng.random((20, 5)), rng.random((20, 5))
    c1, c2 = x1.copy(), x2.copy()
    G.cvpca(x1, x2)
    assert np.array_equal(x1, c1) and np.array_equal(x2, c2)
