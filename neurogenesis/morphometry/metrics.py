"""Registered morphometry metrics for fitting (E2) and validation assays (E4).

Metrics:
- `morphology_wasserstein_to_reference`: squared 2-Wasserstein distance between a grown population's
  persistence images and a reference set.
- `laminar_density_profile_ks`: two-sample Fasano-Franceschini 2D Kolmogorov-Smirnov test (Fasano & Franceschini 1987)
  on the two leading PCA components of descriptor vectors (stratification profiles / morphometrics).
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import numpy as np

from ..fitting import register_metric, select
from ..tissue import Tissue
from .features import features
from .tmd import _assignment_cost, barcodes, persistence_images


def population_wasserstein_squared(a: np.ndarray, b: np.ndarray, eps: float = 1e-2) -> float:
    """Squared 2-Wasserstein distance between two populations of feature vectors.

    If len(a) == len(b), solves exact optimal assignment with `_assignment_cost`.
    If len(a) != len(b), computes optimal transport with uniform empirical weights
    via Sinkhorn scaling iterations.
    """
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    n, m = len(a), len(b)
    if n == 0 and m == 0:
        return 0.0
    if n == 0 or m == 0:
        return float(np.sum(a ** 2) if n else np.sum(b ** 2))
    a = a.reshape(n, -1)
    b = b.reshape(m, -1)
    # Pairwise squared Euclidean distance
    C = np.sum((a[:, None, :] - b[None, :, :]) ** 2, axis=-1)
    if n == m:
        return float(_assignment_cost(C) / n)
    # Sinkhorn entropic optimal transport
    scale = float(np.median(C))
    if scale <= 1e-12:
        scale = float(np.mean(C))
    reg = max(eps * max(scale, 1e-6), 1e-6)
    K = np.exp(-C / reg)
    u = np.full(n, 1.0 / n)
    v = np.full(m, 1.0 / m)
    r = np.full(n, 1.0 / n)
    c = np.full(m, 1.0 / m)
    for _ in range(100):
        Kv = K @ v
        Kv = np.maximum(Kv, 1e-300)
        u = r / Kv
        KTu = K.T @ u
        KTu = np.maximum(KTu, 1e-300)
        v = c / KTu
    P = u[:, None] * K * v[None, :]
    return float(np.sum(P * C))


def embed_2d(data1: np.ndarray, data2: np.ndarray, method: str = "pca") -> Tuple[np.ndarray, np.ndarray]:
    """Embeds two sets of feature vectors into 2D using PCA (SVD) or lazy UMAP."""
    d1 = np.asarray(data1, np.float64)
    d2 = np.asarray(data2, np.float64)
    if method == "umap":
        try:
            import umap  # type: ignore
            reducer = umap.UMAP(n_components=2, random_state=0)
            combined = np.vstack([d1, d2])
            emb = reducer.fit_transform(combined)
            return emb[:len(d1)], emb[len(d1):]
        except ImportError:
            warnings.warn("umap-learn is not installed; falling back to PCA (SVD)", RuntimeWarning)
    # Default PCA via SVD
    combined = np.vstack([d1, d2])
    centered = combined - combined.mean(axis=0, keepdims=True)
    if combined.shape[1] <= 2:
        if combined.shape[1] == 2:
            return centered[:len(d1)], centered[len(d1):]
        pad = np.zeros((len(combined), 1))
        padded = np.hstack([centered, pad])
        return padded[:len(d1)], padded[len(d1):]
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    emb = centered @ vt[:2].T
    return emb[:len(d1)], emb[len(d1):]


def fasano_franceschini_2d(p: np.ndarray, q: np.ndarray) -> Tuple[float, float]:
    """Two-sample Fasano-Franceschini 2D Kolmogorov-Smirnov test (Fasano & Franceschini 1987).

    Returns (statistic D, p_value). Null hypothesis: p and q are drawn from the same 2D distribution.
    A criterion of p_value > 0.05 indicates no significant difference between the populations.
    """
    p = np.asarray(p, np.float64).reshape(-1, 2)
    q = np.asarray(q, np.float64).reshape(-1, 2)
    n1, n2 = len(p), len(q)
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    z = np.vstack([p, q])
    M = len(z)
    px, py = p[:, 0, None], p[:, 1, None]
    qx, qy = q[:, 0, None], q[:, 1, None]
    zx, zy = z[:, 0], z[:, 1]

    # Differences across the 4 quadrants centered at each point in z
    d1 = np.abs(((px >= zx) & (py >= zy)).mean(axis=0) - ((qx >= zx) & (qy >= zy)).mean(axis=0))
    d2 = np.abs(((px <= zx) & (py >= zy)).mean(axis=0) - ((qx <= zx) & (qy >= zy)).mean(axis=0))
    d3 = np.abs(((px <= zx) & (py <= zy)).mean(axis=0) - ((qx <= zx) & (qy <= zy)).mean(axis=0))
    d4 = np.abs(((px >= zx) & (py <= zy)).mean(axis=0) - ((qx >= zx) & (qy <= zy)).mean(axis=0))
    D = float(np.max([d1, d2, d3, d4]))

    neff = (n1 * n2) / (n1 + n2)
    std0 = float(np.std(z[:, 0]))
    std1 = float(np.std(z[:, 1]))
    if M > 1 and std0 > 1e-12 and std1 > 1e-12:
        r = float(np.corrcoef(z[:, 0], z[:, 1])[0, 1])
    else:
        r = 0.0
    r = float(np.clip(r if not np.isnan(r) else 0.0, -0.9999, 0.9999))
    factor = 1.0 + np.sqrt(1.0 - r ** 2) * (0.25 - 0.75 / max(np.sqrt(neff), 1e-6))
    factor = max(factor, 0.1)
    lam = D * np.sqrt(neff) / factor
    if lam <= 0:
        return D, 1.0
    val = sum(2.0 * ((-1) ** (j - 1)) * np.exp(-2.0 * (j ** 2) * (lam ** 2)) for j in range(1, 100))
    return D, float(np.clip(val, 0.0, 1.0))


@register_metric("morphology_wasserstein_to_reference")
def morphology_wasserstein_to_reference(t_or_vectors: Union[Tissue, np.ndarray],
                                        options_or_ref: Optional[Union[Dict[str, Any], np.ndarray]] = None,
                                        **kwargs) -> float:
    """Squared 2-Wasserstein distance from grown population persistence images to reference vectors.

    Can be used as a fitting target metric with options:
    `reference_vectors`: (M, grid*grid) reference persistence image vectors
    `grid`: persistence image grid size (default 20)
    `bounds`: (lo, hi) filtration range (default (0.0, 1.0))
    `sigma`: smoothing sigma (default 1.0)
    """
    if isinstance(t_or_vectors, Tissue):
        tissue = t_or_vectors
        o = dict(options_or_ref or {})
        o.update(kwargs)
        ref = o.get("reference_vectors")
        if ref is None:
            ref = o.get("reference")
        if ref is None:
            return 0.0
        cells = select(tissue, o)
        if len(cells) == 0 or getattr(tissue, "arbors", None) is None or tissue.arbors.n_nodes == 0:
            return float(np.sum(np.asarray(ref) ** 2))
        sub_arbor = tissue.arbors.select_cells(cells)
        if sub_arbor.n_nodes == 0:
            return float(np.sum(np.asarray(ref) ** 2))
        bars = barcodes(sub_arbor, filtration=o.get("filtration", "path"),
                        compartments=o.get("compartments", None))
        grid = int(o.get("grid", 20))
        bounds = tuple(o.get("bounds", (0.0, 1.0)))
        sigma = float(o.get("sigma", 1.0))
        imgs = persistence_images(bars, cells=cells, grid=grid, bounds=bounds, sigma=sigma)
        return population_wasserstein_squared(imgs, np.asarray(ref))
    else:
        grown = np.asarray(t_or_vectors)
        ref = np.asarray(options_or_ref if options_or_ref is not None else kwargs.get("reference_vectors"))
        return population_wasserstein_squared(grown, ref)


@register_metric("laminar_density_profile_ks")
def laminar_density_profile_ks(t_or_descriptors: Union[Tissue, np.ndarray],
                               options_or_ref: Optional[Union[Dict[str, Any], np.ndarray]] = None,
                               **kwargs) -> float:
    """Two-sample Fasano-Franceschini 2D KS test on 2 leading PCA components of descriptor vectors.

    Returns the p-value (criterion p > 0.05 indicates compatible laminar stratification).
    Can be used as a fitting metric or validation assay gate.
    """
    if isinstance(t_or_descriptors, Tissue):
        tissue = t_or_descriptors
        o = dict(options_or_ref or {})
        o.update(kwargs)
        ref = o.get("reference_profile")
        if ref is None:
            ref = o.get("reference_descriptors")
        if ref is None:
            return 1.0
        cells = select(tissue, o)
        if len(cells) == 0 or getattr(tissue, "arbors", None) is None or tissue.arbors.n_nodes == 0:
            return 0.0
        sub_arbor = tissue.arbors.select_cells(cells)
        if sub_arbor.n_nodes == 0:
            return 0.0
        feat = features(sub_arbor, n_cells=len(cells), extent=float(o.get("extent", 1.0)),
                        bins=int(o.get("bins", 16)), depth_axis=int(o.get("depth_axis", 2)))
        desc = feat.get("stratification", feat.get("radial"))
        p2d, q2d = embed_2d(desc, np.asarray(ref), method=o.get("embedding", "pca"))
        D, p_val = fasano_franceschini_2d(p2d, q2d)
        return D if o.get("return_d", False) else p_val
    else:
        desc = np.asarray(t_or_descriptors)
        ref = np.asarray(options_or_ref if options_or_ref is not None else kwargs.get("reference_profile"))
        method = kwargs.get("embedding", "pca")
        p2d, q2d = embed_2d(desc, ref, method=method)
        D, p_val = fasano_franceschini_2d(p2d, q2d)
        return D if kwargs.get("return_d", False) else p_val
