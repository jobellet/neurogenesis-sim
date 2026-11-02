"""Cost of a development schedule before running it (D3): cells, synapses, memory and time per stage.

The schedule is walked once without running it. Each stage's cell and synapse counts are predicted from its params
(worst case: a `Gene` or `Fit` at its upper bound, see `params.worst_case`) and its declared cost(N, E, params) is
summed. Time is ops x seconds-per-op, with seconds-per-op measured once per machine on a fixed development workload and
cached next to the simulation calibration (~/.cache/neurogenesis/throughput.json). Like the simulation estimate, this
is a linear extrapolation: treat it as a guide, not a bound.

    python -m neurogenesis estimate --project project.json
"""
from __future__ import annotations

import json
import platform
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .cost import CACHE, CostError, _duration, _human, _load, available_memory
from .params import param_from_dict, worst_case

TISSUE_CELL_BYTES = 136        # per cell, every Tissue array (see Tissue.memory_bytes)
TISSUE_SYNAPSE_BYTES = 16      # per synapse: pre, post, weight, delay (int32)
DEFAULT_SYNAPSES_PER_CELL = 100  # assumed by stages whose synapse count depends on the tissue (rules, legacy growth)


def _w(params: Dict[str, Any], key: str, default: Any) -> Any:
    return worst_case(params.get(key), default)


def _seed(N, E, p):
    if p.get("points") is not None:
        pts = _w(p, "points", None)
        n = len(pts) if isinstance(pts, (list, tuple, np.ndarray)) else int(_w(p, "max_cells", 100))
    elif p.get("density") is not None:
        n = int(_w(p, "max_cells", 100))
    else:
        n = max(0, int(_w(p, "N", 0)))
    return N + n, E


def _proliferate(N, E, p):
    n = int(round(N * (1.0 + min(1.0, max(0.0, float(_w(p, "prob", 0.0)))))))
    if p.get("max_cells") is not None:
        n = min(n, max(N, int(_w(p, "max_cells", n))))
    return n, E


def _place(N, E, p):
    pos = _w(p, "positions", [])
    return N + (len(pos) if isinstance(pos, (list, tuple, np.ndarray)) else 0), E


def _connect(N, E, p):
    pre = _w(p, "pre", [])
    e = len(pre) if isinstance(pre, (list, tuple, np.ndarray)) else 0
    if p.get("matrix") is not None:
        e += N * N
    rules = _w(p, "rules", None)
    if rules:
        e += len(rules if isinstance(rules, list) else [rules]) * N * DEFAULT_SYNAPSES_PER_CELL
    return N, E + e


def _grow_axons(N, E, p):
    from .stages.connectivity import _cost_projections
    n_proj, distinct, sigmas = _cost_projections(p)
    side = N // 2 if distinct else N
    g = _w(p, "guidance", {})
    p0s = []
    if isinstance(g, dict):
        p0s = [float(worst_case(v.get("p0"), 1.0)) for v in g.values() if isinstance(v, dict)] or [float(worst_case(g.get("p0"), 1.0))]
    elif isinstance(g, list):
        p0s = [float(worst_case(v.get("p0"), 1.0)) for v in g if isinstance(v, dict)]
    p0 = max(p0s or [1.0])
    kernel = min(1.0, (2.0 * np.pi) ** 1.5 * max(sigmas) ** 3)       # integral of the Gaussian kernel in the unit box
    return N, E + int(n_proj * side * side * p0 * kernel)


def _legacy(N, E, p):
    plan = _w(p, "plan", None)
    n = 0
    if isinstance(plan, dict):
        for r in plan.get("regions", []):
            c = r.get("count", 0) if isinstance(r, dict) else 0
            n += int(c.get("hi", c.get("value", 0))) if isinstance(c, dict) else int(c or 0)
    n = n or 1000
    return N + n, E + n * DEFAULT_SYNAPSES_PER_CELL


# Predicted (N, E) after one call of a stage, from (N, E) before it. Stages not listed keep N and E (or reduce them).
PREDICTORS: Dict[str, Callable[[int, int, Dict[str, Any]], Tuple[int, int]]] = {
    "seed_cells": _seed, "proliferate": _proliferate, "place_by_hand": _place, "connect_by_hand": _connect,
    "grow_axons": _grow_axons, "legacy_grow_stage": _legacy,
}


