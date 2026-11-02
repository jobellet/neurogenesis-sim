"""Semi-supervised optimisation (E3): evolve `Gene` params with `Fit` params refitted in an inner loop or fixed, and
a multi-objective (Pareto) island.

    evaluate = inner_fit_evaluator(project, targets, outer_evaluate, fit_seeds=(0,), iterations=5)
    P, hist = evolve(base, genes, evaluate, ...)            # neurogenesis.evolution.islands, unchanged

`outer_evaluate(genomes, seeds)` is any evaluator of `islands.evolve`; the wrapper first fits each genome's Fit params
to the data targets (`neurogenesis.fitting.fit`), then scores the fitted genome. Its info dicts carry the fitted
values, so the chosen genome can be rebuilt with `fitting.with_fit`.

`evolve_pareto` keeps a population on the Pareto front of several objectives (all maximised), with non-dominated
sorting and crowding distance (Deb et al. 2002, IEEE Trans Evol Comput).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..fitting import fit, with_fit
from ..genome.genes import INTEGER_ROOTS, from_unit, to_unit
from .islands import seeds_of


def inner_fit_evaluator(project: Dict[str, Any], targets: Sequence[Dict[str, Any]], outer_evaluate: Callable,
                        fit_seeds: Sequence[int] = (0,), iterations: int = 5, popsize: Optional[int] = None,
                        refit: bool = True) -> Callable:
    """Evaluator for `islands.evolve` that refits each genome's Fit params (refit=True) or keeps them as they are in
    the genome (refit=False, "fixed"), then calls outer_evaluate on the resulting genomes. The inner CMA-ES is seeded
    by the genome's position in the batch, so evaluation is deterministic."""
    def evaluate(genomes: List[Dict[str, Any]], seeds: Sequence[int]):
        fitted, losses = [], []
        for k, g in enumerate(genomes):
            if refit:
                r = fit(project, targets, seeds=fit_seeds, genome=g, iterations=iterations, popsize=popsize, seed=k)
                fitted.append(r.genome)
                losses.append(r.loss)
            else:
                fitted.append(g)
                losses.append(float("nan"))
        fitness, info = outer_evaluate(fitted, seeds)
        info = [dict(i, fit=dict(g.get("__fit__", {})), fit_loss=l) for i, g, l in zip(info, fitted, losses)]
        return fitness, info
    return evaluate


def non_dominated_sort(F: np.ndarray) -> np.ndarray:
    """Front rank of each row of F (objectives maximised): 0 for the Pareto front, 1 for the next, ... O(P^2 k)."""
    F = np.asarray(F, float)
    P = len(F)
    geq = np.all(F[:, None, :] >= F[None, :, :], axis=2)
    gt = np.any(F[:, None, :] > F[None, :, :], axis=2)
    dominates = geq & gt                                     # dominates[i, j]: i dominates j
    n_dom = dominates.sum(0)
    rank = np.full(P, -1)
    r, current = 0, np.flatnonzero(n_dom == 0)
    while len(current):
        rank[current] = r
        n_dom = n_dom - dominates[current].sum(0)
        n_dom[rank >= 0] = -1
        current = np.flatnonzero(n_dom == 0)
        r += 1
    return rank


def crowding_distance(F: np.ndarray) -> np.ndarray:
    """Crowding distance of each row within its set (boundary points get inf)."""
    F = np.asarray(F, float)
    P, k = F.shape
    d = np.zeros(P)
    if P <= 2:
        return np.full(P, np.inf)
    for j in range(k):
        o = np.argsort(F[:, j], kind="stable")
        span = F[o[-1], j] - F[o[0], j]
        d[o[0]] = d[o[-1]] = np.inf
        if span > 0:
            d[o[1:-1]] += (F[o[2:], j] - F[o[:-2], j]) / span
    return d


def _crowding_by_front(F: np.ndarray, rank: np.ndarray) -> np.ndarray:
    d = np.zeros(len(F))
    for r in np.unique(rank):
        idx = np.flatnonzero(rank == r)
        d[idx] = crowding_distance(F[idx])
    return d


def pareto_front(F: np.ndarray) -> np.ndarray:
    """Indices of the non-dominated rows of F (objectives maximised)."""
    return np.flatnonzero(non_dominated_sort(F) == 0)


def evolve_pareto(base: Dict[str, Any], genes, evaluate: Callable, island: int = 0, pop: int = 32, gens: int = 30,
                  seeds_per_gen: int = 3, sigma: float = 0.1, integer_roots=INTEGER_ROOTS,
                  log: Optional[Callable[[dict], None]] = None) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    """Multi-objective island: evaluate(genomes, seeds) -> (F (pop, k) objectives to maximise, info list).

    Each generation, mutated children of tournament-selected parents join the population, and the best `pop` of the
    union by (front rank, crowding distance) survive. Returns (population as [0, 1] vectors, their objectives, history).
    Deterministic for a given island number.
    """
    rng = np.random.default_rng(island)
    u0 = to_unit(base, genes)
    P = np.clip(u0[None] + sigma * rng.standard_normal((pop, len(genes))), 0, 1)
    P[0] = u0
    hist = []
    F = None
    for gen in range(gens):
        seeds = seeds_of(island, gen, seeds_per_gen)
        if F is None:
            F, _ = evaluate([from_unit(base, genes, u, integer_roots) for u in P], seeds)
            F = np.asarray(F, float)
        rank = non_dominated_sort(F)
        crowd = _crowding_by_front(F, rank)
        a, b = rng.integers(0, pop, pop), rng.integers(0, pop, pop)
        better = (rank[a] < rank[b]) | ((rank[a] == rank[b]) & (crowd[a] >= crowd[b]))
        parents = np.where(better, a, b)
        children = np.clip(P[parents] + sigma * rng.standard_normal((pop, len(genes))), 0, 1)
        Fc, _ = evaluate([from_unit(base, genes, u, integer_roots) for u in children], seeds)
        # parents are re-scored on this generation's seeds so the comparison is fair
        Fp, _ = evaluate([from_unit(base, genes, u, integer_roots) for u in P], seeds)
        U, FU = np.concatenate([P, children]), np.concatenate([np.asarray(Fp, float), np.asarray(Fc, float)])
        rank = non_dominated_sort(FU)
        crowd = _crowding_by_front(FU, rank)
        order = np.lexsort((-crowd, rank))[:pop]
        P, F = U[order], FU[order]
        front = pareto_front(F)
        hist.append(dict(generation=gen, front_size=int(len(front)), front=F[front].round(4).tolist()))
        if log:
            log(hist[-1])
    return P, F, hist
