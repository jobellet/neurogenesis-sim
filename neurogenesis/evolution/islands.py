"""Island evolution of genomes coded as [0, 1] gene vectors (neurogenesis.genome).

One island: a population starts around a founding genome (u0 + sigma N(0, 1), the founder itself kept), and each
generation is evaluated on fresh development seeds; the best `elite` individuals are kept, the rest are mutated
children of the best `parents`. Run several islands (different `island` numbers) in parallel and choose among their
results on validation seeds, then audit on held-out seeds (neurogenesis.evolution.robust).
"""
from __future__ import annotations

import time

import numpy as np

from ..genome.genes import INTEGER_ROOTS, from_unit, to_unit


def seeds_of(island, generation, n):
    """Development seeds of one generation: distinct across islands and generations, never equal to small audit seeds."""
    return tuple(100000 * (island + 1) + 10 * generation + k for k in range(n))


def evolve(base, genes, evaluate, island=0, pop=64, gens=150, seeds_per_gen=6, elite=2, parents=16, sigma=0.1,
           integer_roots=INTEGER_ROOTS, log=None):
    """Evolve one island.

    evaluate(genomes, seeds) -> (fitness array, list of per-genome info dicts). Returns (final population as [0, 1]
    vectors, history list). log(dict) is called after every generation.
    """
    rng = np.random.default_rng(island)
    u0 = to_unit(base, genes)
    P = np.clip(u0[None] + sigma * rng.standard_normal((pop, len(genes))), 0, 1)
    P[0] = u0
    hist, t0 = [], time.time()
    for gen in range(gens):
        fit, info = evaluate([from_unit(base, genes, u, integer_roots) for u in P], seeds_of(island, gen, seeds_per_gen))
        fit = np.asarray(fit, float)
        o = np.argsort(-fit)
        hist.append(dict(generation=gen, best=float(fit[o[0]]), median=float(np.median(fit)), best_info=info[o[0]],
                         wall_s=round(time.time() - t0, 1)))
        if log:
            log(hist[-1])
        keep = o[:min(elite, pop)]
        n_par = min(parents, pop)
        pick = o[:n_par][rng.integers(0, n_par, pop - len(keep))]
        P = np.concatenate([P[keep], np.clip(P[pick] + sigma * rng.standard_normal((len(pick), len(genes))), 0, 1)])
    return P, hist


def choose(base, genes, P, evaluate, seeds, integer_roots=INTEGER_ROOTS, top=None, fitness_of=None):
    """Best genome of a final population on given (validation) seeds. Returns (genome, its evaluation info)."""
    gs = [from_unit(base, genes, u, integer_roots) for u in (P if top is None else P[:top])]
    fit, info = evaluate(gs, seeds)
    b = int(np.argmax(fit))
    return gs[b], info[b]
