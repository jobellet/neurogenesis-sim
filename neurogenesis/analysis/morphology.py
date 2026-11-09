"""Morphometry of arbors (N6): scalar morphometrics, Sholl profiles and topological morphology descriptors (NumPy).

Inputs are `ArborStore`s (`neurogenesis.arbors`: grown by `grow_arbors`, read from SWC, imported skeletons). Each
cell's tree is rooted at its root node (normally the soma, `parent = -1`). Definitions:
- a *branch point* is a non-root node with two or more children, a *tip* a non-root node without children, a *stem* a
  child of a root;
- the *branch order* of a node is the number of branch points strictly between it and its root;
- a *branch* is the path between a node that is a root, branch point or tip and its nearest such ancestor; its
  tortuosity is path length / Euclidean distance (>= 1).
Scalar morphometrics follow the feature set of MorphoPy (Laturnus et al. 2020, J Open Source Softw 5:2339); the
topological morphology descriptor (TMD) is that of Kanari et al. 2018, Neuroinformatics 16:3-13, and barcodes are
compared through persistence images (Adams et al. 2017, J Mach Learn Res 18:1-35).

Vectorised over all nodes (pointer jumping, O(M log depth)) or tree levels (O(M) per level); nothing loops over nodes in
Python. Nothing here changes the store.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np

from ..arbors import ArborStore

FEATURES = ("radial", "path")


def _accumulate_to_root(parent: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Sum of `values` over each node and all its ancestors (pointer jumping)."""
    d = values.astype(np.float64).copy()
    p = parent.astype(np.int64).copy()
    while np.any(p >= 0):
        has = p >= 0
        d = d + np.where(has, d[np.maximum(p, 0)], 0.0)
        p = np.where(has, p[np.maximum(p, 0)], -1)
    return d


def root_of(store: ArborStore) -> np.ndarray:
    """Index of each node's root (pointer jumping)."""
    r = np.arange(store.n_nodes, dtype=np.int64)
    p = store.parent.astype(np.int64).copy()
    while np.any(p >= 0):
        has = p >= 0
        r = np.where(has, p, r)
        p = np.where(has, store.parent[np.maximum(p, 0)].astype(np.int64), -1)
    return r


def node_kinds(store: ArborStore) -> Dict[str, np.ndarray]:
    """Boolean masks {"root", "branch_point", "tip", "stem"} over nodes."""
    nc = store.children_count()
    root = store.parent < 0
    stem = np.zeros(store.n_nodes, bool)
    has = ~root
    stem[has] = root[store.parent[has]]
    return dict(root=root, branch_point=~root & (nc >= 2), tip=~root & (nc == 0), stem=stem)


def branch_order(store: ArborStore) -> np.ndarray:
    """Number of branch points strictly between each node and its root (0 for roots and the first branches)."""
    if store.n_nodes == 0:
        return np.zeros(0, np.int64)
    bp = node_kinds(store)["branch_point"].astype(np.float64)
    has = store.parent >= 0
    own = np.where(has, bp[np.maximum(store.parent, 0)], 0.0)       # 1 if this node's parent is a branch point
    return np.rint(_accumulate_to_root(store.parent, own)).astype(np.int64)


def feature_values(store: ArborStore, feature: str = "radial") -> np.ndarray:
    """Per-node filtration value: Euclidean distance to its root ("radial") or path length to it ("path")."""
    if feature not in FEATURES:
        raise ValueError(f"unknown feature {feature!r} ({', '.join(FEATURES)})")
    if feature == "path":
        return store.path_length_to_root()
    r = root_of(store)
    return np.linalg.norm(store.xyz.astype(np.float64) - store.xyz[r].astype(np.float64), axis=1)


def _branches(store: ArborStore, kinds: Dict[str, np.ndarray]):
    """(child node, critical ancestor) of every branch: critical = root, branch point or tip."""
    critical = kinds["root"] | kinds["branch_point"] | kinds["tip"]
    anc = store.parent.astype(np.int64).copy()
    while True:
        bad = (anc >= 0) & ~critical[np.maximum(anc, 0)]
        if not bad.any():
            break
        anc[bad] = store.parent[anc[bad]]
    child = np.flatnonzero(critical & (anc >= 0))
    return child, anc[child]


