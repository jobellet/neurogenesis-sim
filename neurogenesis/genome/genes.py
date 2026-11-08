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
    A missing key raises KeyError, unless create is True: then missing dict keys are created (intermediate keys as
    empty dicts); array values are never created. The genome is left unchanged when a KeyError is raised."""
    node, k = genome, 0
    while k < len(path) and isinstance(node, dict) and path[k] in node:      # existing part of the path
        node, k = node[path[k]], k + 1
    if k < len(path) and isinstance(node, dict):                           # first missing key path[k]
        if not create:
            raise KeyError(f"gene path {tuple(path)!r}: no key {path[k]!r}")
        if any(isinstance(p, (int, np.integer)) for p in path[k + 1:]):
            raise KeyError(f"gene path {tuple(path)!r}: cannot create the array value {path[k]!r}")
        for p in path[k:-1]:
            node[p] = {}
            node = node[p]
        return node, path[-1], ()
    parent, key = genome, None
    node = genome
    for j, p in enumerate(path):
        if not isinstance(node, dict):
            return parent, key, tuple(path[j:])
        parent, key, node = node, p, node[p]
    return parent, key, ()


def get_gene(genome, path) -> float:
    parent, key, idx = _split(genome, path)
    v = parent[key]
    return float(np.asarray(v, float)[idx]) if idx else float(v)


def set_gene(genome, path, v, create: bool = False):
    """Set a gene in place (array values are replaced by modified copies). A path that does not exist raises KeyError,
    so that a misspelled gene cannot become a silent dead gene; create=True adds missing dict keys instead."""
    parent, key, idx = _split(genome, path, create=create)
    if idx:
        arr = np.array(parent[key], float)
        arr[idx] = v
        parent[key] = arr
    else:
        parent[key] = v


def from_unit(genome, genes, u, integer_roots=INTEGER_ROOTS, create: bool = False):
    """Copy of genome with gene k set to low_k + clip(u_k, 0, 1) (high_k - low_k). Every gene path must exist in the
    genome (KeyError otherwise) unless create=True."""
    g = copy.deepcopy(genome)
    for (path, lo, hi), x in zip(genes, u):
        v = lo + float(np.clip(x, 0, 1)) * (hi - lo)
        if path[0] in integer_roots:
            v = int(round(v))
        set_gene(g, path, v, create=create)
    return g


def to_unit(genome, genes) -> np.ndarray:
    """Gene values of a genome scaled to [0, 1] (clipped)."""
    return np.clip(np.asarray([(get_gene(genome, path) - lo) / (hi - lo) for path, lo, hi in genes]), 0, 1)


def rebound(genes, new):
    """Gene list with some bounds replaced: new = {path: (low, high)}."""
    return [(p, *new.get(p, (lo, hi))) for p, lo, hi in genes]
