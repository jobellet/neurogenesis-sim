"""Measures of critical dynamics in population activity (NumPy, O(T) memory and time).

- `branching_mr`: branching parameter m by multistep regression (Wilting & Priesemann 2018, Nat Commun), robust to
  subsampling: slopes r_k of A(t + k) on A(t), fitted as b * m^k. m = 1 is critical, m < 1 subcritical; the
  autocorrelation time is tau = -dt / ln m.
- `avalanches`: sizes and durations of runs of non-empty bins (Beggs & Plenz 2003, J Neurosci).
- `powerlaw_fit`, `powerlaw_fit_xmin`: discrete power law P(x) ∝ x^-alpha on [xmin, xmax] by maximum likelihood (Clauset, Shalizi & Newman
  2009, SIAM Rev; truncated at xmax for finite systems) with the Kolmogorov-Smirnov distance of the fit.
- `crackling`: the scaling relation <S>(D) ∝ D^gamma with gamma = (alpha_D - 1) / (alpha_S - 1) at criticality
  (Sethna, Dahmen & Myers 2001, Nature; Friedman et al. 2012, Phys Rev Lett).
- `summary`: all of the above from a spike-count series.

A power law alone does not prove criticality (Touboul & Destexhe 2010, PLoS One; Priesemann & Shriki 2018, PLoS
Comput Biol): use m, the exponents and the scaling relation together, and compare with sub- and supercritical controls.
Units: activity is a count per time bin; times are in bins unless `dt` is given.
"""
from __future__ import annotations

import numpy as np


def branching_mr(activity, k_max: int = 40, dt: float = 1.0, k_min: int = 1) -> dict:
    """Multistep-regression estimate of the branching parameter of a count series `activity` (T,).

    r_k = Cov(A_t, A_{t+k}) / Var(A_t) for k = k_min..k_max, fitted by least squares as b * m^k (m on a grid refined
    twice in [0, 1.2]; b in closed form). Returns m, b, tau (= -dt / ln m, inf for m >= 1), the slopes r_k and the
    fit's coefficient of determination. Constant series give m = nan."""
    a = np.asarray(activity, np.float64)
    k = np.arange(k_min, k_max + 1)
    out = dict(m=np.nan, b=np.nan, tau=np.nan, k=k, r=np.full(len(k), np.nan), r2=np.nan)
    if len(a) <= k_max + 2 or a.std() == 0:
        return out
    a = a - a.mean()
    var = float(np.mean(a * a))
    r = np.array([np.mean(a[:-kk] * a[kk:]) / var for kk in k])

    def fit(ms):
        p = ms[:, None] ** k[None, :]
        b = (p @ r) / np.maximum((p * p).sum(1), 1e-300)
        err = ((r[None, :] - b[:, None] * p) ** 2).sum(1)
        return b, err
    grid = np.linspace(0.0, 1.2, 1201)
    for _ in range(3):
        _, err = fit(grid)
        i = int(np.argmin(err))
        grid = np.linspace(grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)], 201)
    _, err = fit(grid)
    m = float(grid[int(np.argmin(err))])
    b, err = fit(np.array([m]))
    ss = float(((r - r.mean()) ** 2).sum())
    out.update(m=m, b=float(b[0]), tau=(-dt / np.log(m)) if 0 < m < 1 else (np.inf if m >= 1 else 0.0), r=r,
               r2=float(1 - err[0] / ss) if ss > 0 else np.nan)
    return out


def avalanches(counts, threshold: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """(sizes, durations) of avalanches: maximal runs of bins with count > `threshold`, bounded by empty bins. Size =
    total count in the run (minus threshold x duration when threshold > 0), duration = number of bins. Runs touching
    the ends of the series are dropped."""
    c = np.asarray(counts, np.float64)
    on = c > threshold
    if not on.any():
        return np.zeros(0), np.zeros(0, int)
    d = np.diff(np.r_[0, on.astype(np.int8), 0])
    start, stop = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    keep = (start > 0) & (stop < len(c))
    start, stop = start[keep], stop[keep]
    cs = np.r_[0.0, np.cumsum(c - threshold)]
    return cs[stop] - cs[start], (stop - start).astype(int)


def _zsum(a: np.ndarray, lo: int, hi: int, exact: int = 1000) -> np.ndarray:
    """sum_{x = lo}^{hi} x^-a for each exponent in `a`: exact over the first `exact` integers, then the
    Euler-Maclaurin integral of x^-a from L + 1/2 to hi + 1/2 (relative error < 1e-6 for x > 1000)."""
    a = np.asarray(a, np.float64)
    L = min(hi, lo + exact - 1)
    xs = np.log(np.arange(lo, L + 1, dtype=np.float64))
    z = np.exp(-a[:, None] * xs[None, :]).sum(1)
    if hi > L:
        p, q = L + 0.5, hi + 0.5
        one = np.isclose(a, 1.0)
        z = z + np.where(one, np.log(q / p), (p ** (1 - a) - q ** (1 - a)) / np.where(one, 1.0, a - 1))
    return z


def powerlaw_fit(x, xmin: float = 1, xmax: float | None = None, alphas=None) -> dict:
    """Maximum-likelihood exponent of a discrete power law on the integers in [xmin, xmax] (xmax: the largest value
    if None). Returns alpha, the KS distance between the empirical and fitted CDFs, the number of values used and the
    span in decades. Fewer than 10 values give nan."""
    x = np.rint(np.asarray(x, np.float64))
    xmin = int(max(1, xmin))
    xmax = int(x.max()) if xmax is None and len(x) else int(xmax or xmin)
    x = x[(x >= xmin) & (x <= xmax)]
    res = dict(alpha=np.nan, ks=np.nan, n=int(len(x)), decades=float(np.log10(max(xmax, 1) / xmin)), xmin=xmin,
               xmax=xmax)
    if len(x) < 10 or xmax <= xmin:
        return res
    slx = float(np.log(x).sum())
    grid = np.linspace(1.01, 4.0, 300) if alphas is None else np.asarray(alphas, np.float64)

    def nll(a):
        return a * slx + len(x) * np.log(_zsum(a, xmin, xmax))
    for _ in range(3):
        v = nll(grid)
        i = int(np.argmin(v))
        grid = np.linspace(grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)], 101)
    a = float(grid[int(np.argmin(nll(grid)))])
    u, cnt = np.unique(x, return_counts=True)
    emp = np.cumsum(cnt) / len(x)
    za = _zsum(np.array([a]), xmin, xmax)[0]
    cdf = np.array([_zsum(np.array([a]), xmin, int(v))[0] for v in u]) / za
    emp_before = np.r_[0.0, emp[:-1]]
    cdf_before = cdf - u ** -a / za
    res.update(alpha=a, ks=float(max(np.abs(emp - cdf).max(), np.abs(emp_before - cdf_before).max())))
    return res


