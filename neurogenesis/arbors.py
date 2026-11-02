"""Arbor morphologies as struct of arrays (N1): `ArborStore`, SWC read / write, path lengths, downsampling.

A store holds the trees of many cells. Node i has a position `xyz[i]` (space units), a `radius[i]`, a `parent[i]` (-1 for
a root) and a `compartment[i]` label, and belongs to cell `cell[i]` (index into the Tissue). Invariant: a parent comes
before its children (parent[i] < i), so path lengths and subtree operations are vectorised (pointer jumping,
O(M log depth)). Compartment labels follow the SWC convention where it is generic: 0 undefined, 1 soma, 2 axon,
3 dendrite, 5 neurite (a process that is both, as in unipolar cells); any other integer is a user label, named in
`labels`. Nothing enforces apical / basal dendrites.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Sequence, Union

import numpy as np

from .spatial import _concat_ranges

UNDEFINED, SOMA, AXON, DENDRITE, NEURITE = 0, 1, 2, 3, 5
COMPARTMENTS = {"undefined": UNDEFINED, "soma": SOMA, "axon": AXON, "dendrite": DENDRITE, "neurite": NEURITE}
NODE_BYTES = 12 + 4 + 4 + 1 + 4      # xyz float32, radius float32, parent int32, compartment int8, cell int32


def compartment_id(c: Union[str, int]) -> int:
    return int(c) if not isinstance(c, str) else COMPARTMENTS[c]


@dataclass
class ArborStore:
    xyz: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), np.float32))
    radius: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    parent: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int32))
    compartment: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int8))
    cell: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int32))
    labels: Dict[int, str] = field(default_factory=dict)

    def __post_init__(self):
        self.xyz = np.asarray(self.xyz, np.float32).reshape(-1, 3)
        self.radius = np.asarray(self.radius, np.float32).reshape(-1)
        self.parent = np.asarray(self.parent, np.int32).reshape(-1)
        self.compartment = np.asarray(self.compartment, np.int8).reshape(-1)
        self.cell = np.asarray(self.cell, np.int32).reshape(-1)
        M = len(self.xyz)
        if not (len(self.radius) == len(self.parent) == len(self.compartment) == len(self.cell) == M):
            raise ValueError("ArborStore arrays must have one entry per node")
        if M and np.any(self.parent >= np.arange(M)):
            raise ValueError("ArborStore needs parent[i] < i (use ArborStore.ordered)")

    @property
    def n_nodes(self) -> int:
        return len(self.xyz)

    def nbytes(self) -> int:
        return self.n_nodes * NODE_BYTES

    @classmethod
    def ordered(cls, xyz, radius, parent, compartment, cell, labels=None) -> "ArborStore":
        """A store from nodes in any order (parents may come after children): reordered breadth first."""
        parent = np.asarray(parent, np.int64)
        M = len(parent)
        order = np.zeros(0, np.int64)
        level = np.flatnonzero(parent < 0)
        children = np.argsort(parent, kind="stable")
        sorted_par = parent[children]
        while len(level):
            order = np.concatenate([order, level])
            lo = np.searchsorted(sorted_par, level, side="left")
            hi = np.searchsorted(sorted_par, level, side="right")
            level = children[_concat_ranges(lo, hi - lo)]
        if len(order) != M:
            raise ValueError("arbor parents contain a cycle or point outside the store")
        new = np.empty(M, np.int64)
        new[order] = np.arange(M)
        p = parent[order]
        p = np.where(p >= 0, new[np.maximum(p, 0)], -1)
        return cls(np.asarray(xyz)[order], np.asarray(radius)[order], p, np.asarray(compartment)[order],
                   np.asarray(cell)[order], dict(labels or {}))

    def segment_lengths(self) -> np.ndarray:
        """Length of the segment from each node to its parent (0 for roots)."""
        has = self.parent >= 0
        out = np.zeros(self.n_nodes, np.float64)
        out[has] = np.linalg.norm(self.xyz[has].astype(np.float64) - self.xyz[self.parent[has]], axis=1)
        return out

    def path_length_to_root(self) -> np.ndarray:
        """Distance along the tree from each node to its root (pointer jumping, O(M log depth))."""
        d = self.segment_lengths()
        p = self.parent.astype(np.int64).copy()
        while np.any(p >= 0):
            has = p >= 0
            d = d + np.where(has, d[np.maximum(p, 0)], 0.0)
            p = np.where(has, p[np.maximum(p, 0)], -1)
        return d

    def children_count(self) -> np.ndarray:
        return np.bincount(self.parent[self.parent >= 0], minlength=self.n_nodes)

    def take(self, keep: np.ndarray) -> "ArborStore":
        """Store with only the kept nodes (boolean mask); a dropped node's children attach to its nearest kept
        ancestor (subtrees of dropped roots become new roots)."""
        keep = np.asarray(keep, bool)
        anc = self.parent.astype(np.int64).copy()
        while True:                                   # move every parent pointer up to a kept ancestor
            bad = (anc >= 0) & ~keep[np.maximum(anc, 0)]
            if not bad.any():
                break
            anc[bad] = self.parent[anc[bad]]
        new = np.full(self.n_nodes, -1, np.int64)
        new[keep] = np.arange(int(keep.sum()))
        p = np.where(anc >= 0, new[np.maximum(anc, 0)], -1)[keep]
        return ArborStore(self.xyz[keep], self.radius[keep], p, self.compartment[keep], self.cell[keep], dict(self.labels))

    def select_cells(self, cells: Sequence[int], renumber: Optional[np.ndarray] = None) -> "ArborStore":
        """Nodes of the given cells; `renumber` (old cell index -> new, -1 = drop) re-indexes cells, e.g. after
        Tissue.compact."""
        keep = np.isin(self.cell, np.asarray(cells))
        out = self.take(keep)
        if renumber is not None:
            out.cell = np.asarray(renumber, np.int32)[out.cell]
        return out

    @classmethod
    def concatenate(cls, stores: Sequence["ArborStore"]) -> "ArborStore":
        stores = [s for s in stores if s is not None]
        if not stores:
            return cls()
        offsets = np.cumsum([0] + [s.n_nodes for s in stores[:-1]])
        labels = {}
        for s in stores:
            labels.update(s.labels)
        return cls(np.concatenate([s.xyz for s in stores]), np.concatenate([s.radius for s in stores]),
                   np.concatenate([np.where(s.parent >= 0, s.parent + o, -1) for s, o in zip(stores, offsets)]),
                   np.concatenate([s.compartment for s in stores]), np.concatenate([s.cell for s in stores]), labels)

    def downsample(self, step: int) -> "ArborStore":
        """Keeps roots, branch points, terminals and every `step`-th node along unbranched stretches (counted from the
        root by depth), so the topology and the total path length are kept up to the removed bends."""
        if step <= 1 or self.n_nodes == 0:
            return self
        nc = self.children_count()
        topo = (self.parent < 0) | (nc != 1) | (self.compartment != np.where(self.parent >= 0, self.compartment[np.maximum(self.parent, 0)], self.compartment))
        return self.take(topo | (self.depth() % step == 0))

    def depth(self) -> np.ndarray:
        """Number of edges from each node to its root (pointer jumping)."""
        d = (self.parent >= 0).astype(np.int64)
        p = self.parent.astype(np.int64).copy()
        while np.any(p >= 0):
            has = p >= 0
            d = d + np.where(has, d[np.maximum(p, 0)], 0)
            p = np.where(has, p[np.maximum(p, 0)], -1)
        return d

    def to_budget(self, max_nodes_per_cell: int) -> "ArborStore":
        """Downsamples with the smallest step that brings every cell to at most `max_nodes_per_cell` nodes (or to its
        roots, branch points and terminals if that is still more)."""
        step, out = 1, self
        while out.n_nodes and np.bincount(out.cell).max() > max_nodes_per_cell and step < 1 << 20:
            step *= 2
            nxt = self.downsample(step)
            if nxt.n_nodes == out.n_nodes and step > 2:
                break
            out = nxt
        return out


def read_swc(path: Union[str, Path], cell: int = 0, scale: float = 1.0) -> ArborStore:
    """Reads an SWC file (columns: id, type, x, y, z, radius, parent id; '#' comments) as the arbor of one cell.
    Coordinates and radii are multiplied by `scale` (e.g. 1e-3 to turn nanometres into micrometres)."""
    a = np.loadtxt(path, comments="#", ndmin=2)
    if a.size == 0:
        return ArborStore()
    ids = a[:, 0].astype(np.int64)
    par_id = a[:, 6].astype(np.int64)
    order = np.argsort(ids)
    pos = np.searchsorted(ids[order], par_id)
    pos = np.clip(pos, 0, len(ids) - 1)
    found = (par_id >= 0) & (ids[order][pos] == par_id)
    parent = np.where(found, order[pos], -1)
    return ArborStore.ordered(a[:, 2:5] * scale, a[:, 5] * scale, parent, a[:, 1].astype(np.int8),
                              np.full(len(a), cell, np.int32))


def write_swc(store: ArborStore, path: Union[str, Path], cell: Optional[int] = None) -> None:
    """Writes the arbor of one cell (or of every cell, as a forest) in SWC; node ids start at 1."""
    s = store if cell is None else store.select_cells([cell])
    ids = np.arange(1, s.n_nodes + 1)
    par = np.where(s.parent >= 0, s.parent + 1, -1)
    a = np.column_stack([ids, s.compartment.astype(int), s.xyz, s.radius, par])
    header = "neurogenesis ArborStore export\nid type x y z radius parent"
    np.savetxt(path, a, fmt=["%d", "%d", "%.6g", "%.6g", "%.6g", "%.6g", "%d"], header=header)
