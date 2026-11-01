"""Cell differentiation and molecular identity.

* Lateral-inhibition differentiation (Notch-Delta type, after Collier et al. 1996): two fates per neuron (excitability,
  pacemaker) from a positional bias plus noise, each cell inhibited by the mean fate of its neighbours. The excitability
  fate sets the threshold and time constants; the pacemaker fate makes intrinsic bursters.
* Molecular identity: K identities per region, from a genetic code on position, argmax_k (a_k0 + a_k . pos); deterministic.
"""
from __future__ import annotations

import numpy as np


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


N_IDENTITIES = 6


def neutral_identity(k=N_IDENTITIES):
    """Founding identity code: all logits 0 (every neuron takes identity 0)."""
    return dict(logits=np.zeros((k, 4)))


def neutral_typed_guidance(gd, k=N_IDENTITIES):
    """Founding identity-dependent guidance of a projection: no offset, full expression (no effect)."""
    return dict(gd, type_c=np.zeros((k, 3)), type_s=np.ones(k))


def identities(code, pos):
    L = np.asarray(code["logits"], float)
    return np.argmax(L[:, 0][None, :] + pos @ L[:, 1:].T, axis=1)


def neutral_differentiation():
    """Founding values of the differentiation step: no effect (uniform fates, threshold 1024, base time constants, no pacemaker)."""
    return dict(exc=dict(b0=0.0, b=np.zeros(3), c=0.0, r=0.2), pace=dict(b0=-6.0, c=0.0, r=0.2),
                theta0=0.0, theta1=0.0, s1v=0.0, s1s=0.0, period=50.0, duty=10.0)


def lateral_fates(pos, b0, b, c, r, rng, iters=12, gain=8.0):
    """Fate in [0, 1] per cell: positional bias plus noise, inhibited by the mean fate of neighbours (Gaussian kernel of
    range r, rows normalised)."""
    x0 = np.clip(sigmoid(b0 + pos @ np.asarray(b, float)) + 0.05 * rng.standard_normal(len(pos)), 0.0, 1.0)
    d2 = ((pos[:, None, :] - pos[None, :, :]) ** 2).sum(-1)
    K = np.exp(-d2 / (2 * r ** 2))
    np.fill_diagonal(K, 0.0)
    K /= np.maximum(K.sum(1, keepdims=True), 1e-12)
    x = x0.copy()
    for _ in range(iters):
        x = sigmoid(gain * ((x0 - 0.5) + (x - 0.5) - c * (K @ x)))
    return x


def differentiate(dg, pos, base_v, base_s, rng):
    """Per-neuron threshold, time constants and pacemaker identity from the two fates."""
    f = lateral_fates(pos, dg["exc"]["b0"], dg["exc"]["b"], dg["exc"]["c"], dg["exc"]["r"], rng)
    p = lateral_fates(pos, dg["pace"]["b0"], np.zeros(3), dg["pace"]["c"], dg["pace"]["r"], rng)
    thr = np.clip(np.round(1024 * 2.0 ** (dg["theta0"] + dg["theta1"] * (f - 0.5))), 384, 2000).astype(int)
    sv = np.clip(np.round(base_v + dg["s1v"] * (f - 0.5)), 1, 8).astype(int)
    ss = np.clip(np.round(base_s + dg["s1s"] * (f - 0.5)), 1, 8).astype(int)
    pace = p > 0.5
    return dict(threshold=thr, shift_v=sv, shift_s=ss, pacemaker=pace, period=int(np.clip(round(dg["period"]), 20, 200)),
                duty=int(np.clip(round(dg["duty"]), 4, 40)), fate=f, pace_fate=p)
