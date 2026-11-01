"""Genomes to and from JSON. Tuple keys (projections) become "src->dst"; arrays become lists and back."""
from __future__ import annotations

import numpy as np


def to_json(g):
    """JSON-ready copy of a genome."""
    if isinstance(g, dict):
        return {("->".join(k) if isinstance(k, tuple) else k): to_json(v) for k, v in g.items()}
    if isinstance(g, np.ndarray):
        return g.tolist()
    if isinstance(g, (np.floating, np.integer)):
        return g.item()
    if isinstance(g, (list, tuple)):
        return [to_json(v) for v in g]
    return g


def _numeric_list(x):
    if not isinstance(x, list) or not x:
        return False
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) or _numeric_list(v) for v in x)


def from_json(d):
    """Genome from its JSON form: "a->b" keys become tuples, numeric lists become arrays."""
    if isinstance(d, dict):
        return {(tuple(k.split("->")) if isinstance(k, str) and "->" in k else k): from_json(v) for k, v in d.items()}
    if _numeric_list(d):
        return np.asarray(d)
    if isinstance(d, list):
        return [from_json(v) for v in d]
    return d