def morphometrics(store: ArborStore, cells: Optional[Sequence[int]] = None) -> Dict[str, np.ndarray]:
    """Scalar morphometrics of each cell's arbor (space units), as arrays aligned with `cells` (default: every cell
    with nodes, ascending). Keys: cell, n_nodes, n_stems, n_branch_points, n_tips, total_length, max_path_length,
    max_radial_distance, mean_radial_distance (of the tips), width, depth, height (extents along x, y, z),
    max_branch_order, n_branches, mean_branch_length, median_tortuosity, max_tortuosity (of branches; nan without
    branches), mean_branch_angle (radians, between the two first children of each branch point; nan without
    branch points). A cell without nodes gets zeros (nan for means)."""
    cells = np.unique(store.cell) if cells is None else np.asarray(cells, np.int64).ravel()
    K = len(cells)
    lut_size = int(max(store.cell.max(initial=-1), cells.max(initial=-1)) + 1)
    lut = np.full(lut_size, -1, np.int64)
    lut[cells] = np.arange(K)
    out: Dict[str, np.ndarray] = dict(cell=cells)
    node_c = lut[store.cell] if store.n_nodes else np.zeros(0, np.int64)
    m = node_c >= 0
    nc = node_c[m]
    kinds = node_kinds(store)
    count = lambda mask: np.bincount(nc, mask[m].astype(np.float64), minlength=K).astype(np.int64)
    out["n_nodes"] = np.bincount(nc, minlength=K).astype(np.int64)
    out["n_stems"] = count(kinds["stem"])
    out["n_branch_points"] = count(kinds["branch_point"])
    out["n_tips"] = count(kinds["tip"])
    seg = store.segment_lengths()
    out["total_length"] = np.bincount(nc, seg[m], minlength=K)

    def group_max(v, mask=None, fill=0.0):
        r = np.full(K, -np.inf)
        sel = m if mask is None else (m & mask)
        np.maximum.at(r, node_c[sel], v[sel])
        return np.where(np.isfinite(r), r, fill)

    plen = store.path_length_to_root()
    rad = feature_values(store, "radial")
    out["max_path_length"] = group_max(plen)
    out["max_radial_distance"] = group_max(rad)
    n_tips = out["n_tips"]
    with np.errstate(invalid="ignore", divide="ignore"):
        out["mean_radial_distance"] = np.where(n_tips > 0, np.bincount(nc, (rad * kinds["tip"])[m], minlength=K) / n_tips,
                                               np.nan)
    xyz = store.xyz.astype(np.float64)
    for axis, name in enumerate(("width", "depth", "height")):
        hi = group_max(xyz[:, axis], fill=0.0)
        lo = -group_max(-xyz[:, axis], fill=0.0)
        out[name] = hi - lo
    out["max_branch_order"] = group_max(branch_order(store).astype(np.float64)).astype(np.int64)

    child, anc = _branches(store, kinds)
    bc = lut[store.cell[child]] if len(child) else np.zeros(0, np.int64)
    keep = bc >= 0
    child, anc, bc = child[keep], anc[keep], bc[keep]
    blen = plen[child] - plen[anc]
    euc = np.linalg.norm(xyz[child] - xyz[anc], axis=1)
    tort = np.where(euc > 1e-12, blen / np.maximum(euc, 1e-12), 1.0)
    n_br = np.bincount(bc, minlength=K)
    out["n_branches"] = n_br.astype(np.int64)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["mean_branch_length"] = np.where(n_br > 0, np.bincount(bc, blen, minlength=K) / n_br, np.nan)
    tmax = np.full(K, -np.inf)
    np.maximum.at(tmax, bc, tort)
    out["max_tortuosity"] = np.where(n_br > 0, tmax, np.nan)
    med = np.full(K, np.nan)
    if len(bc):
        o = np.lexsort((tort, bc))
        sb, st = bc[o], tort[o]
        starts = np.searchsorted(sb, np.arange(K))
        lo_i = starts + (n_br - 1) // 2
        hi_i = starts + n_br // 2
        has = n_br > 0
        med[has] = 0.5 * (st[lo_i[has]] + st[hi_i[has]])
    out["median_tortuosity"] = med

    # angle between the first two children of every branch point (and root with >= 2 stems is not included)
    bp = np.flatnonzero(kinds["branch_point"])
    ang = np.full(K, np.nan)
    if len(bp):
        nonroot = np.flatnonzero(store.parent >= 0)
        par = store.parent[nonroot]
        o = np.lexsort((nonroot, par))
        ch, pa = nonroot[o], par[o]
        first = np.searchsorted(pa, bp)
        c1, c2 = ch[first], ch[first + 1]
        v1 = xyz[c1] - xyz[bp]
        v2 = xyz[c2] - xyz[bp]
        cosv = np.sum(v1 * v2, 1) / np.maximum(np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1), 1e-12)
        a = np.arccos(np.clip(cosv, -1, 1))
        pc = lut[store.cell[bp]]
        ok = pc >= 0
        cnt = np.bincount(pc[ok], minlength=K)
        with np.errstate(invalid="ignore", divide="ignore"):
            ang = np.where(cnt > 0, np.bincount(pc[ok], a[ok], minlength=K) / cnt, np.nan)
    out["mean_branch_angle"] = ang
    return out


def sholl(store: ArborStore, cell: int, radii: Sequence[float], center=None) -> np.ndarray:
    """Sholl profile (Sholl 1953, J Anat): number of segments of `cell` crossing each sphere of radius r around
    `center` (default its root). O(M x len(radii))."""
    radii = np.asarray(radii, np.float64)
    nodes = np.flatnonzero((store.cell == cell) & (store.parent >= 0))
    if len(nodes) == 0:
        return np.zeros(len(radii), np.int64)
    xyz = store.xyz.astype(np.float64)
    if center is None:
        center = xyz[root_of(store)[nodes[0]]]
    d_child = np.linalg.norm(xyz[nodes] - center, axis=1)
    d_par = np.linalg.norm(xyz[store.parent[nodes]] - center, axis=1)
    lo, hi = np.minimum(d_child, d_par), np.maximum(d_child, d_par)
    return np.sum((lo[None, :] < radii[:, None]) & (hi[None, :] >= radii[:, None]), axis=1).astype(np.int64)


