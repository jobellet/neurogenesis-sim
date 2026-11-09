"""Quality-diversity search on genomes coded as [0, 1] gene vectors: MAP-Elites, CMA-ME and CMA-MAE (E5).

Instead of one best genome, the search fills an *archive*: a grid over behaviour descriptors (for example the total
wiring length, an excitation / inhibition ratio, the largest directed simplex), each cell keeping the best genome found
with descriptors in it. This keeps stepping stones that a single objective would drop, and returns a map of the
trade-offs between the descriptors.
- **MAP-Elites** (Mouret & Clune 2015, arXiv:1504.04909): `emitter="gaussian"`; each child is a random elite plus
  Gaussian noise of width `sigma` in the [0, 1] coding.
- **CMA-ME** (Fontaine et al. 2020, GECCO, arXiv:1912.02400): `emitter="cma"`; each emitter is a CMA-ES (Hansen &
  Ostermeier 2001, Evol Comput) whose candidates are ranked by their improvement of the archive, and which restarts
  from a random elite when none of its candidates enters the archive.
- **CMA-MAE** (Fontaine & Nikolaidis 2023, GECCO, arXiv:2205.10752): `emitter="cma"` with `learning_rate` < 1. Each
  cell has an acceptance threshold that moves towards the fitness of every accepted candidate by that rate (the
  annealing), starting at `threshold_min`; a candidate enters when its fitness beats the threshold, and its
  improvement is fitness minus threshold. With learning_rate = 1 the threshold is the elite's fitness (CMA-ME).
The archive always keeps, per cell, the best genome seen.

evaluate(genomes, seeds) -> (fitness array, list of info dicts), as for `islands.evolve`; descriptors(info) -> d
numbers (or the name of an info key holding them, or a list of info keys). Each generation evaluates
`emitters x batch` genomes on seeds_of(island, generation, seeds_per_gen). Memory: the archive (cells x n_genes) and,
for CMA emitters, one n_genes x n_genes covariance each (O(n_genes^3) eigen-decomposition per generation).
Deterministic for a given `island`.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import numpy as np

from ..genome.genes import INTEGER_ROOTS, from_unit, to_unit
from .islands import seeds_of


class Archive:
    """Grid archive over d descriptors: `cells[k]` equal bins on [lows[k], highs[k]] (values outside are clipped to the
    edge bins). Per cell: the elite (best genome seen, its fitness, descriptors, info) and the acceptance threshold
    (CMA-MAE; equal to the elite's fitness when learning_rate = 1)."""

    def __init__(self, n_genes: int, lows: Sequence[float], highs: Sequence[float], cells: Sequence[int],
                 learning_rate: float = 1.0, threshold_min: float = -np.inf):
        self.lows, self.highs = np.asarray(lows, float), np.asarray(highs, float)
        self.cells = np.asarray(cells, np.int64)
        if not (len(self.lows) == len(self.highs) == len(self.cells)) or np.any(self.highs <= self.lows) or np.any(self.cells < 1):
            raise ValueError("Archive: lows, highs and cells need one entry per descriptor, highs > lows, cells >= 1")
        if not 0.0 < learning_rate <= 1.0:
            raise ValueError("Archive: learning_rate must be in (0, 1]")
        if learning_rate < 1.0 and not np.isfinite(threshold_min):
            raise ValueError("Archive: CMA-MAE (learning_rate < 1) needs a finite threshold_min")
        self.learning_rate, self.threshold_min = float(learning_rate), float(threshold_min)
        size = int(np.prod(self.cells))
        self.genes = np.full((size, n_genes), np.nan)
        self.fitness = np.full(size, -np.inf)
        self.threshold = np.full(size, self.threshold_min)
        self.descriptors = np.full((size, len(self.cells)), np.nan)
        self.info: List[Optional[Dict[str, Any]]] = [None] * size

    def index(self, bd) -> int:
        """Flat index of the cell holding descriptors bd."""
        bd = np.asarray(bd, float)
        k = np.floor((bd - self.lows) / (self.highs - self.lows) * self.cells).astype(np.int64)
        k = np.clip(k, 0, self.cells - 1)
        return int(np.ravel_multi_index(tuple(k), tuple(self.cells)))

    def add(self, u, fitness: float, bd, info=None) -> tuple:
        """Offers a genome: returns (status, improvement) with status 2 = new cell, 1 = beat the threshold, 0 = not
        accepted; improvement = fitness - threshold before the offer (fitness - threshold_min for a new cell with an
        infinite threshold_min: the fitness itself)."""
        i = self.index(bd)
        f = float(fitness)
        empty = not np.isfinite(self.fitness[i])
        thr = self.threshold[i]
        imp = f - (thr if np.isfinite(thr) else 0.0)
        accepted = f > thr
        if f > self.fitness[i] and (accepted or not empty):     # an empty cell takes only accepted genomes
            self.genes[i], self.fitness[i], self.descriptors[i], self.info[i] = np.asarray(u, float), f, bd, info
        if not accepted:
            return 0, imp
        self.threshold[i] = f if not np.isfinite(thr) else (1 - self.learning_rate) * thr + self.learning_rate * f
        return (2 if empty else 1), imp

    @property
    def filled(self) -> np.ndarray:
        return np.flatnonzero(np.isfinite(self.fitness))

    def coverage(self) -> float:
        """Fraction of cells holding an elite."""
        return len(self.filled) / len(self.fitness)

    def qd_score(self, offset: float = 0.0) -> float:
        """Sum over filled cells of (elite fitness - offset)."""
        return float(np.sum(self.fitness[self.filled] - offset))

    def best(self) -> int:
        """Flat index of the best elite (-1 if empty)."""
        return int(np.argmax(self.fitness)) if len(self.filled) else -1

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        """n elites drawn uniformly among filled cells (rows of genes)."""
        f = self.filled
        return self.genes[f[rng.integers(0, len(f), n)]]


class CMAEmitter:
    """A CMA-ES (Hansen & Ostermeier 2001; Hansen 2016, arXiv:1604.00772) in the [0, 1] coding with ask / tell; tell
    takes the candidates ranked best first (by improvement for CMA-ME / CMA-MAE)."""

    def __init__(self, x0, sigma: float, batch: int, rng: np.random.Generator):
        self.n = len(x0)
        self.batch = int(batch)
        self.rng = rng
        self.sigma0 = float(sigma)
        n, lam = self.n, self.batch
        self.mu = lam // 2
        w = np.log(self.mu + 0.5) - np.log(np.arange(1, self.mu + 1))
        self.w = w / w.sum()
        self.mueff = 1.0 / np.sum(self.w ** 2)
        self.cc = (4 + self.mueff / n) / (n + 4 + 2 * self.mueff / n)
        self.cs = (self.mueff + 2) / (n + self.mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((n + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0.0, np.sqrt((self.mueff - 1) / (n + 1)) - 1) + self.cs
        self.chin = np.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
        self.reset(x0)

    def reset(self, x0) -> None:
        self.mean = np.asarray(x0, float).copy()
        self.sigma = self.sigma0
        self.C = np.eye(self.n)
        self.pc, self.ps = np.zeros(self.n), np.zeros(self.n)
        self.B, self.D = np.eye(self.n), np.ones(self.n)
        self.restarts = getattr(self, "restarts", -1) + 1

    def ask(self) -> np.ndarray:
        z = self.rng.standard_normal((self.batch, self.n))
        self._y = (z * self.D) @ self.B.T
        return np.clip(self.mean + self.sigma * self._y, 0.0, 1.0)

    def tell(self, ranking: np.ndarray) -> None:
        y = self._y[np.asarray(ranking)[: self.mu]]
        yw = self.w @ y
        self.mean = np.clip(self.mean + self.sigma * yw, 0.0, 1.0)
        invsq = (self.B / self.D) @ self.B.T
        self.ps = (1 - self.cs) * self.ps + np.sqrt(self.cs * (2 - self.cs) * self.mueff) * invsq @ yw
        hs = float(np.linalg.norm(self.ps) / self.chin < 1.4 + 2 / (self.n + 1))
        self.pc = (1 - self.cc) * self.pc + hs * np.sqrt(self.cc * (2 - self.cc) * self.mueff) * yw
        self.C = ((1 - self.c1 - self.cmu) * self.C + self.c1 * np.outer(self.pc, self.pc)
                  + self.cmu * (y.T * self.w) @ y)
        self.sigma *= np.exp((self.cs / self.damps) * (np.linalg.norm(self.ps) / self.chin - 1))
        self.sigma = float(np.clip(self.sigma, 1e-8, 1.0))
        self.C = (self.C + self.C.T) / 2
        d2, self.B = np.linalg.eigh(self.C)
        self.D = np.sqrt(np.maximum(d2, 1e-20))


def _descriptor_fn(descriptors: Union[str, Sequence[str], Callable]) -> Callable:
    if callable(descriptors):
        return lambda info: np.asarray(descriptors(info), float).ravel()
    if isinstance(descriptors, str):
        return lambda info: np.asarray(info[descriptors], float).ravel()
    keys = list(descriptors)
    return lambda info: np.asarray([info[k] for k in keys], float)


def evolve_qd(base, genes, evaluate, descriptors, lows, highs, cells, island: int = 0, emitter: str = "cma",
              emitters: int = 4, batch: int = 16, gens: int = 100, seeds_per_gen: int = 6, sigma: float = 0.1,
              learning_rate: float = 1.0, threshold_min: float = -np.inf, u0=None,
              integer_roots=INTEGER_ROOTS, log=None):
    """Fill an `Archive` by MAP-Elites (`emitter="gaussian"`) or CMA-ME / CMA-MAE (`emitter="cma"`; see the module
    docstring).

    base, genes: the genome and its gene list; u0: the starting point in the [0, 1] coding (default: the base genome).
    descriptors, lows, highs, cells: the behaviour descriptors and the archive grid. emitters x batch genomes per
    generation; sigma: initial step (CMA) or mutation width (Gaussian) in the [0, 1] coding. learning_rate,
    threshold_min: CMA-MAE annealing (1 and -inf: plain archive). Returns (archive, history); log(dict) is called after
    every generation with: generation, coverage, qd_score (offset threshold_min if finite, else 0), best fitness,
    number of genomes added (new cells and improvements), restarts and wall time.
    """
    if emitter not in ("cma", "gaussian"):
        raise ValueError(f"unknown emitter {emitter!r} (cma or gaussian)")
    if batch < 2 or emitters < 1:
        raise ValueError("evolve_qd needs batch >= 2 and emitters >= 1")
    rng = np.random.default_rng([island, 5])
    x0 = np.clip(np.asarray(to_unit(base, genes) if u0 is None else u0, float), 0.0, 1.0)
    n = len(genes)
    archive = Archive(n, lows, highs, cells, learning_rate, threshold_min)
    describe = _descriptor_fn(descriptors)
    ems = [CMAEmitter(x0, sigma, batch, np.random.default_rng([island, 6, e])) for e in range(emitters)] \
        if emitter == "cma" else []
    offset = threshold_min if np.isfinite(threshold_min) else 0.0
    hist, t0 = [], time.time()
    for gen in range(gens):
        if emitter == "cma":
            U = np.concatenate([e.ask() for e in ems])
        else:
            parents = archive.sample(rng, emitters * batch) if len(archive.filled) else np.tile(x0, (emitters * batch, 1))
            U = np.clip(parents + sigma * rng.standard_normal(parents.shape), 0.0, 1.0)
        fit, info = evaluate([from_unit(base, genes, u, integer_roots) for u in U], seeds_of(island, gen, seeds_per_gen))
        fit = np.asarray(fit, float)
        status = np.zeros(len(U), np.int64)
        imp = np.zeros(len(U))
        for k in range(len(U)):                          # archive insertion is sequential by definition
            status[k], imp[k] = archive.add(U[k], fit[k], describe(info[k]), info[k])
        restarts = 0
        for e, em in enumerate(ems):
            s, im = status[e * batch:(e + 1) * batch], imp[e * batch:(e + 1) * batch]
            if not np.any(s > 0):
                em.reset(archive.sample(rng, 1)[0])
                restarts += 1
                continue
            if learning_rate < 1.0:                      # CMA-MAE: rank every candidate by improvement
                ranking = np.argsort(-im, kind="stable")
            else:                                        # CMA-ME: new cells first, then improvements, then the rest
                ranking = np.lexsort((-im, -s))
            em.tell(ranking)
        hist.append(dict(generation=gen, coverage=archive.coverage(), qd_score=archive.qd_score(offset),
                         best=float(archive.fitness[archive.best()]), added=int(np.sum(status > 0)), restarts=restarts,
                         wall_s=round(time.time() - t0, 1)))
        if log:
            log(hist[-1])
    return archive, hist
