"""Tests for functional connectomics metrics and stimulus bank (Phase M3)."""
import numpy as np
import pytest

from neurogenesis.metrics.function import (
    multiplicity_regression,
    pair_correlations,
    residual_correlations,
    student_t_pvalue,
    tuning_metrics,
)
from neurogenesis.metrics.stimuli import generate_natural_movie, movie_input_currents


def test_pair_correlations_synthetic():
    T = 200
    rng = np.random.default_rng(42)
    base = rng.standard_normal(T)
    # Cell 0 and 1: highly correlated (r ~ 0.95)
    s0 = base + 0.3 * rng.standard_normal(T)
    s1 = base + 0.3 * rng.standard_normal(T)
    # Cell 2: uncorrelated (r ~ 0)
    s2 = rng.standard_normal(T)
    # Cell 3: anti-correlated (r ~ -0.95)
    s3 = -base + 0.3 * rng.standard_normal(T)

    data = np.column_stack([s0, s1, s2, s3])
    pre = [0, 0, 0]
    post = [1, 2, 3]

    corrs = pair_correlations(data, pre, post)
    assert len(corrs) == 3
    assert corrs[0] > 0.85
    assert abs(corrs[1]) < 0.2
    assert corrs[2] < -0.85


def test_residual_correlations_and_multiplicity_regression_planted_slope():
    rng = np.random.default_rng(10)
    P = 150
    # True relationship: correlation decays with distance
    soma_dist = rng.uniform(10.0, 100.0, size=P)
    base_corr = 0.8 - 0.005 * soma_dist + rng.normal(0, 0.05, size=P)

    # Residual correlation after subtracting distance trend
    res_corr = residual_correlations(base_corr, soma_dist)
    # Residuals must have mean near zero
    assert abs(float(np.mean(res_corr))) < 1e-4

    # Planted positive multiplicity slope: contacts increase with residual correlation
    # MICrONS like-to-like rule
    true_slope = 4.0
    contacts = np.maximum(1, np.round(2.5 + true_slope * res_corr + rng.normal(0, 0.3, size=P))).astype(np.int32)

    pre = rng.integers(0, 30, size=P)
    post = rng.integers(0, 30, size=P)
    reg = multiplicity_regression(res_corr, contacts, pre=pre, post=post)

    assert reg["slope"] > 0.0
    assert reg["p_value"] < 0.01  # Acceptance number: significant positive slope
    assert reg["r_squared"] > 0.1
    assert len(reg["reciprocity"]) == 5

    # Shuffled control must give slope ~ 0 and non-significant p-value
    shuffled_contacts = rng.permutation(contacts)
    shuff_reg = multiplicity_regression(res_corr, shuffled_contacts, pre=pre, post=post)
    assert abs(shuff_reg["slope"]) < abs(reg["slope"])
    assert shuff_reg["p_value"] > 0.01


def test_gOSI_hand_computed():
    angles = [0.0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]
    # Sharp cell responding only at angle 0
    r_sharp = np.array([[12.0, 0.0, 0.0, 0.0]])
    m_sharp = tuning_metrics(r_sharp, angles)
    assert np.isclose(m_sharp["gOSI"][0], 1.0, atol=1e-5)

    # Flat unselective cell
    r_flat = np.array([[5.0, 5.0, 5.0, 5.0]])
    m_flat = tuning_metrics(r_flat, angles)
    assert np.isclose(m_flat["gOSI"][0], 0.0, atol=1e-5)

    # Intermediate cell: response at 0 and pi/2 (orthogonal) -> phasors cancel -> 0
    r_cross = np.array([[10.0, 0.0, 10.0, 0.0]])
    assert np.isclose(tuning_metrics(r_cross, angles)["gOSI"][0], 0.0, atol=1e-5)

    # Surround suppression index with annulus
    r_annulus = np.array([[4.0, 0.0, 0.0, 0.0]])
    m_ssi = tuning_metrics(r_sharp, angles, annulus_responses=r_annulus)
    # (12 - 4) / 12 = 8 / 12 = 0.6667
    assert np.isclose(m_ssi["SSI"][0], 8.0 / 12.0, atol=1e-4)


def test_student_t_pvalue():
    # Symmetric two-tailed p-value
    assert student_t_pvalue(0.0, 10) == 1.0
    assert student_t_pvalue(10.0, 20) < 1e-6
    # Degrees of freedom check
    assert student_t_pvalue(2.0, 1) > student_t_pvalue(2.0, 50)


def test_natural_movie_stimuli_determinism():
    m1 = generate_natural_movie(n_frames=20, height=16, width=16, seed=42)
    m2 = generate_natural_movie(n_frames=20, height=16, width=16, seed=42)
    assert np.array_equal(m1, m2)

    # Seed isolation
    m3 = generate_natural_movie(n_frames=20, height=16, width=16, seed=99)
    assert not np.array_equal(m1, m3)

    # Current projection
    positions = np.array([[0.2, 0.2], [0.8, 0.8]])
    c1 = movie_input_currents(m1, positions, gain=150.0)
    c2 = movie_input_currents(m2, positions, gain=150.0)
    assert np.allclose(c1, c2)
    assert c1.shape == (20, 2)
    assert np.all(c1 >= 0.0)