def tmd_barcodes(store: ArborStore, feature: str = "radial", cells: Optional[Sequence[int]] = None) -> Dict[int, np.ndarray]:
    """Topological morphology descriptor of each cell's tree (Kanari et al. 2018): a barcode of (birth, death) bars,
    one per tip. Every node carries the largest feature value f of the tips below it; at each branch point (or root
    with several stems) the child subtree with the largest value continues (elder rule; ties go to the lower node
    index) and every other child subtree ends with a bar (its value, f(branch point)); the subtree that reaches the
    root ends with (its value, f(root)). `feature` is "radial" (Euclidean distance to the root) or "path" (path
    length). Returns {cell: (n_tips, 2) float array} sorted by decreasing birth. Cost O(M) per tree level."""
    out: Dict[int, np.ndarray] = {}
    M = store.n_nodes
    cells = np.unique(store.cell) if cells is None else np.asarray(cells, np.int64).ravel()
    if M == 0:
        return {int(c): np.zeros((0, 2)) for c in cells}
    f = feature_values(store, feature)
    nc = store.children_count()
    mval = np.where(nc == 0, f, -np.inf)
    depth = np.rint(_accumulate_to_root(store.parent, (store.parent >= 0).astype(np.float64))).astype(np.int64)
    order = np.argsort(-depth, kind="stable")
    sd = depth[order]
    bounds = np.flatnonzero(np.r_[True, sd[1:] != sd[:-1], True])
    for s, e in zip(bounds[:-1], bounds[1:]):
        lvl = order[s:e]
        lvl = lvl[store.parent[lvl] >= 0]
        if len(lvl):
            np.maximum.at(mval, store.parent[lvl], mval[lvl])
    child = np.flatnonzero(store.parent >= 0)
    par = store.parent[child]
    bars_cell, birth, death = [], [], []
    multi = nc[par] >= 2
    c2, p2 = child[multi], par[multi]
    if len(c2):
        o = np.lexsort((c2, -mval[c2], p2))
        c2, p2 = c2[o], p2[o]
        loser = np.r_[False, p2[1:] == p2[:-1]]
        bars_cell.append(store.cell[c2[loser]])
        birth.append(mval[c2[loser]])
        death.append(f[p2[loser]])
    roots = np.flatnonzero(store.parent < 0)
    roots = roots[nc[roots] > 0]                       # a lone root (no neurite) has no tip and no bar
    bars_cell.append(store.cell[roots])
    birth.append(mval[roots])
    death.append(f[roots])
    bc = np.concatenate(bars_cell)
    bars = np.stack([np.concatenate(birth), np.concatenate(death)], axis=1)
    o = np.lexsort((-bars[:, 0], bc))
    bc, bars = bc[o], bars[o]
    for c in cells:
        out[int(c)] = bars[bc == c]
    return out


def persistence_image(bars, extent: Optional[Sequence[float]] = None, resolution: int = 20,
                      bandwidth: Optional[float] = None) -> np.ndarray:
    """Persistence image of a barcode (Adams et al. 2017): Gaussian kernels at (birth, death) weighted by the bar
    length |birth - death|, sampled on a resolution x resolution grid over `extent` = (lo, hi) for both axes (default
    0 to the largest value), normalised to sum 1 (zeros for an empty barcode). `bandwidth` defaults to (hi - lo) / 10."""
    bars = np.asarray(bars, np.float64).reshape(-1, 2)
    if extent is None:
        hi = float(bars.max()) if len(bars) else 1.0
        extent = (0.0, hi if hi > 0 else 1.0)
    lo, hi = float(extent[0]), float(extent[1])
    bw = (hi - lo) / 10.0 if bandwidth is None else float(bandwidth)
    g = np.linspace(lo, hi, resolution)
    if len(bars) == 0:
        return np.zeros((resolution, resolution))
    w = np.abs(bars[:, 0] - bars[:, 1])
    kb = np.exp(-0.5 * ((g[None, :] - bars[:, 0:1]) / bw) ** 2)
    kd = np.exp(-0.5 * ((g[None, :] - bars[:, 1:2]) / bw) ** 2)
    img = np.einsum("k,ki,kj->ij", w, kb, kd)
    s = img.sum()
    return img / s if s > 0 else img


def barcode_distance(a, b, resolution: int = 20, bandwidth: Optional[float] = None) -> float:
    """L1 distance between the persistence images of two barcodes on a common extent: 0 for identical barcodes, at
    most 2."""
    a = np.asarray(a, np.float64).reshape(-1, 2)
    b = np.asarray(b, np.float64).reshape(-1, 2)
    hi = max(float(a.max()) if len(a) else 0.0, float(b.max()) if len(b) else 0.0)
    ext = (0.0, hi if hi > 0 else 1.0)
    return float(np.abs(persistence_image(a, ext, resolution, bandwidth) - persistence_image(b, ext, resolution, bandwidth)).sum())
