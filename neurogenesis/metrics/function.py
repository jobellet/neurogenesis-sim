"""Functional connectomics metrics: pair correlations, distance adjustment and multiplicity regression (M3).

Grounding:
MICrONS visual cortex millimetre cube (~75,000 recorded cells, >200,000 segmented neurons, ~500M synapses):
Connection probability and the number of synaptic contacts per connected pair increase linearly with the
neurons' residual signal correlation (correlation left after correcting for physical distance and retinotopy;
P = 0.009; Nature 640:8058, 2025; PMC11981947).

Functions:
- `pair_correlations`: Pearson correlation of response series for a list of (pre, post) pairs.
- `residual_correlations`: residual signal correlation after regressing out somatic distance and RF distance.
- `multiplicity_regression`: OLS regression of synaptic multiplicity (contacts) on residual correlation with
  analytic inference (slope, standard error, p-value, reciprocity per bin).
- `tuning_metrics`: global orientation selectivity index (gOSI) and surround suppression index.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import numpy as np

from ..fitting import register_metric, select
from ..tissue import Tissue

_PAIR_CHUNK = 1 << 18


def pair_correlations(spikes_or_rates: np.ndarray, pre: Sequence[int], post: Sequence[int],
                      chunk_size: int = _PAIR_CHUNK) -> np.ndarray:
    """Pearson correlation of response series for given (pre, post) cell pairs.

    `spikes_or_rates`: (T, N) array across time ticks or trial conditions.
    `pre`, `post`: integer arrays of length P.
    Vectorised O(P x T) in blocks of `chunk_size` pairs; memory bounded.
    """
    data = np.asarray(spikes_or_rates, dtype=np.float64)
    pre_idx = np.asarray(pre, dtype=np.int64)
    post_idx = np.asarray(post, dtype=np.int64)
    P = len(pre_idx)
    if P == 0 or data.size == 0:
        return np.zeros(P, dtype=np.float64)

    # Standardize time series across time (axis 0)
    mu = np.mean(data, axis=0, keepdims=True)
    std = np.std(data, axis=0, keepdims=True)
    std = np.where(std < 1e-12, 1.0, std)
    z = (data - mu) / std
    T = data.shape[0]

    out = np.zeros(P, dtype=np.float64)
    for start in range(0, P, chunk_size):
        end = min(P, start + chunk_size)
        pr = pre_idx[start:end]
        po = post_idx[start:end]
        # Inner product over time T divided by T
        corr = np.sum(z[:, pr] * z[:, po], axis=0) / max(T, 1)
        out[start:end] = np.clip(corr, -1.0, 1.0)
    return out


def residual_correlations(pairs_corr: Sequence[float], soma_distance: Sequence[float],
                          rf_distance: Optional[Sequence[float]] = None) -> np.ndarray:
    """Per pair, subtract the linear regression of correlation on soma distance (and RF distance).

    Returns the residual signal correlation (MICrONS distance-adjusted correlation).
    """
    y = np.asarray(pairs_corr, dtype=np.float64)
    d_soma = np.asarray(soma_distance, dtype=np.float64)
    P = len(y)
    if P <= 2:
        return y.copy()

    if rf_distance is not None:
        d_rf = np.asarray(rf_distance, dtype=np.float64)
        X = np.column_stack([np.ones(P, dtype=np.float64), d_soma, d_rf])
    else:
        X = np.column_stack([np.ones(P, dtype=np.float64), d_soma])

    # OLS fit: beta = (X^T X)^-1 X^T y
    try:
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        y_hat = X @ beta
        residuals = y - y_hat
    except np.linalg.LinAlgError:
        residuals = y - np.mean(y)
    return residuals


def student_t_pvalue(t_stat: float, df: float) -> float:
    """Analytic two-tailed p-value for Student-t distribution without scipy."""
    t_val = abs(float(t_stat))
    df = float(df)
    if df <= 0 or math.isnan(t_val):
        return 1.0
    if t_val == 0.0:
        return 1.0
    # Normalization constant: 1 / (sqrt(df) * Beta(0.5, df/2))
    log_c = -0.5 * math.log(df) - (math.lgamma(0.5) + math.lgamma(df / 2.0) - math.lgamma((df + 1.0) / 2.0))
    c = math.exp(log_c)
    # Numerical integration on [0, min(t_val, 35.0)]
    limit = min(t_val, 35.0)
    n_steps = 300
    u = np.linspace(0.0, limit, n_steps + 1)
    y = c * np.exp(-0.5 * (df + 1.0) * np.log1p(u ** 2 / df))
    if hasattr(np, "trapezoid"):
        cdf_0_to_t = float(np.trapezoid(y, u))
    else:
        cdf_0_to_t = float(np.trapz(y, u))
    p_val = 2.0 * max(0.0, 0.5 - cdf_0_to_t)
    return float(np.clip(p_val, 0.0, 1.0))


def multiplicity_regression(residual_corr: Sequence[float], contacts: Sequence[int],
                            pre: Optional[Sequence[int]] = None, post: Optional[Sequence[int]] = None,
                            bins: int = 5) -> Dict[str, Any]:
    """OLS regression of synaptic contact count (multiplicity) on residual signal correlation.

    Analytic OLS inference: slope, standard error, t-stat, p-value and r_squared.
    Reports reciprocity across residual correlation bins if (pre, post) pair indices are supplied.
    """
    x = np.asarray(residual_corr, dtype=np.float64)
    y = np.asarray(contacts, dtype=np.float64)
    n = len(x)
    if n < 3:
        return {
            "slope": 0.0,
            "intercept": float(np.mean(y)) if n else 0.0,
            "se": 0.0,
            "t_stat": 0.0,
            "p_value": 1.0,
            "r_squared": 0.0,
            "reciprocity": np.zeros(bins, dtype=np.float64),
            "n_pairs": n
        }

    x_mean = np.mean(x)
    y_mean = np.mean(y)
    dx = x - x_mean
    dy = y - y_mean
    Sxx = float(np.sum(dx ** 2))
    Syy = float(np.sum(dy ** 2))
    Sxy = float(np.sum(dx * dy))

    if Sxx > 1e-12:
        slope = Sxy / Sxx
        intercept = y_mean - slope * x_mean
        y_pred = intercept + slope * x
        ss_res = float(np.sum((y - y_pred) ** 2))
        r_squared = float(max(0.0, 1.0 - ss_res / (Syy if Syy > 1e-12 else 1.0)))
        df = max(1, n - 2)
        s2 = ss_res / df
        se = float(math.sqrt(max(0.0, s2 / Sxx)))
        t_stat = float(slope / se) if se > 1e-12 else 0.0
        p_value = student_t_pvalue(t_stat, df)
    else:
        slope, intercept, se, t_stat, p_value, r_squared = 0.0, y_mean, 0.0, 0.0, 1.0, 0.0

    # Reciprocity per residual correlation bin
    recip_binned = np.zeros(bins, dtype=np.float64)
    if pre is not None and post is not None and len(pre) == n:
        pre_arr = np.asarray(pre, dtype=np.int64)
        post_arr = np.asarray(post, dtype=np.int64)
        pair_set = set(zip(pre_arr, post_arr))
        is_reciprocal = np.array([(p, q) in pair_set for q, p in zip(pre_arr, post_arr)], dtype=np.float64)

        x_min, x_max = float(np.min(x)), float(np.max(x))
        if x_max > x_min:
            bin_idx = np.clip(((x - x_min) / (x_max - x_min) * bins).astype(np.int64), 0, bins - 1)
            for b in range(bins):
                m = bin_idx == b
                if np.any(m):
                    recip_binned[b] = float(np.mean(is_reciprocal[m]))

    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "se": float(se),
        "t_stat": float(t_stat),
        "p_value": float(p_value),
        "r_squared": float(r_squared),
        "reciprocity": recip_binned,
        "n_pairs": n
    }


def tuning_metrics(responses: np.ndarray, angles: Sequence[float],
                   annulus_responses: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """Computes global orientation selectivity index (gOSI) and surround suppression index (SSI).

    `responses`: (N, n_angles) tuning responses to oriented gratings.
    `angles`: orientations in radians.
    gOSI = ``|sum_theta R(theta) e^{2i theta}| / sum_theta R(theta)``.
    SSI = max(0, (R_center - R_annulus) / max(R_center, 1e-6)).
    """
    R = np.asarray(responses, dtype=np.float64)
    th = np.asarray(angles, dtype=np.float64)
    N = R.shape[0]
    if R.size == 0 or len(th) == 0:
        return {"gOSI": np.zeros(N, dtype=np.float32), "SSI": np.zeros(N, dtype=np.float32)}

    # gOSI calculation
    phasors = np.exp(2.0j * th)
    numerator = np.abs(np.sum(R * phasors[None, :], axis=1))
    denominator = np.sum(R, axis=1)
    gOSI = np.divide(numerator, denominator, out=np.zeros(N, dtype=np.float64), where=denominator > 1e-12)

    # SSI calculation
    if annulus_responses is not None:
        R_ann = np.asarray(annulus_responses, dtype=np.float64)
        c_max = np.max(R, axis=1)
        a_max = np.max(R_ann, axis=1)
        SSI = np.divide(c_max - a_max, np.maximum(c_max, 1e-6), out=np.zeros(N, dtype=np.float64), where=c_max > 1e-6)
        SSI = np.clip(SSI, 0.0, 1.0)
    else:
        SSI = np.zeros(N, dtype=np.float64)

    return {"gOSI": gOSI.astype(np.float32), "SSI": SSI.astype(np.float32)}


@register_metric("multiplicity_slope")
def _multiplicity_slope(tissue: Tissue, options: Dict[str, Any]) -> float:
    """Registered metric returning the multiplicity regression slope."""
    conn = getattr(tissue, "connectivity", None)
    if conn is None or len(conn.pre) == 0:
        return 0.0
    contacts = getattr(conn, "contacts", None)
    if contacts is None:
        contacts = np.ones(len(conn.pre), dtype=np.int32)
    res_corr = options.get("residual_correlations")
    if res_corr is None:
        return 0.0
    res = multiplicity_regression(res_corr, contacts, pre=conn.pre, post=conn.post)
    return float(res["slope"])


@register_metric("mean_gOSI")
def _mean_gOSI(tissue: Tissue, options: Dict[str, Any]) -> float:
    """Registered metric returning the population mean gOSI."""
    responses = options.get("responses")
    angles = options.get("angles")
    if responses is None or angles is None:
        return 0.0
    metrics = tuning_metrics(responses, angles)
    return float(np.mean(metrics["gOSI"]))
