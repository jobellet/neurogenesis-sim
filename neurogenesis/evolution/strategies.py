"""Evolution strategies (ES) on genomes coded as [0, 1] gene vectors (neurogenesis.genome): the alternative to the island
model (`neurogenesis.evolution.islands`) when the score must be kept on a smooth neighbourhood rather than on its best
individuals.

One centre theta moves each generation along a Monte Carlo estimate of the slope of the expected score under
N(theta, sigma^2 I) (Salimans et al. 2017, arXiv:1703.03864; Wierstra et al. 2008, IEEE CEC):
- `pop` variants theta + sigma x eps_i in antithetic pairs (eps, -eps), eps ~ N(0, I); frozen genes get eps = 0;
- every variant (and the centre itself, scored for the record) is evaluated on the same development seeds, so the noise common
  to a pair cancels in its difference;
- fitness shaping: centred ranks (default; robust to outliers) or z-scores;
- slope g = sum_i u_i eps_i / (pop x sigma), step by SGD or Adam, theta clipped to [0, 1].
Because it maximises the mean score of a cloud of width sigma, ES prefers wide regions of good genomes; on tasks that change,
this kept old tasks better than a genetic algorithm (Nisioti et al. 2026, arXiv:2610.01583).

evaluate(genomes, seeds) -> (fitness array, list of info dicts), as for `islands.evolve`. Cost per generation: pop + 1
evaluations (the centre included), O(pop x n_genes) memory for the directions. Deterministic for a given `island`.

functions: centred_ranks, zscores, shape, antithetic, gradient, Adam, evolve_es
"""
from __future__ import annotations

import time

import numpy as np

from ..genome.genes import INTEGER_ROOTS, from_unit, to_unit
from .islands import seeds_of


def centred_ranks(f) -> np.ndarray:
    """rank / (n - 1) - 0.5 in [-0.5, 0.5] (lowest -0.5); tied scores share their mean rank. Sums to 0."""
    f = np.asarray(f, float)
    order = np.argsort(f, kind="stable")
    r = np.empty(len(f))
    r[order] = np.arange(len(f), dtype=float)
    for v in np.unique(f):
        m = f == v
        if m.sum() > 1:
            r[m] = r[m].mean()
    return r / max(len(f) - 1, 1) - 0.5


def zscores(f) -> np.ndarray:
    """(f - mean) / sd; zeros when every score is equal."""
    f = np.asarray(f, float)
    sd = f.std()
    return (f - f.mean()) / sd if sd > 0 else np.zeros_like(f)


def shape(f, kind: str = "rank") -> np.ndarray:
    """Fitness shaping: kind = rank (centred ranks) or z (z-scores)."""
    if kind not in ("rank", "z"):
        raise ValueError(f"unknown fitness shaping {kind!r} (rank or z)")
    return centred_ranks(f) if kind == "rank" else zscores(f)


