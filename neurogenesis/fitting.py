"""Supervised fitting of `Fit` params to data targets (E2).

A `Fit(target, init, lo, hi)` param is a free number named `target`. Its fitted value is stored in the genome under
`params.FIT_KEY` ({target: value}), so `resolve` and `run_schedule` use it everywhere the Fit appears; without a
fitted value it resolves to `init`. `fit()` searches the values that make the developed tissue match measured targets:

    targets = [{"metric": "cell_count", "value": 800, "scale": 50},
               {"metric": "layer_thickness", "cell_type": 1, "axis": 2, "value": 0.2, "scale": 0.02}]
    result = fit(project, targets, seeds=(0, 1, 2))
    genome = result.genome                       # base genome + {"__fit__": {...}}

Each target is {"metric": name, "value": number, "scale": tolerance (default 1), "weight": 1, ...metric options}.
The loss of a candidate is the mean over development seeds of sum_k weight_k ((metric_k - value_k) / scale_k)^2, so
several seeds per evaluation make the fit robust to developmental noise. The default optimiser is a CMA-ES (Hansen &
Ostermeier 2001, Evol Comput) on the [0, 1]-coded Fit values: gradient free, robust to stochastic development, and
deterministic for a given `seed`. Metrics are registered with `@register_metric`; built in: cell_count, density,
layer_thickness, synapse_count, mean_in_degree, connection_probability, firing_rate.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .params import FIT_KEY, collect_fits
from .tissue import Tissue

METRICS: Dict[str, Callable[[Tissue, Dict[str, Any]], float]] = {}


def register_metric(name: str):
    """Registers metric(tissue, options) -> float under `name`."""
    def deco(f):
        METRICS[name] = f
        return f
    return deco


def select(tissue: Tissue, options: Dict[str, Any], prefix: str = "") -> np.ndarray:
    """Indices of living cells matching options `<prefix>region` and `<prefix>cell_type` (int or list; absent = all)."""
    mask = tissue.alive.copy()
    for key in ("region", "cell_type"):
        v = options.get(prefix + key)
        if v is not None:
            mask &= np.isin(getattr(tissue, key), np.asarray(v).ravel())
    return np.flatnonzero(mask)


@register_metric("cell_count")
def _cell_count(t: Tissue, o: Dict[str, Any]) -> float:
    """Number of living cells (optionally of a region / cell type)."""
    return float(len(select(t, o)))


@register_metric("density")
def _density(t: Tissue, o: Dict[str, Any]) -> float:
    """Selected cells per unit volume; option `volume` (space units cubed, required)."""
    return float(len(select(t, o))) / float(o["volume"])


@register_metric("layer_thickness")
def _layer_thickness(t: Tissue, o: Dict[str, Any]) -> float:
    """Extent of the selected cells along `axis` (0, 1, 2 or a vector; default 2): the `upper` minus `lower`
    percentiles (default 95 and 5) of their coordinates."""
    idx = select(t, o)
    if len(idx) < 2:
        return 0.0
    axis = o.get("axis", 2)
    x = t.positions[idx] @ (np.eye(3)[axis] if np.isscalar(axis) else np.asarray(axis, float) / np.linalg.norm(axis))
    return float(np.percentile(x, o.get("upper", 95)) - np.percentile(x, o.get("lower", 5)))


@register_metric("synapse_count")
def _synapse_count(t: Tissue, o: Dict[str, Any]) -> float:
    """Synapses between selected pre (`pre_region`, `pre_cell_type`) and post (`post_...`) cells."""
    c = t.connectivity
    pre_ok = np.zeros(len(t.alive), bool)
    pre_ok[select(t, o, "pre_")] = True
    post_ok = np.zeros(len(t.alive), bool)
    post_ok[select(t, o, "post_")] = True
    return float(np.sum(pre_ok[c.pre] & post_ok[c.post])) if len(c.pre) else 0.0


@register_metric("mean_in_degree")
def _mean_in_degree(t: Tissue, o: Dict[str, Any]) -> float:
    """Synapses per selected post cell (from selected pre cells)."""
    n = len(select(t, o, "post_"))
    return _synapse_count(t, o) / n if n else 0.0


@register_metric("connection_probability")
def _connection_probability(t: Tissue, o: Dict[str, Any]) -> float:
    """Fraction of (pre, post) pairs at distance in [`d_min`, `d_max`) (default 0, inf) that are connected; pairs come
    from the cell list when `d_max` is finite, so memory is O(pairs within d_max)."""
    from .spatial import CellList
    pre, post = select(t, o, "pre_"), select(t, o, "post_")
    if len(pre) == 0 or len(post) == 0:
        return 0.0
    d_min, d_max = float(o.get("d_min", 0.0)), float(o.get("d_max", np.inf))
    c = t.connectivity
    syn_d = np.linalg.norm(t.positions[c.post] - t.positions[c.pre], axis=1) if len(c.pre) else np.zeros(0)
    pre_ok = np.isin(c.pre, pre) & np.isin(c.post, post) & (syn_d >= d_min) & (syn_d < d_max) & (c.pre != c.post)
    connected = len(set(zip(c.pre[pre_ok].tolist(), c.post[pre_ok].tolist())))
    if np.isfinite(d_max):
        q, k, d = CellList(t.positions[post], d_max).query_radius(t.positions[pre], d_max, return_distances=True)
        n_pairs = int(np.sum((d >= d_min) & (d < d_max) & (pre[q] != post[k])))
    else:
        n_pairs = len(pre) * len(post) - len(np.intersect1d(pre, post))
    return connected / n_pairs if n_pairs else 0.0


@register_metric("firing_rate")
def _firing_rate(t: Tissue, o: Dict[str, Any]) -> float:
    """Mean rate (Hz) of the selected cells in a `lif_int` simulation of `ticks` (default 500) with a constant
    `ext_current` (default 0) and kernel seed `sim_seed` (default 0)."""
    from .stages.refinement import simulate_tissue
    t = copy.deepcopy(t)
    t.compact()
    ticks = int(o.get("ticks", 500))
    ext = np.full(len(t.alive), int(o.get("ext_current", 0)), np.int32)
    spikes = simulate_tissue(t, ticks, int(o.get("sim_seed", 0)), ext)
    idx = select(t, o)
    return float(spikes[:, idx].sum() * 1000.0 / (ticks * max(1, len(idx))))


def target_loss(tissue: Tissue, targets: Sequence[Dict[str, Any]]) -> Tuple[float, List[float]]:
    """(sum_k weight ((metric - value) / scale)^2, list of metric values) of one tissue."""
    loss, values = 0.0, []
    for tg in targets:
        if tg["metric"] not in METRICS:
            raise ValueError(f"unknown metric {tg['metric']!r} (registered: {sorted(METRICS)})")
        m = METRICS[tg["metric"]](tissue, tg)
        values.append(m)
        loss += float(tg.get("weight", 1.0)) * ((m - float(tg["value"])) / float(tg.get("scale", 1.0))) ** 2
    return loss, values


def with_fit(genome: Dict[str, Any], values: Dict[str, float]) -> Dict[str, Any]:
    """Copy of a genome with fitted values set (merged with any already there)."""
    g = copy.deepcopy(genome)
    g[FIT_KEY] = {**g.get(FIT_KEY, {}), **{k: float(v) for k, v in values.items()}}
    return g


def evaluate(project: Dict[str, Any], genome: Dict[str, Any], targets: Sequence[Dict[str, Any]],
             seeds: Sequence[int]) -> Tuple[float, List[List[float]]]:
    """Mean target loss over development seeds, and the metric values per seed."""
    from .stages.base import run_schedule
    losses, values = [], []
    for s in seeds:
        loss, v = target_loss(run_schedule(project, genome, int(s)), targets)
        losses.append(loss)
        values.append(v)
    return float(np.mean(losses)), values


def cmaes(f: Callable[[np.ndarray], float], x0: np.ndarray, sigma0: float = 0.3, iterations: int = 30,
          popsize: Optional[int] = None, seed: int = 0, log: Optional[Callable[[dict], None]] = None):
    """Minimises f on [0, 1]^d with a CMA-ES (rank-one and rank-mu updates, cumulative step-size adaptation; Hansen
    2016, arXiv:1604.00772). Candidates are clipped to the cube. Returns (best x, best f, history)."""
    rng = np.random.default_rng(seed)
    d = len(x0)
    lam = popsize or 4 + int(3 * np.log(d))
    mu = lam // 2
    w = np.log(mu + 0.5) - np.log(np.arange(1, mu + 1))
    w /= w.sum()
    mueff = 1.0 / np.sum(w ** 2)
    cc = (4 + mueff / d) / (d + 4 + 2 * mueff / d)
    cs = (mueff + 2) / (d + mueff + 5)
    c1 = 2 / ((d + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 2 + 1 / mueff) / ((d + 2) ** 2 + mueff))
    damps = 1 + 2 * max(0.0, np.sqrt((mueff - 1) / (d + 1)) - 1) + cs
    chi = np.sqrt(d) * (1 - 1 / (4 * d) + 1 / (21 * d * d))
    m, sigma = np.clip(np.asarray(x0, float), 0, 1), float(sigma0)
    C, pc, ps = np.eye(d), np.zeros(d), np.zeros(d)
    best_x, best_f = m.copy(), float(f(m))
    hist = [dict(iteration=-1, best=best_f, sigma=sigma)]
    for it in range(iterations):
        evals, B = np.linalg.eigh(C)
        D = np.sqrt(np.maximum(evals, 1e-20))
        z = rng.standard_normal((lam, d))
        y = z @ (B * D).T
        X = np.clip(m + sigma * y, 0, 1)
        F = np.asarray([f(x) for x in X])
        o = np.argsort(F, kind="stable")
        if F[o[0]] < best_f:
            best_f, best_x = float(F[o[0]]), X[o[0]].copy()
        y_sel = (X[o[:mu]] - m) / sigma
        y_w = w @ y_sel
        m = m + sigma * y_w
        C_inv_sqrt = (B / D) @ B.T
        ps = (1 - cs) * ps + np.sqrt(cs * (2 - cs) * mueff) * (C_inv_sqrt @ y_w)
        hsig = np.linalg.norm(ps) / np.sqrt(1 - (1 - cs) ** (2 * (it + 1))) < (1.4 + 2 / (d + 1)) * chi
        pc = (1 - cc) * pc + hsig * np.sqrt(cc * (2 - cc) * mueff) * y_w
        C = (1 - c1 - cmu) * C + c1 * (np.outer(pc, pc) + (not hsig) * cc * (2 - cc) * C) + cmu * (y_sel.T * w) @ y_sel
        sigma *= np.exp((cs / damps) * (np.linalg.norm(ps) / chi - 1))
        sigma = float(min(sigma, 1.0))
        hist.append(dict(iteration=it, best=best_f, generation_best=float(F[o[0]]), sigma=sigma))
        if log:
            log(hist[-1])
    return best_x, best_f, hist


@dataclass
class FitResult:
    values: Dict[str, float]                 # fitted value per Fit target
    loss: float                              # mean target loss over the fitting seeds
    genome: Dict[str, Any]                   # base genome with the fitted values (params.FIT_KEY)
    metrics: List[List[float]]               # metric values per seed at the fitted values
    history: List[dict] = field(default_factory=list)


def fit(project: Dict[str, Any], targets: Sequence[Dict[str, Any]], seeds: Sequence[int] = (0, 1, 2),
        genome: Optional[Dict[str, Any]] = None, iterations: int = 30, popsize: Optional[int] = None,
        sigma0: float = 0.3, seed: int = 0, log: Optional[Callable[[dict], None]] = None) -> FitResult:
    """Fits every Fit param of the project (`collect_fits`) to the targets with CMA-ES, starting from their init (or
    the values already in the genome). Deterministic for given seeds. A project without Fit params is evaluated as is."""
    genome = genome or {}
    fits = collect_fits(project)
    if not fits:
        loss, metrics = evaluate(project, genome, targets, seeds)
        return FitResult({}, loss, copy.deepcopy(genome), metrics)
    lo = np.asarray([f[2] for f in fits])
    span = np.maximum(np.asarray([f[3] for f in fits]) - lo, 1e-12)
    current = genome.get(FIT_KEY, {})
    x0 = (np.asarray([current.get(f[0], f[1]) for f in fits]) - lo) / span

    def values_of(x):
        return {f[0]: float(v) for f, v in zip(fits, lo + np.clip(x, 0, 1) * span)}

    def loss_of(x):
        return evaluate(project, with_fit(genome, values_of(x)), targets, seeds)[0]

    x, best, hist = cmaes(loss_of, x0, sigma0=sigma0, iterations=iterations, popsize=popsize, seed=seed, log=log)
    g = with_fit(genome, values_of(x))
    loss, metrics = evaluate(project, g, targets, seeds)
    return FitResult(values_of(x), loss, g, metrics, hist)
