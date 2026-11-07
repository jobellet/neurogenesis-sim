"""Structural measures of a grown tissue or network: cell mosaics, connection lengths, modules (NumPy).

Connectivity is given as arrays of presynaptic and postsynaptic cell indices (`Tissue.connectivity.pre / post`, or
`SNNNetwork.synapse_arrays`); labels are any per-cell integer partition (clones, regions, cell types).
"""
from __future__ import annotations

import numpy as np


def nearest_neighbour_regularity(xy) -> float:
    """Nearest-neighbour regularity index of a cell mosaic: mean / s.d. of each cell's distance to its nearest neighbour
    (about 1.9 for random positions; larger for regular mosaics, e.g. retinal cell types)."""
    xy = np.asarray(xy, float)
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1)) + np.diag(np.full(len(xy), np.inf))
    nn = d.min(1)
    return float(nn.mean() / max(nn.std(), 1e-12))


def connection_lengths(positions, pre, post) -> np.ndarray:
    """Euclidean length of every synapse (space units)."""
    p = np.asarray(positions, float)
    return np.linalg.norm(p[np.asarray(pre)] - p[np.asarray(post)], axis=1)


def within_group_fraction(pre, post, labels) -> float:
    """Fraction of synapses whose two cells share a label (e.g. the clone: 1 = fully segregated islands). nan
    without synapses."""
    lab = np.asarray(labels)
    pre, post = np.asarray(pre), np.asarray(post)
    return float(np.mean(lab[pre] == lab[post])) if len(pre) else float("nan")


def modularity(pre, post, labels, weights=None) -> float:
    """Newman's modularity Q of a partition of a directed graph (Leicht & Newman 2008, Phys Rev Lett):
    Q = (1/E) sum_ij (A_ij - k_i^out k_j^in / E) delta(c_i, c_j), with absolute weights if given. O(E + N).
    0 for a random graph, up to 1 for disconnected modules; nan without synapses."""
    pre, post = np.asarray(pre), np.asarray(post)
    if len(pre) == 0:
        return float("nan")
    w = np.ones(len(pre)) if weights is None else np.abs(np.asarray(weights, float))
    lab = np.asarray(labels)
    _, c = np.unique(lab, return_inverse=True)
    m = w.sum()
    inside = w[c[pre] == c[post]].sum() / m
    k_out = np.bincount(c[pre], w, c.max() + 1)
    k_in = np.bincount(c[post], w, c.max() + 1)
    return float(inside - (k_out * k_in).sum() / m ** 2)
