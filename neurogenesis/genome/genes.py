"""Genes: (path, low, high) triples addressing values in a nested genome, and their [0, 1] coding for evolution.

A path is a sequence of keys into the genome's nested dicts, possibly followed by integer indices into an array value,
e.g. ("guidance", ("src", "dst"), "B", 0, 1) or ("migration", "region", "mean", 2). Genes whose first key is listed in
`integer_roots` are rounded to integers when set.
"""
from __future__ import annotations

import copy

import numpy as np

INTEGER_ROOTS = ("count", "excitability")


def _split(genome, path, create: bool = False):
    """(parent dict, key, array indices) for a path: dict keys first, then integer indices into an array value.
    If create is True, missing intermediate dict keys are created automatically.
    """
    node, parent, key = genome, None, None
    for k, p in enumerate(path):
        if isinstance(node, dict):
            if create and p not in node:
                if k < len(path) - 1 and not isinstance(path[k + 1], int):
                    node[p] = {}
            if p not in node and not create:
                raise KeyError(p)
            parent, key = node, p
            node = node.get(p) if create else node[p]
        else:
            return parent, key, tuple(path[k:])
    return parent, key, ()


def get_gene(genome, path) -> float:
    parent, key, idx = _split(genome, path)
    v = parent[key]
    return float(np.asarray(v, float)[idx]) if idx else float(v)


def set_gene(genome, path, v):
    """Set a gene in place (array values are replaced by modified copies). Auto-creates intermediate dicts."""
    parent, key, idx = _split(genome, path, create=True)
    if idx:
        arr = np.array(parent[key], float)
        arr[idx] = v
        parent[key] = arr
    else:
        parent[key] = v


def from_unit(genome, genes, u, integer_roots=INTEGER_ROOTS):
    """Copy of genome with gene k set to low_k + clip(u_k, 0, 1) (high_k - low_k)."""
    g = copy.deepcopy(genome)
    for (path, lo, hi), x in zip(genes, u):
        v = lo + float(np.clip(x, 0, 1)) * (hi - lo)
        if path[0] in integer_roots:
            v = int(round(v))
        set_gene(g, path, v)
    return g


def to_unit(genome, genes) -> np.ndarray:
    """Gene values of a genome scaled to [0, 1] (clipped)."""
    return np.clip(np.asarray([(get_gene(genome, path) - lo) / (hi - lo) for path, lo, hi in genes]), 0, 1)


def rebound(genes, new):
    """Gene list with some bounds replaced: new = {path: (low, high)}."""
    return [(p, *new.get(p, (lo, hi))) for p, lo, hi in genes]
