"""Statistical connectome measures (J10): degrees, weights, reciprocity, distance- and common-neighbour-dependent
connection probability, triad motifs, directed simplices (NumPy).

The same functions run on grown networks and on imported connectomes. Connectivity is given as arrays of presynaptic
and postsynaptic cell indices (`Tissue.connectivity.pre / post`, `SNNNetwork.synapse_arrays`) and the number of cells
`n`; multiple synapses between the same ordered pair count as one connection and self-connections are ignored, so every
measure is on the binary directed graph A (A_ij = 1 if i connects to j). Vocabulary of statistical connectome analysis:
Song et al. 2005, PLoS Biol (reciprocity, motifs); Perin et al. 2011, PNAS (common neighbours); Reimann et al. 2017,
Front Comput Neurosci and 2019, Nat Commun (directed simplices); Holland & Leinhardt 1976, Sociol Methodol (triad
census); Connectome-Manipulator, Pokorny et al. 2025.

Costs: O(N + E) for degrees and reciprocity; O(pairs within d_max) for distance bins (cell list); O(sum_k deg_k^2) for
common neighbours and the triad census; directed simplices grow with the number of simplices found (bounded by `max_simplices`).
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from ..spatial import CellList, _concat_ranges


def edges(pre, post, n: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, int]:
    """(pre, post, n) of the binary directed graph: unique ordered pairs, self-connections removed, sorted by (pre,
    post). n defaults to 1 + the largest index."""
    pre = np.asarray(pre, np.int64).ravel()
    post = np.asarray(post, np.int64).ravel()
    if pre.shape != post.shape:
        raise ValueError("pre and post must have the same length")
    if n is None:
        n = int(max(pre.max(initial=-1), post.max(initial=-1)) + 1)
    if len(pre) and (min(pre.min(), post.min()) < 0 or max(pre.max(), post.max()) >= n):
        raise ValueError(f"cell indices must lie in [0, {n})")
    keep = pre != post
    key = np.unique(pre[keep] * n + post[keep])
    return key // n, key % n, int(n)


def degrees(pre, post, n: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray]:
    """(in-degree, out-degree) of every cell in the binary directed graph."""
    a, b, n = edges(pre, post, n)
    return np.bincount(b, minlength=n), np.bincount(a, minlength=n)


def _skewness(x) -> float:
    x = np.asarray(x, float)
    sd = x.std()
    return float(np.mean((x - x.mean()) ** 3) / sd ** 3) if sd > 0 else 0.0


def degree_stats(pre, post, n: Optional[int] = None) -> Dict[str, float]:
    """Mean, s.d. and skewness of in- and out-degrees (skewness 0 for a constant degree). A heavier out-degree tail
    gives out_skew > in_skew."""
    k_in, k_out = degrees(pre, post, n)
    if len(k_in) == 0:
        return dict(in_mean=float("nan"), in_sd=float("nan"), in_skew=float("nan"),
                    out_mean=float("nan"), out_sd=float("nan"), out_skew=float("nan"))
    return dict(in_mean=float(k_in.mean()), in_sd=float(k_in.std()), in_skew=_skewness(k_in),
                out_mean=float(k_out.mean()), out_sd=float(k_out.std()), out_skew=_skewness(k_out))


def reciprocity(pre, post, n: Optional[int] = None) -> Dict[str, float]:
    """Reciprocal connections of the binary directed graph:
    - `fraction`: fraction of connections i -> j whose reverse j -> i exists;
    - `pairs`: number of reciprocally connected unordered pairs;
    - `overrepresentation`: fraction / p, with p = E / (n (n - 1)) the connection probability (1 when reciprocal
      pairs are as frequent as in a random graph of the same density; Song et al. 2005 report about 4 in rat cortex);
    - `r`: Pearson correlation between A_ij and A_ji over ordered pairs i != j, (R / M - p^2) / (p (1 - p)) with R
      ordered reciprocal pairs and M = n (n - 1) (0 for an Erdos-Renyi graph, 1 when every connection is reciprocal).
    nan without connections. O(E log E)."""
    a, b, n = edges(pre, post, n)
    E = len(a)
    if E == 0 or n < 2:
        return dict(fraction=float("nan"), pairs=0, overrepresentation=float("nan"), r=float("nan"))
    key = a * n + b
    rev = b * n + a
    R = int(np.isin(rev, key, assume_unique=True).sum())
    M = n * (n - 1)
    p = E / M
    frac = R / E
    r = (R / M - p * p) / (p * (1 - p)) if 0 < p < 1 else float("nan")
    return dict(fraction=float(frac), pairs=R // 2, overrepresentation=float(frac / p), r=float(r))


def distance_dependent_probability(positions, pre, post, bins: Sequence[float], cells=None) -> Dict[str, np.ndarray]:
    """Connection probability as a function of distance (space units): for each bin [bins[k], bins[k+1]), the number of
    ordered pairs (i, j), i != j, at that distance and the fraction of them with i -> j. Pairs come from the cell list,
    so memory is O(pairs within bins[-1]) and `bins[-1]` must be finite. `cells` restricts both ends of the pairs to
    those cells (default all). Returns {"bins", "pairs", "connected", "probability"} (probability nan for an empty
    bin)."""
    pos = np.asarray(positions, np.float64)
    bins = np.asarray(bins, np.float64)
    if bins.ndim != 1 or len(bins) < 2 or not np.all(np.diff(bins) > 0) or not np.isfinite(bins[-1]):
        raise ValueError("bins must be finite, increasing edges (at least 2)")
    n = len(pos)
    idx = np.arange(n) if cells is None else np.unique(np.asarray(cells, np.int64))
    nb = len(bins) - 1
    pairs = np.zeros(nb, np.int64)
    connected = np.zeros(nb, np.int64)
    if len(idx):
        d_max = float(bins[-1])
        q, k, d = CellList(pos[idx], d_max).query_radius(pos[idx], d_max, return_distances=True)
        ok = (idx[q] != idx[k]) & (d >= bins[0]) & (d < d_max)
        pairs = np.bincount(np.searchsorted(bins, d[ok], side="right") - 1, minlength=nb)[:nb]
        a, b, _ = edges(pre, post, n)
        sel = np.zeros(n, bool)
        sel[idx] = True
        m = sel[a] & sel[b]
        de = np.linalg.norm(pos[a[m]] - pos[b[m]], axis=1)
        inb = (de >= bins[0]) & (de < d_max)
        connected = np.bincount(np.searchsorted(bins, de[inb], side="right") - 1, minlength=nb)[:nb]
    with np.errstate(invalid="ignore", divide="ignore"):
        prob = np.where(pairs > 0, connected / np.maximum(pairs, 1), np.nan)
    return dict(bins=bins, pairs=pairs, connected=connected, probability=prob)


def _neighbour_lists(a, b, n):
    """CSR lists of the undirected neighbours of every cell (union of in- and out-neighbours)."""
    u = np.unique(np.concatenate([a * n + b, b * n + a]))
    src, dst = u // n, u % n
    ptr = np.concatenate([[0], np.cumsum(np.bincount(src, minlength=n))])
    return ptr, dst


def common_neighbour_probability(pre, post, n: Optional[int] = None, positions=None, d_max: Optional[float] = None,
                                 max_cn: int = 10, max_pairs: int = 50_000_000) -> Dict[str, np.ndarray]:
    """Connection probability of ordered pairs (i, j), i != j, as a function of their number of common neighbours
    (cells connected to or from both, ignoring direction; Perin et al. 2011, PNAS). `positions` and `d_max` restrict
    the pairs to those closer than d_max. Counts of pairs with 0 common neighbours are exact (all pairs minus the
    others; the cell list gives the pairs within d_max). Pairs with more than `max_cn` common neighbours are counted in
    the last bin. Returns {"cn", "pairs", "connected", "probability"}. Cost O(sum_k deg_k^2) to list the 2-paths;
    raises if that exceeds `max_pairs`."""
    a, b, n = edges(pre, post, n)
    ptr, nb = _neighbour_lists(a, b, n)
    deg = np.diff(ptr)
    n_paths = int(np.sum(deg.astype(np.int64) ** 2))
    if n_paths > max_pairs:
        raise ValueError(f"common_neighbour_probability: {n_paths} two-paths exceed max_pairs={max_pairs}")
    # every pair (i, j) of neighbours of a middle cell k is a 2-path i - k - j
    mid = np.repeat(np.arange(n), deg)                   # one entry (k, i) per neighbour i of k, i = nb
    reps = deg[mid]                                      # each (k, i) pairs with every j in N(k)
    i = np.repeat(nb, reps)
    j = nb[_concat_ranges(ptr[mid], reps)] if len(reps) else np.zeros(0, np.int64)
    ok = i != j
    key = i[ok] * n + j[ok]
    pair_key, cn = np.unique(key, return_counts=True)
    if positions is not None and d_max is not None:
        pos = np.asarray(positions, np.float64)
        pi, pj = pair_key // n, pair_key % n
        near = np.linalg.norm(pos[pi] - pos[pj], axis=1) < d_max
        pair_key, cn = pair_key[near], cn[near]
        q, k, _ = CellList(pos, float(d_max)).query_radius(pos, float(d_max), return_distances=True)
        total = int(np.sum(q != k))
        conn_mask = np.linalg.norm(pos[a] - pos[b], axis=1) < d_max
        conn_key = (a * n + b)[conn_mask]
    else:
        total = n * (n - 1)
        conn_key = a * n + b
    cn = np.minimum(cn, max_cn)
    pairs = np.bincount(cn, minlength=max_cn + 1).astype(np.int64)
    pairs[0] = total - len(pair_key)
    is_conn = np.isin(pair_key, conn_key, assume_unique=True)
    connected = np.bincount(cn[is_conn], minlength=max_cn + 1).astype(np.int64)
    connected[0] = len(conn_key) - int(is_conn.sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        prob = np.where(pairs > 0, connected / np.maximum(pairs, 1), np.nan)
    return dict(cn=np.arange(max_cn + 1), pairs=pairs, connected=connected, probability=prob)


def directed_simplices(pre, post, n: Optional[int] = None, max_dim: int = 7,
                       max_simplices: int = 20_000_000) -> np.ndarray:
    """Number of directed simplices of each dimension 0..max_dim in the directed flag complex of the graph (Reimann et
    al. 2017, Front Comput Neurosci): a k-simplex is an ordered list of k + 1 distinct cells (v0, ..., vk) with
    v_a -> v_b for every a < b (v0 is the source, vk the sink). Dimension 0 counts cells, 1 connections; a reciprocal
    pair gives two 1-simplices. Simplices are listed level by level, extending each (k-1)-simplex by the
    out-neighbours of its sink that receive from every other vertex; memory and time grow with the number of simplices
    (raises if a level would exceed `max_simplices`). Trailing zeros are kept up to max_dim."""
    a, b, n = edges(pre, post, n)
    counts = np.zeros(max_dim + 1, np.int64)
    counts[0] = n
    if max_dim < 1 or len(a) == 0:
        return counts
    key = a * n + b                                       # sorted (edges() sorts by pre, then post)
    ptr = np.concatenate([[0], np.cumsum(np.bincount(a, minlength=n))])
    S = np.stack([a, b], axis=1)                          # 1-simplices
    counts[1] = len(S)
    for dim in range(2, max_dim + 1):
        sink = S[:, -1]
        reps = ptr[sink + 1] - ptr[sink]
        if int(reps.sum()) > max_simplices:
            raise ValueError(f"directed_simplices: more than max_simplices={max_simplices} candidates in dimension {dim}")
        w = b[_concat_ranges(ptr[sink], reps)]
        rows = np.repeat(np.arange(len(S)), reps)
        ok = np.ones(len(w), bool)
        for col in range(S.shape[1] - 1):
            v = S[rows, col]
            k = v * n + w
            pos = np.searchsorted(key, k)
            ok &= (pos < len(key)) & (key[np.minimum(pos, len(key) - 1)] == k)
        S = np.concatenate([S[rows[ok]], w[ok, None]], axis=1)
        counts[dim] = len(S)
        if len(S) == 0:
            break
    return counts


def weight_stats(weight, pre=None, post=None, n: Optional[int] = None, per_connection: bool = False) -> Dict[str, Dict[str, float]]:
    """Distribution of synaptic weights, for excitatory (w > 0), inhibitory (w < 0) and all non-zero weights: count,
    mean, s.d., coefficient of variation, skewness and median of |w|, and the mean (`log_mu`) and s.d. (`log_sigma`)
    of log |w| (the parameters of a log-normal fit; cortical weights are close to log-normal, Song et al. 2005).
    With `per_connection`, the weights of synapses between the same ordered pair (pre, post) are summed first (needs
    pre and post). Zero weights are ignored. nan entries for an empty group. O(E) (O(E log E) per connection)."""
    w = np.asarray(weight, np.float64).ravel()
    if per_connection:
        if pre is None or post is None:
            raise ValueError("weight_stats: per_connection needs pre and post")
        pre = np.asarray(pre, np.int64).ravel()
        post = np.asarray(post, np.int64).ravel()
        if n is None:
            n = int(max(pre.max(initial=-1), post.max(initial=-1)) + 1)
        key, inv = np.unique(pre * n + post, return_inverse=True)
        w = np.bincount(inv, w, minlength=len(key))
    out = {}
    for name, m in (("exc", w > 0), ("inh", w < 0), ("all", w != 0)):
        a = np.abs(w[m])
        if len(a) == 0:
            out[name] = dict(count=0, mean=float("nan"), sd=float("nan"), cv=float("nan"), skew=float("nan"),
                             median=float("nan"), log_mu=float("nan"), log_sigma=float("nan"))
            continue
        lg = np.log(a)
        out[name] = dict(count=int(len(a)), mean=float(a.mean()), sd=float(a.std()), cv=float(a.std() / a.mean()),
                         skew=_skewness(a), median=float(np.median(a)), log_mu=float(lg.mean()), log_sigma=float(lg.std()))
    return out


TRIAD_NAMES = ("003", "012", "102", "021D", "021U", "021C", "111D", "111U", "030T", "030C", "201", "120D", "120U",
               "120C", "210", "300")
# class of the 3-cell graph with adjacency bits a->b 1, b->a 2, a->c 4, c->a 8, b->c 16, c->b 32 (index in TRIAD_NAMES)
_TRIAD_CLASS = np.array([0, 1, 1, 2, 1, 3, 5, 7, 1, 5, 4, 6, 2, 7, 6, 10, 1, 5, 3, 7, 4, 8, 8, 12, 5, 9, 8, 13, 6, 13,
                         11, 14, 1, 4, 5, 6, 5, 8, 9, 13, 3, 8, 8, 11, 7, 12, 13, 14, 2, 6, 7, 10, 6, 11, 13, 14, 7, 13,
                         12, 14, 10, 14, 14, 15], np.int64)


def triad_census(pre, post, n: Optional[int] = None, max_pairs: int = 50_000_000) -> Dict[str, int]:
    """Number of unordered cell triples in each of the 16 isomorphism classes of directed 3-cell graphs (Holland &
    Leinhardt 1976; names M-A-N: mutual, asymmetric, null dyads, then D down, U up, C cyclic, T transitive; e.g. 030T
    a feed-forward loop, 030C a 3-cycle, 300 all six connections). Triples with two or three connected pairs come
    from the 2-paths (O(sum_k deg_k^2), raises above `max_pairs`); those with one connected pair and the empty ones are
    counted without listing them. The counts sum to C(n, 3)."""
    a, b, n = edges(pre, post, n)
    counts = dict.fromkeys(TRIAD_NAMES, 0)
    total = n * (n - 1) * (n - 2) // 6
    if n < 3:
        return counts
    ptr, nb = _neighbour_lists(a, b, n)
    deg = np.diff(ptr)
    n_paths = int(np.sum(deg.astype(np.int64) ** 2))
    if n_paths > max_pairs:
        raise ValueError(f"triad_census: {n_paths} two-paths exceed max_pairs={max_pairs}")
    key = a * n + b
    mid = np.repeat(np.arange(n), deg)
    reps = deg[mid]
    i = np.repeat(nb, reps)
    j = nb[_concat_ranges(ptr[mid], reps)] if len(reps) else np.zeros(0, np.int64)
    k = np.repeat(mid, reps)
    ok = i < j
    i, j, k = i[ok], j[ok], k[ok]
    # connected triples {i, j, k}: sorted rows, unique
    T = np.sort(np.stack([i, j, k], axis=1), axis=1)
    if len(T):
        o = np.lexsort((T[:, 2], T[:, 1], T[:, 0]))
        T = T[o]
        T = T[np.r_[True, np.any(T[1:] != T[:-1], axis=1)]]

    def has(u, v):
        q = u * n + v
        pos = np.searchsorted(key, q)
        return (pos < len(key)) & (key[np.minimum(pos, max(len(key) - 1, 0))] == q) if len(key) else np.zeros(len(q), bool)

    if len(T):
        x, y, z = T[:, 0], T[:, 1], T[:, 2]
        code = (has(x, y) * 1 + has(y, x) * 2 + has(x, z) * 4 + has(z, x) * 8 + has(y, z) * 16 + has(z, y) * 32)
        cls = np.bincount(_TRIAD_CLASS[code], minlength=16)
        for c, name in enumerate(TRIAD_NAMES):
            counts[name] += int(cls[c])
    # triples with exactly one connected pair: third cell adjacent to neither end
    u = np.unique(np.minimum(a, b) * n + np.maximum(a, b))
    pu, pv = u // n, u % n
    pk, cn = np.unique(i * n + j, return_counts=True)
    pos = np.searchsorted(pk, u)
    common = np.where((pos < len(pk)) & (pk[np.minimum(pos, max(len(pk) - 1, 0))] == u), cn[np.minimum(pos, max(len(pk) - 1, 0))], 0) \
        if len(pk) else np.zeros(len(u), np.int64)
    alone = n - deg[pu] - deg[pv] + common
    mutual = has(pu, pv) & has(pv, pu)
    counts["102"] = int(alone[mutual].sum())
    counts["012"] = int(alone[~mutual].sum())
    counts["003"] = total - sum(v for name, v in counts.items() if name != "003")
    return counts


def summary(pre, post, n: Optional[int] = None, positions=None, bins=None, max_dim: int = 4) -> Dict[str, object]:
    """Degree statistics, reciprocity, directed simplex counts up to `max_dim` and, with `positions` and `bins`, the
    distance-dependent connection probability, in one dict."""
    a, b, n = edges(pre, post, n)
    out: Dict[str, object] = dict(n=n, connections=len(a))
    out.update(degree_stats(a, b, n))
    out["reciprocity"] = reciprocity(a, b, n)
    out["simplices"] = directed_simplices(a, b, n, max_dim)
    if positions is not None and bins is not None:
        out["distance"] = distance_dependent_probability(positions, a, b, bins)
    return out
