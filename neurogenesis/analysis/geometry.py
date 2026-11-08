"""Geometry of population representations and of connectivity (NumPy).

- `participation_ratio`: effective number of dimensions of a variance spectrum, (sum l)^2 / sum l^2 (Gao et al. 2017,
  bioRxiv "A theory of multineuronal dimensionality"; used for representations and connectivity by Chakravarthula et
  al. 2026, Nat Neurosci). 1 for a single dimension, n for n equal ones.
- `cvpca`: cross-validated PCA (Stringer et al. 2019, Nature): responses of the same neurons to the same stimuli in two
  repeats; principal axes from repeat 1, and on each axis the covariance between the two repeats' projections, which
  noise independent between repeats does not bias. Returns the reliable (stimulus-specific) variance per dimension, its
  total, the fraction of the variance it explains, and the participation ratio of its positive part.
- `connectivity_dimensionality`: participation ratio of the squared singular values of a weight matrix (how many
  independent patterns a projection can carry).

Units: responses in any unit (spike counts per window); the outputs are variances in that unit squared, fractions and
numbers of dimensions. Costs: cvpca O(S N min(S, N)) for S stimuli and N neurons; connectivity_dimensionality
O(n_pre n_post min(n_pre, n_post)), dense (state the size you call it with: it is meant for population-level blocks,
e.g. n <= 4096).
"""
from __future__ import annotations

import numpy as np


def participation_ratio(spectrum) -> float:
    """(sum l)^2 / sum l^2 of the non-negative entries of `spectrum` (negative entries, e.g. noise in a
    cross-validated spectrum, are set to 0). 0 for an empty or all-zero spectrum."""
    s = np.clip(np.asarray(spectrum, np.float64).ravel(), 0.0, None)
    q = float(np.sum(s * s))
    return float(np.sum(s) ** 2 / q) if q > 0 else 0.0


def cvpca(x1, x2) -> dict:
    """Cross-validated PCA of responses x1, x2 (S stimuli, N neurons): the same stimuli in two repeats.

    Each repeat is centred over stimuli. The principal axes v_k come from repeat 1; the reliable variance on axis k is
    mean_s (x1_s . v_k)(x2_s . v_k), which has expectation 0 when the two repeats share no stimulus-specific signal.
    Returns dict(spectrum (min(S, N),), reliable (sum of the spectrum = mean_s x1_s . x2_s, independent of the axes),
    total (mean of the two repeats' total variances), fraction (reliable / total, in [-1, 1]; 0 when total is 0),
    dim (participation ratio of the spectrum's positive part)). Needs S >= 2."""
    a = np.asarray(x1, np.float64)
    b = np.asarray(x2, np.float64)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError(f"x1 and x2 must be two (stimuli, neurons) arrays of the same shape, got {a.shape} and {b.shape}")
    s = a.shape[0]
    if s < 2:
        raise ValueError("cvpca needs at least 2 stimuli")
    a = a - a.mean(0)
    b = b - b.mean(0)
    _, _, vt = np.linalg.svd(a, full_matrices=False)
    spectrum = np.sum((a @ vt.T) * (b @ vt.T), 0) / s
    reliable = float(np.sum(a * b) / s)
    total = 0.5 * float(np.sum(a * a) + np.sum(b * b)) / s
    return dict(spectrum=spectrum, reliable=reliable, total=total, fraction=reliable / total if total > 0 else 0.0,
                dim=participation_ratio(spectrum))


def connectivity_dimensionality(pre, post, weight, n_pre: int | None = None, n_post: int | None = None,
                                pre_offset: int = 0, post_offset: int = 0) -> float:
    """Participation ratio of the squared singular values of the (n_pre, n_post) weight matrix of the synapses
    `pre` -> `post` (indices minus the offsets; repeated pairs add up). Dense: for population blocks of a few thousand
    neurons at most. 0 for a matrix without non-zero weight."""
    pre = np.asarray(pre, np.int64) - int(pre_offset)
    post = np.asarray(post, np.int64) - int(post_offset)
    w = np.asarray(weight, np.float64)
    n_pre = int(n_pre if n_pre is not None else (pre.max() + 1 if len(pre) else 0))
    n_post = int(n_post if n_post is not None else (post.max() + 1 if len(post) else 0))
    if n_pre == 0 or n_post == 0:
        return 0.0
    keep = (pre >= 0) & (pre < n_pre) & (post >= 0) & (post < n_post)
    m = np.zeros((n_pre, n_post))
    np.add.at(m, (pre[keep], post[keep]), w[keep])
    return participation_ratio(np.linalg.svd(m, compute_uv=False) ** 2)
