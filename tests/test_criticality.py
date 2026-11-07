"""Criticality measures (neurogenesis.criticality) on branching processes with known m, and their failure modes."""
import numpy as np
import pytest

from neurogenesis import criticality as C


@pytest.mark.parametrize("m", [0.8, 0.95, 0.99])
def test_branching_mr_recovers_m_and_is_robust_to_subsampling(m):
    a = C.branching_process(m, 100_000, h=0.5 if m < 0.99 else 0.05, n=10_000, rng=1)
    assert C.branching_mr(a)["m"] == pytest.approx(m, abs=0.01)
    sub = np.random.default_rng(2).binomial(a, 0.1)            # 10 % of the units observed
    assert C.branching_mr(sub)["m"] == pytest.approx(m, abs=0.015)


def test_critical_process_has_mean_field_exponents_and_scaling():
    a = C.branching_process(1.0, 300_000, h=0.01, n=5000, rng=1)
    s = C.summary(a, bin_ticks=1)
    assert s["m"] == pytest.approx(1.0, abs=0.01)
    assert s["alpha_size"] == pytest.approx(1.5, abs=0.1)     # mean field: 3/2
    assert 1.6 < s["alpha_duration"] < 2.1                   # mean field: 2 (finite-size estimates are lower)
    assert s["gamma_fit"] == pytest.approx(s["gamma_pred"], abs=0.15)
    assert s["ks_size"] < 0.05


def test_powerlaw_fit_recovers_exponent_of_a_sampled_power_law():
    rng = np.random.default_rng(3)
    x = np.floor((1 - rng.random(20000)) ** (-1 / 1.5)).astype(int)      # continuous alpha 2.5, floored
    f = C.powerlaw_fit(x[x <= 10_000], xmin=5, xmax=10_000)
    assert f["alpha"] == pytest.approx(2.5, abs=0.1)
    assert f["n"] > 0 and f["ks"] < 0.05


def test_avalanches_split_on_empty_bins_and_drop_edges():
    c = np.array([1, 0, 2, 3, 0, 0, 1, 1, 1, 0, 4])
    s, d = C.avalanches(c)
    assert s.tolist() == [5, 3] and d.tolist() == [2, 3]


def test_degenerate_inputs_give_nan_not_errors():
    assert np.isnan(C.branching_mr(np.ones(1000))["m"])
    assert np.isnan(C.powerlaw_fit([1, 2, 3])["alpha"])
    s = C.summary(np.zeros(5000))
    assert s["n_avalanches"] == 0 and np.isnan(s["alpha_size"])


def test_zsum_matches_exact_sum():
    a = np.array([1.2, 1.5, 2.0])
    exact = np.array([(np.arange(3, 50_001, dtype=float) ** -x).sum() for x in a])
    assert np.allclose(C._zsum(a, 3, 50_000), exact, rtol=1e-6)
