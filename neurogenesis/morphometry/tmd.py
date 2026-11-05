"""Topological morphology descriptor (TMD) of arbors: persistence barcodes, images and Wasserstein distance.

Algorithm: Kanari, L. et al. (2018) "A topological representation of neuronal morphologies", Neuroinformatics
(reference code: BlueBrain/TMD; population statistics: siegert-lab/morphOMICs). A filtration f(v) (path distance from
the soma, or Euclidean radial distance) is evaluated on every node. At each bifurcation the child subtree reaching the
largest tip value continues the bar of its parent; every other child subtree is a terminal branch giving one bar
(birth, death) = (f at the bifurcation, f at the farthest tip of that subtree). Each tree adds one bar from its root
(f = 0 at the soma) to its farthest tip. With a filtration growing outwards, death >= birth. Bars are invariant to
rotation and translation of the cell.

All functions are vectorised over the whole `ArborStore` (parent[i] < i ordering, pointer jumping, level sweeps over
tree depth); time and memory are O(nodes).
"""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

import numpy as np

from ..arbors import ArborStore, compartment_id

MAX_WASSERSTEIN_PAIRS = 1_000_000     # refuse n * m above this (assignment is O(k^3) in the worst case, k = n + m)
WASSERSTEIN_REFUSALS = 0              # number of refused calls (counted warning)
_BYTES_PER_NODE = 120                 # float64/int64 working arrays of `barcodes`
_OPS_PER_NODE = 40


@dataclass
class Barcode:
    """Bars of a population: `cell[k]` (Tissue index), `birth[k]`, `death[k]` (space units)."""
    cell: np.ndarray
    birth: np.ndarray
    death: np.ndarray

    def __len__(self) -> int:
        return len(self.birth)

    def of_cell(self, c: int) -> np.ndarray:
        """(n, 2) array of (birth, death) of one cell."""
        m = self.cell == c
        return np.stack([self.birth[m], self.death[m]], axis=1)


def barcodes_cost(n_nodes: int) -> Tuple[int, int]:
    """Declared (bytes, operations) of `barcodes` for an arbor store of `n_nodes` nodes."""
    return int(_BYTES_PER_NODE * n_nodes), int(_OPS_PER_NODE * n_nodes)


def barcodes(store: ArborStore, filtration: str = "path", compartments: Optional[Sequence[Union[str, int]]] = None,
             ) -> Barcode:
    """TMD barcodes of every tree in the store.

    `filtration` is "path" (distance along the tree from the root) or "radial" (Euclidean distance from the root).
    `compartments` restricts the nodes (e.g. ["dendrite"]); the soma / root nodes are always kept so that trees stay
    attached. Cost: `barcodes_cost(store.n_nodes)`.
    """
    if filtration not in ("path", "radial"):
        raise ValueError("filtration must be 'path' or 'radial'")
    if compartments is not None:
        ids = {compartment_id(c) for c in compartments}
        store = store.take((store.parent < 0) | np.isin(store.compartment, list(ids)))
    M = store.n_nodes
    if M == 0:
        return Barcode(np.zeros(0, np.int32), np.zeros(0), np.zeros(0))
    par = store.parent.astype(np.int64)
    jump, _ = _jump(par)
    root = jump
    if filtration == "path":
        f = store.path_length_to_root()
    else:
        f = np.linalg.norm(store.xyz.astype(np.float64) - store.xyz[root], axis=1)
    nchild = store.children_count()
    leaf = nchild == 0
    depth = _depth(par)
    m = np.where(leaf, f, -np.inf)                # farthest tip in each subtree, swept from the deepest level up
    order = np.argsort(depth, kind="stable")
    bounds = np.searchsorted(depth[order], np.arange(depth.max() + 2))
    for lev in range(int(depth.max()), 0, -1):
        nodes = order[bounds[lev]:bounds[lev + 1]]
        np.maximum.at(m, par[nodes], m[nodes])
    nonroot = np.flatnonzero(par >= 0)
    # children of a parent ordered by decreasing m (ties: lower index); the first one continues the parent's bar
    srt = nonroot[np.lexsort((nonroot, -m[nonroot], par[nonroot]))]
    first = np.ones(len(srt), bool)
    first[1:] = par[srt][1:] != par[srt][:-1]
    term = srt[~first]
    roots = np.flatnonzero(par < 0)
    cells = np.concatenate([store.cell[roots], store.cell[term]])
    birth = np.concatenate([f[roots], f[par[term]]])
    death = np.concatenate([m[roots], m[term]])
    o = np.lexsort((death, birth, cells))
    return Barcode(cells[o].astype(np.int32), birth[o], death[o])