def predict(operator: str, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
    """(N, E) after one call of `operator`: the stage class's own `predict` if it has one, else `PREDICTORS`."""
    from .stages.base import STAGE_REGISTRY
    cls = STAGE_REGISTRY.get(operator)
    if cls is not None and hasattr(cls, "predict"):
        return cls.predict(N, E, params)
    f = PREDICTORS.get(operator)
    return f(N, E, params) if f else (N, E)


def schedule_rows(project: Dict[str, Any], N0: int = 0, E0: int = 0) -> List[Dict[str, Any]]:
    """One row per stage call (repeats expanded): name, operator, rep, N and E before the call, declared bytes and ops."""
    import neurogenesis.stages  # noqa: F401  (registers the stages)
    from .stages.base import STAGE_REGISTRY
    for plugin in project.get("plugins", []):
        __import__(plugin)
    rows, N, E = [], int(N0), int(E0)
    for i, cfg in enumerate(project.get("schedule", [])):
        params = {k: (param_from_dict(v) if isinstance(v, dict) else v) for k, v in cfg.get("params", {}).items()}
        op = cfg["operator"]
        if op not in STAGE_REGISTRY:
            raise ValueError(f"Operator {op!r} not found in registry")
        cls = STAGE_REGISTRY[op]
        for rep in range(int(cfg.get("repeat", 1))):
            b, ops = cls.cost(N, E, params) if hasattr(cls, "cost") else (0, 0)
            N2, E2 = predict(op, N, E, params)
            rows.append(dict(name=cfg.get("name", f"stage_{i}"), operator=op, rep=rep, N=N, E=E, N_after=N2,
                             E_after=E2, bytes=int(b), ops=int(ops)))
            N, E = N2, E2
    return rows


def _machine() -> str:
    return f"development@{platform.machine()}:{platform.processor() or platform.system()}:numpy{np.__version__}"


def calibrate(refresh: bool = False) -> float:
    """Seconds per declared operation on this machine: a fixed workload (seed, proliferate, migrate with cell-list
    repulsion, express) timed once against its declared ops, cached."""
    cache = _load()
    key = _machine()
    if key in cache and not refresh:
        return float(cache[key]["seconds_per_op"])
    from .stages.base import run_schedule
    project = {"schedule": [
        {"name": "seed", "operator": "seed_cells", "params": {"N": 20000, "geometry": {"type": "Const", "value": "box"}}},
        {"name": "grow", "operator": "proliferate", "params": {"prob": 0.5}},
        {"name": "move", "operator": "migrate", "params": {"speed": 0.01, "min_distance": 0.03, "steps": 2}},
        {"name": "expr", "operator": "express", "params": {"K": 4}}],
        "geometry": {"box": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}}}
    run_schedule(project, {}, 0)                                   # warm-up (imports, allocations)
    t0 = time.perf_counter()
    run_schedule(project, {}, 0)
    dt = time.perf_counter() - t0
    ops = sum(r["ops"] for r in schedule_rows(project))
    spo = dt / max(1, ops)
    cache[key] = dict(seconds_per_op=spo, measured=time.strftime("%Y-%m-%d %H:%M"))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1))
    return spo


def estimate_development(project: Dict[str, Any], N0: int = 0, E0: int = 0, calibrated: bool = True) -> Dict[str, Any]:
    """dict: per-stage `rows`, final cells and synapses, peak memory (largest stage memory plus the tissue it holds),
    total ops, seconds (None when not calibrated and calibrated=False), available memory, `fits`, and a verdict."""
    rows = schedule_rows(project, N0, E0)
    peak = 0
    for r in rows:
        tissue = max(r["N"], r["N_after"]) * TISSUE_CELL_BYTES + max(r["E"], r["E_after"]) * TISSUE_SYNAPSE_BYTES
        r["peak_bytes"] = r["bytes"] + tissue
        peak = max(peak, r["peak_bytes"])
    ops = sum(r["ops"] for r in rows)
    avail = available_memory()
    spo = calibrate() if calibrated else _load().get(_machine(), {}).get("seconds_per_op")
    out = dict(rows=rows, cells=rows[-1]["N_after"] if rows else N0, synapses=rows[-1]["E_after"] if rows else E0,
               peak_bytes=int(peak), ops=int(ops), available_bytes=avail,
               fits=avail is None or peak <= 0.8 * avail, seconds=None if spo is None else ops * float(spo))
    mem = f"peak memory {_human(peak, 'B')}" + (f" of {_human(avail, 'B')} available" if avail else "")
    t = "time not calibrated" if out["seconds"] is None else f"about {_duration(out['seconds'])}"
    out["verdict"] = (f"{'fits' if out['fits'] else 'DOES NOT FIT'}: {out['cells']:,} cells, {out['synapses']:,} synapses, "
                      f"{mem}; {t}")
    return out


def check_development(project: Dict[str, Any], N0: int = 0, E0: int = 0, force: bool = False) -> Dict[str, Any]:
    """Refuses (CostError) a schedule whose predicted peak memory exceeds 80 % of the available memory, unless force.
    Never runs the calibration benchmark itself."""
    e = estimate_development(project, N0, E0, calibrated=False)
    if not e["fits"] and not force:
        raise CostError(e["verdict"] + " (pass force=True to try anyway)")
    return e


def format_rows(e: Dict[str, Any]) -> str:
    lines = [f"{'stage':24s} {'operator':20s} {'cells':>12s} {'synapses':>14s} {'memory':>10s} {'ops':>10s}"]
    for r in e["rows"]:
        name = r["name"] + (f"[{r['rep']}]" if r["rep"] else "")
        lines.append(f"{name[:24]:24s} {r['operator'][:20]:20s} {r['N_after']:>12,} {r['E_after']:>14,} "
                     f"{_human(r['peak_bytes'], 'B'):>10s} {_human(r['ops'], ''):>10s}")
    return "\n".join(lines)