def powerlaw_fit_xmin(x, xmax: float | None = None, min_n: int = 50, max_xmin: float | None = None) -> dict:
    """`powerlaw_fit` with xmin chosen among log-spaced candidates to minimise the KS distance (Clauset, Shalizi &
    Newman 2009), keeping at least `min_n` values and xmin <= max_xmin (default: xmax / 10, so at least one decade is
    fitted)."""
    x = np.asarray(x, np.float64)
    if len(x) < min_n:
        return powerlaw_fit(x, 1, xmax)
    top = float(xmax if xmax is not None else x.max())
    cap = max_xmin if max_xmin is not None else max(1.0, top / 10)
    cands = np.unique(np.rint(np.logspace(0, np.log10(max(cap, 1.0)), 12)).astype(int))
    best = None
    for c in cands:
        if np.sum(x >= c) < min_n:
            break
        f = powerlaw_fit(x, c, xmax)
        if np.isfinite(f["ks"]) and (best is None or f["ks"] < best["ks"]):
            best = f
    return best or powerlaw_fit(x, 1, xmax)


def crackling(sizes, durations, alpha_size: float, alpha_duration: float, d_min: int = 2) -> dict:
    """Scaling of the mean size with duration, <S>(D) ∝ D^gamma, fitted on log-log over durations >= d_min that occur
    at least 3 times, against the prediction gamma = (alpha_D - 1) / (alpha_S - 1)."""
    s, d = np.asarray(sizes, np.float64), np.asarray(durations)
    res = dict(gamma_fit=np.nan, gamma_pred=np.nan, n_durations=0)
    if alpha_size > 1 and np.isfinite(alpha_duration):
        res["gamma_pred"] = float((alpha_duration - 1) / (alpha_size - 1))
    u, cnt = np.unique(d[d >= d_min], return_counts=True)
    u = u[cnt >= 3]
    res["n_durations"] = int(len(u))
    if len(u) >= 3:
        ms = np.array([s[d == v].mean() for v in u])
        res["gamma_fit"] = float(np.polyfit(np.log(u), np.log(ms), 1)[0])
    return res


def summary(spikes_per_tick, bin_ticks: int | None = None, k_max_ms: int = 100) -> dict:
    """Criticality measures of a population spike-count series (one value per 1-ms tick).

    m and tau come from multistep regression on 1-ms counts (k = 1..k_max_ms). Avalanches use bins of `bin_ticks`
    (default: the mean inter-spike interval of the population, rounded, at least 1; Beggs & Plenz 2003) with
    xmin = 1, xmax = the largest event. Also the mean count per tick and the fraction of empty bins."""
    a = np.asarray(spikes_per_tick, np.float64)
    T = len(a)
    rate = float(a.mean()) if T else 0.0
    if bin_ticks is None:
        bin_ticks = int(max(1, round(1.0 / rate))) if rate > 0 else 1
    nb = T // bin_ticks
    binned = a[:nb * bin_ticks].reshape(nb, bin_ticks).sum(1) if nb else np.zeros(0)
    mr = branching_mr(a, k_max=k_max_ms)
    s, d = avalanches(binned)
    fs = powerlaw_fit_xmin(s) if len(s) else powerlaw_fit([])
    fd = powerlaw_fit_xmin(d) if len(d) else powerlaw_fit([])
    cr = crackling(s, d, fs["alpha"], fd["alpha"], d_min=max(2, fd["xmin"])) if len(s) else \
        crackling([], [], np.nan, np.nan)
    return dict(m=mr["m"], tau_ms=mr["tau"], mr_r2=mr["r2"], rate_per_tick=rate, bin_ticks=int(bin_ticks),
                frac_empty_bins=float(np.mean(binned == 0)) if nb else np.nan, n_avalanches=int(len(s)),
                alpha_size=fs["alpha"], ks_size=fs["ks"], decades_size=fs["decades"], xmin_size=fs["xmin"],
                alpha_duration=fd["alpha"], ks_duration=fd["ks"], decades_duration=fd["decades"],
                xmin_duration=fd["xmin"], gamma_fit=cr["gamma_fit"],
                gamma_pred=cr["gamma_pred"])


def branching_process(m: float, T: int, h: float, n: int = 10_000, rng=None) -> np.ndarray:
    """Counts of a driven branching process (Poisson offspring, mean m per unit; Poisson drive of mean h per step),
    capped at n: the reference process of Wilting & Priesemann 2018 for testing the estimators."""
    rng = np.random.default_rng(rng)
    a = np.zeros(T, np.int64)
    x = 0
    for t in range(T):
        x = min(n, rng.poisson(m * x) + rng.poisson(h))
        a[t] = x
    return a