def antithetic(rng: np.random.Generator, pop: int, n: int, frozen=()) -> np.ndarray:
    """(pop, n) directions: pop / 2 standard normal draws then their negatives; columns in `frozen` are 0."""
    if pop < 2 or pop % 2:
        raise ValueError("ES needs an even population of at least 2 (antithetic pairs)")
    half = rng.standard_normal((pop // 2, n))
    if len(frozen):
        half[:, list(frozen)] = 0.0
    return np.concatenate([half, -half])


def gradient(u, eps, sigma: float) -> np.ndarray:
    """sum_i u_i eps_i / (len(u) x sigma): the slope of the expected (shaped) score under N(theta, sigma^2 I)."""
    u = np.asarray(u, float)
    return (u @ np.asarray(eps, float)) / (len(u) * sigma)


class Adam:
    """Adam (Kingma & Ba 2015, ICLR) as an ascent step: step(g) returns the update to ADD to theta."""

    def __init__(self, n: int, lr: float, b1: float = 0.9, b2: float = 0.999, eps: float = 1e-8):
        self.m, self.v, self.t = np.zeros(n), np.zeros(n), 0
        self.lr, self.b1, self.b2, self.eps = lr, b1, b2, eps

    def step(self, g) -> np.ndarray:
        g = np.asarray(g, float)
        self.t += 1
        self.m = self.b1 * self.m + (1 - self.b1) * g
        self.v = self.b2 * self.v + (1 - self.b2) * g * g
        mh, vh = self.m / (1 - self.b1 ** self.t), self.v / (1 - self.b2 ** self.t)
        return self.lr * mh / (np.sqrt(vh) + self.eps)


def _frozen_index(genes, frozen) -> list:
    """Indices of the genes to keep fixed: integer indices, or gene paths (tuples, or strings joined by '/')."""
    paths = ["/".join(map(str, p)) for p, _, _ in genes]
    out = []
    for f in frozen:
        if isinstance(f, (int, np.integer)):
            out.append(int(f))
        else:
            key = f if isinstance(f, str) else "/".join(map(str, f))
            if key not in paths:
                raise KeyError(f"frozen gene {key!r} is not in the gene list")
            out.append(paths.index(key))
    return sorted(set(out))


def evolve_es(base, genes, evaluate, island=0, pop=64, gens=150, seeds_per_gen=6, sigma=0.03, lr=0.01, optimizer="sgd",
              shaping="rank", u0=None, frozen=(), integer_roots=INTEGER_ROOTS, log=None):
    """Evolve one centre by ES (see the module docstring).

    base, genes: the genome and its gene list (neurogenesis.genome); u0: the first centre as a [0, 1] vector (default: the base
    genome's own coding). pop: number of variants (even). sigma: width of the perturbations in the [0, 1] coding. lr: step
    size (SGD) or learning rate (Adam); optimizer: sgd or adam. frozen: genes that do not move (indices or paths).
    Each generation evaluates the pop variants and the centre on seeds_of(island, generation, seeds_per_gen).
    Returns (final centre as a [0, 1] vector, history list); log(dict) is called after every generation with: generation,
    centre (its fitness), best and median variant fitness, the spread of the variants' fitness, the norms of the slope and of
    the step, the distance from the first centre, the centre's info dict and wall time.
    """
    if optimizer not in ("sgd", "adam"):
        raise ValueError(f"unknown optimizer {optimizer!r} (sgd or adam)")
    rng = np.random.default_rng(island)
    theta = np.clip(np.asarray(to_unit(base, genes) if u0 is None else u0, float).copy(), 0.0, 1.0)
    theta0, n = theta.copy(), len(genes)
    fz = _frozen_index(genes, frozen)
    opt = Adam(n, lr) if optimizer == "adam" else None
    hist, t0 = [], time.time()
    for gen in range(gens):
        eps = antithetic(rng, pop, n, fz)
        U = np.clip(theta + sigma * eps, 0.0, 1.0)
        fit, info = evaluate([from_unit(base, genes, u, integer_roots) for u in np.concatenate([U, theta[None]])],
                             seeds_of(island, gen, seeds_per_gen))
        fit = np.asarray(fit, float)
        fv, fc = fit[:pop], float(fit[pop])
        g = gradient(shape(fv, shaping), eps, sigma)
        d = opt.step(g) if opt is not None else lr * g
        d[fz] = 0.0
        new = np.clip(theta + d, 0.0, 1.0)
        hist.append(dict(generation=gen, centre=fc, best=float(fv.max()), median=float(np.median(fv)), spread=float(fv.std()),
                         grad_norm=float(np.linalg.norm(g)), step_norm=float(np.linalg.norm(new - theta)),
                         dist_from_start=float(np.linalg.norm(new - theta0)), centre_info=info[pop],
                         wall_s=round(time.time() - t0, 1)))
        theta = new
        if log:
            log(hist[-1])
    return theta, hist
