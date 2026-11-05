"""MorphoPy-style arbor features as fixed-length float32 vectors, one row per cell (berenslab/MorphoPy, JOSS 2020).

Per compartment (axon, dendrite, neurite or user labels): soma-relative 3D spatial density (binned histogram + Gaussian
smoothing, a KDE approximation), radial-distance and path-distance distributions, the conditional distribution of the
local branch angle given the somatic path distance, and the stratification profile (density vs depth along one axis,
to check laminar peaks). Histograms are weighted by segment length, so they do not depend on the node sampling.
All O(nodes) with `np.bincount` over a combined (cell, bin) index; no Python loop over nodes.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple, Union

import numpy as np

from ..arbors import ArborStore, compartment_id
from .tmd import _jump

FEATURE_BYTES_PER_NODE = 150
FEATURE_OPS_PER_NODE = 120


def features_cost(n_nodes: int) -> Tuple[int, int]:
    """Declared (bytes, operations) of `features` for `n_nodes` nodes (without the output vectors)."""
    return FEATURE_BYTES_PER_NODE * n_nodes, FEATURE_OPS_PER_NODE * n_nodes


def _smooth(h: np.ndarray, sigma: float, axes: Sequence[int]) -> np.ndarray:
    if sigma <= 0:
        return h
    rad = max(1, int(np.ceil(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sigma) ** 2)
    k /= k.sum()
    for ax in axes:
        n = h.shape[ax]
        pad = [(0, 0)] * h.ndim
        pad[ax] = (rad, rad)
        hp = np.pad(h, pad)
        h = sum(k[j] * np.take(hp, np.arange(j, j + n), axis=ax) for j in range(len(k)))
    return h


def _hist(cell: np.ndarray, idx: np.ndarray, w: np.ndarray, n_cells: int, n_bins: int) -> np.ndarray:
    return np.bincount(cell * n_bins + idx, weights=w, minlength=n_cells * n_bins).reshape(n_cells, n_bins).astype(np.float64)


def _bin(x: np.ndarray, lo: float, hi: float, n: int) -> np.ndarray:
    return np.clip(((x - lo) / max(hi - lo, 1e-12) * n).astype(np.int64), 0, n - 1)


def _norm(h: np.ndarray) -> np.ndarray:
    s = h.sum(axis=-1, keepdims=True)
    return np.divide(h, s, out=np.zeros_like(h), where=s > 0)


def features(store: ArborStore, n_cells: Optional[int] = None, compartment: Union[str, int] = "dendrite",
             extent: float = 1.0, depth_axis: int = 2, bins: int = 16, density_bins: int = 8, angle_bins: int = 6,
             sigma: float = 1.0, normalise: bool = True) -> Dict[str, np.ndarray]:
    """Feature vectors of one compartment for every cell (rows indexed by Tissue cell, zeros where a cell has none).

    `extent` is the distance (space units) covered by the histograms: radial / path distances in [0, extent], 3D density
    and the stratification profile in [-extent, extent] around the soma (root node). Returns float32 arrays:
    `density3d` (n_cells, density_bins^3), `radial` and `path` (n_cells, bins), `angle_given_distance`
    (n_cells, bins * angle_bins; rows = path-distance bins, conditional on each row), `stratification` (n_cells, bins).
    With `normalise` each distribution sums to 1 (or to 0 for an empty cell); otherwise it holds total length.
    """
    n = int(n_cells if n_cells is not None else (store.cell.max() + 1 if store.n_nodes else 0))
    par = store.parent.astype(np.int64)
    M = store.n_nodes
    out = {"density3d": np.zeros((n, density_bins ** 3)), "radial": np.zeros((n, bins)), "path": np.zeros((n, bins)),
           "angle_given_distance": np.zeros((n, bins * angle_bins)), "stratification": np.zeros((n, bins))}
    if M:
        root, _ = _jump(par)
        rel = store.xyz.astype(np.float64) - store.xyz[root]
        path = store.path_length_to_root()
        seg = store.segment_lengths()
        sel = (store.compartment == compartment_id(compartment)) & (par >= 0)
        c, w = store.cell[sel].astype(np.int64), seg[sel]
        if len(c) > 0 and c.max() >= n:
            if len(np.unique(c)) <= n:
                _, c = np.unique(c, return_inverse=True)
            else:
                c = np.clip(c, 0, n - 1)
        r = np.linalg.norm(rel[sel], axis=1)
        out["radial"] = _hist(c, _bin(r, 0, extent, bins), w, n, bins)
        out["path"] = _hist(c, _bin(path[sel], 0, extent, bins), w, n, bins)
        ix = [_bin(rel[sel][:, a], -extent, extent, density_bins) for a in range(3)]
        d3 = _hist(c, (ix[0] * density_bins + ix[1]) * density_bins + ix[2], w, n, density_bins ** 3)
        d3 = _smooth(d3.reshape(n, *(density_bins,) * 3), sigma, (1, 2, 3))
        out["density3d"] = d3.reshape(n, -1)
        out["stratification"] = _smooth(_hist(c, _bin(rel[sel][:, depth_axis], -extent, extent, bins), w, n, bins), sigma, (1,))
        # branch angle at bifurcations (nodes with >= 2 children): angle between the first two child segments
        nc = store.children_count()
        kids = np.flatnonzero(par >= 0)
        kids = kids[np.lexsort((kids, par[kids]))]
        pk = par[kids]
        first = np.r_[True, pk[1:] != pk[:-1]]
        rank = np.arange(len(kids)) - np.maximum.accumulate(np.where(first, np.arange(len(kids)), 0))
        k0, k1 = kids[rank == 0], kids[rank == 1]
        k0 = k0[nc[par[k0]] >= 2]
        k1 = k1[nc[par[k1]] >= 2]
        if len(k0) and len(k0) == len(k1):
            p = par[k0]
            va, vb = store.xyz[k0] - store.xyz[p], store.xyz[k1] - store.xyz[p]
            cosang = np.einsum("ij,ij->i", va, vb) / np.maximum(np.linalg.norm(va, axis=1) * np.linalg.norm(vb, axis=1), 1e-12)
            ang = np.arccos(np.clip(cosang, -1, 1))
            ok = store.compartment[p] == compartment_id(compartment)
            ok |= store.compartment[k0] == compartment_id(compartment)
            cc = store.cell[p][ok].astype(np.int64)
            if len(cc) > 0 and cc.max() >= n:
                if len(np.unique(cc)) <= n:
                    _, cc = np.unique(cc, return_inverse=True)
                else:
                    cc = np.clip(cc, 0, n - 1)
            ab = _bin(ang[ok], 0, np.pi, angle_bins)
            db = _bin(path[p][ok], 0, extent, bins)
            out["angle_given_distance"] = np.bincount(cc * bins * angle_bins + db * angle_bins + ab, minlength=n * bins * angle_bins
                                                      ).reshape(n, bins * angle_bins).astype(np.float64)
    if normalise:
        for k in ("density3d", "radial", "path", "stratification"):
            out[k] = _norm(out[k])
        a = out["angle_given_distance"].reshape(n, bins, angle_bins)
        out["angle_given_distance"] = _norm(a).reshape(n, -1)
    return {k: v.astype(np.float32) for k, v in out.items()}


def stratification_peaks(profile: np.ndarray, min_prominence: float = 0.05) -> np.ndarray:
    """Indices of the local maxima of a 1D stratification profile whose height exceeds its neighbours by
    `min_prominence` of the profile maximum (laminar peaks)."""
    p = np.asarray(profile, np.float64)
    if p.size < 3 or p.max() <= 0:
        return np.zeros(0, np.int64)
    inner = (p[1:-1] > p[:-2]) & (p[1:-1] >= p[2:]) & (p[1:-1] - np.minimum(p[:-2], p[2:]) >= min_prominence * p.max())
    return np.flatnonzero(inner) + 1
