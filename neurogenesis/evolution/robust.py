"""Robustness to developmental randomness: a genome must work in every individual it grows, whatever the seed.

An evaluator returns, per genome, per-individual scores and gates (one individual per development seed):
dict(score=array, passed=bool array, cost=float, ...). Fitness used in evolution: worst + 0.25 x mean - cost.
"""
from __future__ import annotations

import numpy as np

HELD_OUT = tuple(range(1000, 1020))
VALIDATION = tuple(range(2000, 2020))
EXTRA = tuple(range(3000, 3100))


def robust_value(r, mean_weight=0.25):
    """Worst individual's score + mean_weight x mean score - cost."""
    s = np.asarray(r["score"], float)
    return float(s.min() + mean_weight * s.mean() - r.get("cost", 0.0))


def audit(evaluate_one, genome, seeds=HELD_OUT, keep=()):
    """Per-individual audit of one genome on seeds never used in evolution. evaluate_one(genome, seeds) -> result dict."""
    r = evaluate_one(genome, tuple(seeds))
    s = np.asarray(r["score"], float)
    out = dict(n=len(seeds), pass_fraction=float(np.mean(r["passed"])), all_pass=bool(np.all(r["passed"])), worst=float(s.min()),
               p10=float(np.percentile(s, 10)), median=float(np.median(s)), per_seed=s.round(4).tolist(),
               passed=np.asarray(r["passed"]).tolist(), seeds=list(seeds))
    for k in keep:
        if k in r:
            out[k] = np.asarray(r[k]).round(4).tolist()
    return out