def _jump(par: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(root, depth) of every node by pointer doubling, O(M log depth)."""
    M = len(par)
    jump = np.where(par >= 0, par, np.arange(M))
    cnt = (par >= 0).astype(np.int64)
    for _ in range(max(1, int(np.ceil(np.log2(M + 1))) + 1)):
        cnt = cnt + cnt[jump]
        jump = jump[jump]
    return jump, cnt


def _depth(par: np.ndarray) -> np.ndarray:
    return _jump(par)[1]

def persistence_images(bars: Barcode, n_cells: Optional[int] = None, grid: int = 20, bounds: Tuple[float, float] = (0.0, 1.0),
                       sigma: float = 1.0, cells: Optional[Sequence[int]] = None) -> np.ndarray:
    """Persistence images, one fixed-length float32 vector of `grid * grid` per cell (morphOMICs-style).

    Each cell's bars are binned in a `grid x grid` histogram over (birth, death) in `bounds` (bars outside are clipped
    to the edge bins), smoothed with a Gaussian of `sigma` bins, and flattened. `cells` selects the rows (default
    0..n_cells-1, `n_cells` default max cell + 1). Counts are kept (not normalised) so that bar number is encoded.
    """
    if cells is None:
        n = int(n_cells if n_cells is not None else (bars.cell.max() + 1 if len(bars) else 0))
        cells = np.arange(n)
    cells = np.asarray(cells)
    lo, hi = bounds
    scale = grid / max(hi - lo, 1e-12)
    bi = np.clip(((bars.birth - lo) * scale).astype(np.int64), 0, grid - 1)
    di = np.clip(((bars.death - lo) * scale).astype(np.int64), 0, grid - 1)
    row = np.full(int(max(cells.max(initial=-1), bars.cell.max(initial=-1))) + 1, -1, np.int64)
    row[cells] = np.arange(len(cells))
    r = row[bars.cell]
    keep = r >= 0
    img = np.zeros((len(cells), grid, grid), np.float64)
    np.add.at(img, (r[keep], bi[keep], di[keep]), 1.0)
    if sigma > 0:
        rad = int(np.ceil(3 * sigma))
        k = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sigma) ** 2)
        k /= k.sum()
        for ax in (1, 2):
            pad = [(0, 0)] * 3
            pad[ax] = (rad, rad)
            ip = np.pad(img, pad)
            img = sum(k[j] * np.take(ip, np.arange(j, j + grid), axis=ax) for j in range(len(k)))
    return img.reshape(len(cells), grid * grid).astype(np.float32)


def _assignment_cost(C: np.ndarray) -> float:
    """Minimum cost of a square assignment (shortest augmenting paths, potentials; O(k^3), numpy inner loops)."""
    k = len(C)
    u = np.zeros(k + 1)
    v = np.zeros(k + 1)
    match = np.zeros(k + 1, np.int64)             # match[j]: row (1-based) assigned to column j (1-based)
    for i in range(1, k + 1):
        match[0] = i
        j0 = 0
        minv = np.full(k + 1, np.inf)
        used = np.zeros(k + 1, bool)
        way = np.zeros(k + 1, np.int64)
        while True:
            used[j0] = True
            i0 = match[j0]
            cur = C[i0 - 1] - u[i0] - v[1:]
            free = ~used[1:]
            better = free & (cur < minv[1:])
            minv[1:][better] = cur[better]
            way[1:][better] = j0
            cand = np.where(free, minv[1:], np.inf)
            j1 = int(np.argmin(cand)) + 1
            delta = cand[j1 - 1]
            u[match[used]] += delta
            v[used] -= delta
            minv[~used] -= delta
            j0 = j1
            if match[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            match[j0] = match[j1]
            j0 = j1
    return float(sum(C[match[j] - 1, j - 1] for j in range(1, k + 1)))


def wasserstein_squared(a: np.ndarray, b: np.ndarray) -> float:
    """Squared 2-Wasserstein distance between two persistence diagrams (arrays of (birth, death) rows).

    Optimal matching of bars, each bar being allowed to match the diagonal (cost (death - birth)^2 / 2). Exact,
    O((n + m)^3) worst case, O(n * m) memory. If n * m exceeds `MAX_WASSERSTEIN_PAIRS` the call is refused: a warning
    is issued, `WASSERSTEIN_REFUSALS` is incremented and NaN is returned.
    """
    global WASSERSTEIN_REFUSALS
    a = np.asarray(a, np.float64).reshape(-1, 2)
    b = np.asarray(b, np.float64).reshape(-1, 2)
    n, m = len(a), len(b)
    if n * m > MAX_WASSERSTEIN_PAIRS:
        WASSERSTEIN_REFUSALS += 1
        warnings.warn(f"wasserstein_squared refused: {n} x {m} bars exceed {MAX_WASSERSTEIN_PAIRS} pairs", RuntimeWarning)
        return float("nan")
    if n + m == 0:
        return 0.0
    k = n + m
    C = np.zeros((k, k))
    C[:n, :m] = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
    C[:n, m:] = ((a[:, 1] - a[:, 0]) ** 2 / 2)[:, None]
    C[n:, :m] = ((b[:, 1] - b[:, 0]) ** 2 / 2)[None, :]
    return _assignment_cost(C)


def to_swc_bytes(store: ArborStore, cells: Optional[Sequence[int]] = None) -> bytes:
    """In-memory SWC of the given cells (default all), consumable by MorphoPy and TMD; `read_swc` reads it back.

    Node ids start at 1, one tree per root; positions and radii as stored.
    """
    if cells is not None:
        store = store.take(np.isin(store.cell, np.asarray(cells)))
    ids = np.arange(1, store.n_nodes + 1)
    par = np.where(store.parent >= 0, store.parent + 1, -1)
    buf = io.StringIO()
    for i in range(store.n_nodes):
        x, y, z = store.xyz[i]
        buf.write(f"{ids[i]} {int(store.compartment[i])} {x:.9g} {y:.9g} {z:.9g} {store.radius[i]:.9g} {par[i]}\n")
    return buf.getvalue().encode("ascii")
