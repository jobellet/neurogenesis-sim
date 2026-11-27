"""Validation harness (E4): declarative assays stored in a module and rerun by `python -m neurogenesis validate`.

An assay is a dict (JSON), listed in a module's `validation["assays"]`:

    {"name": "responds", "ticks": 100, "blank": 20, "seeds": [1000, 1001, 1002],
     "knockout": {"regions": ["hidden"], "projections": [["in", "out"]]},        # optional virtual knockout
     "stimuli": [{}, {"in": 300}],                       # one dict per stimulus: region -> current (toolbox units)
     "readout": {"region": "out", "measure": "rate"},    # rate (Hz, mean over cells) or fraction_active
     "metric": "difference",                             # mean | difference | ratio | selectivity | stimulus:<k>
     "gate": {"min": 20.0},                              # min and / or max on the metric
     "pass_fraction": 1.0}                               # fraction of seeds that must pass (default 1)

Each seed grows one individual (`development.grow`, with the module genome and its tonic currents) and runs all
stimuli in sequence with the batched JAX kernel (`spiking.batch.simulate_counts`); the metric is computed per seed and
gated. Defaults: ticks 100, blank 0, seeds 1000-1004 (never used in evolution, see `evolution.robust`), metric mean.
Knockout assays compare a module with a region or projection removed (`development.grow.knockout`).

Optional checks for spiking assays (all off when absent; existing assays give the same results):
- `"reset": true`: every stimulus starts from rest. Without it the state left by one stimulus carries over to the
  next (`simulate_counts`), as with the rest period between inputs of Diehl & Cook (2015, Front Comput Neurosci).
- `"order_check": {"tolerance": t}`: reruns the stimuli in reverse order; reports `order_max_diff`, the largest change
  of a per-stimulus readout, and fails the assay above `t` (readout units).
- `"control": {"knockout": {...}, "lesion": {...}, "gate": {...}}`: a matched control grown from the same seeds and given
  the same stimuli without the mechanism; reports `control_values`, per-seed `effect` (value - control),
  `effect_mean`, `effect_sd`, and with `gate`, gates the effect. Knockouts show what a part is needed for, not how it
  works (Jonas & Kording 2017, PLoS Comput Biol).
- `"lesion": {"fraction": f, "target": "cells" | "synapses", "seed": 0}`: silences a random fraction of cells (all
  their synapses removed, their spikes left out of the readout) or of synapses before running, from its own random
  stream; robustness to neuron loss (Barrett, Denève & Machens 2016, eLife).
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np

from .data.targets import TARGETS, TargetSpec, get_target, register_target
from .development.grow import grow, knockout, region_of, tonic_current
from .evolution.robust import HELD_OUT

MEASURES = ("rate", "fraction_active")


def _metric(values: np.ndarray, metric: str) -> float:
    """Scalar of one seed from its readout per stimulus."""
    v = np.asarray(values, float)
    if metric == "mean":
        return float(v.mean())
    if metric == "difference":
        return float(v[-1] - v[0])
    if metric == "ratio":
        return float(v[-1] / max(v[0], 1e-9))
    if metric == "selectivity":
        return float((v.max() - v.min()) / max(v.max() + v.min(), 1e-9))
    if metric.startswith("stimulus:"):
        return float(v[int(metric.split(":", 1)[1])])
    raise ValueError(f"unknown assay metric {metric!r}")


def _gate(x: float, gate: Dict[str, Any]) -> bool:
    ok = True
    if "min" in gate:
        ok &= x >= float(gate["min"])
    if "max" in gate:
        ok &= x <= float(gate["max"])
    return bool(ok)


def run_assay(module, assay: Dict[str, Any]) -> Dict[str, Any]:
    """Runs one assay on a module. Returns dict(name, values per seed, passed per seed, pass_fraction, ok)."""
    genome = module.genome
    ko = assay.get("knockout")
    if ko:
        genome = knockout(genome, regions=ko.get("regions", ()), projections=[tuple(p) for p in ko.get("projections", ())])
    seeds = [int(s) for s in assay.get("seeds", HELD_OUT[:5])]

    readout = assay.get("readout", {})
    # Check if this assay specifies an objective target
    target_name = assay.get("target") or readout.get("target") or (readout.get("measure") if readout.get("measure") in TARGETS else None)

    if target_name and target_name in TARGETS and not TARGETS[target_name].requires_spiking:
        target_spec = TARGETS[target_name]
        opts = {**assay, **readout, **(readout.get("options") or {}), **(assay.get("options") or {})}
        if "region" in readout and "region" not in opts:
            opts["region"] = readout["region"]
        values = []
        for s in seeds:
            net = grow(module.plan, genome, s)
            from .tissue import Tissue
            tissue = Tissue.from_network(net) if hasattr(Tissue, "from_network") and not isinstance(net, Tissue) else net
            val = target_spec(tissue, opts)
            values.append(float(val))
        gate = assay.get("gate", {})
        passed = [_gate(v, gate) for v in values]
        frac = float(np.mean(passed))
        return dict(name=assay.get("name", "assay"), seeds=seeds, values=[round(v, 4) for v in values], passed=passed,
                    pass_fraction=frac, ok=frac >= float(assay.get("pass_fraction", 1.0)))

    # Spiking assay requiring simulate_counts
    measure = readout.get("measure", "rate")
    if measure not in MEASURES:
        raise ValueError(f"unknown readout measure {measure!r} (use {MEASURES})")
    metric = assay.get("metric", "mean")
    per_stim = _spiking_readouts(module, genome, seeds, assay)
    values = [_metric(v, metric) for v in per_stim]
    gate = assay.get("gate", {})
    passed = [_gate(v, gate) for v in values]
    frac = float(np.mean(passed))
    ok = frac >= float(assay.get("pass_fraction", 1.0))
    result = dict(name=assay.get("name", "assay"), seeds=seeds, values=[round(v, 4) for v in values], passed=passed,
                  pass_fraction=frac, ok=ok)

    order = assay.get("order_check")
    if order:
        tol = float(order.get("tolerance", 0.0)) if isinstance(order, dict) else 0.0
        reverse = _spiking_readouts(module, genome, seeds, assay, reverse=True)
        diff = max((float(np.max(np.abs(a - b))) for a, b in zip(per_stim, reverse)), default=0.0)
        result.update(order_max_diff=round(diff, 4), order_ok=diff <= tol)
        result["ok"] = result["ok"] and diff <= tol

    control = assay.get("control")
    if control:
        cgenome = module.genome
        cko = control.get("knockout")
        if cko:
            cgenome = knockout(cgenome, regions=cko.get("regions", ()),
                               projections=[tuple(p) for p in cko.get("projections", ())])
        cassay = {k: v for k, v in assay.items() if k not in ("knockout", "lesion")}
        if control.get("lesion"):
            cassay["lesion"] = control["lesion"]
        cvalues = [_metric(v, metric) for v in _spiking_readouts(module, cgenome, seeds, cassay)]
        effect = np.asarray(values) - np.asarray(cvalues)
        result.update(control_values=[round(v, 4) for v in cvalues], effect=[round(float(e), 4) for e in effect],
                      effect_mean=round(float(effect.mean()), 4), effect_sd=round(float(effect.std()), 4))
        if "gate" in control:
            epass = [_gate(float(e), control["gate"]) for e in effect]
            result["effect_passed"] = epass
            result["ok"] = result["ok"] and float(np.mean(epass)) >= float(assay.get("pass_fraction", 1.0))
    return result


def _lesion(net, lesion: Dict[str, Any], seed: int) -> np.ndarray:
    """Silences a random fraction of cells (all their synapses removed) or of synapses (weight 0), in place.

    The draw comes from its own stream, seeded by the lesion `seed` and the individual's seed, so the same assay lesions
    the same cells. Returns the (N,) mask of lesioned cells (all False for a synapse lesion). Cells keep their index.
    """
    frac = float(lesion.get("fraction", 0.0))
    if not 0.0 <= frac <= 1.0:
        raise ValueError("lesion fraction must be in [0, 1]")
    target = lesion.get("target", "cells")
    rng = np.random.default_rng([int(lesion.get("seed", 0)), int(seed)])
    N = net.num_neurons
    arrays = net.synapse_arrays
    if arrays is None:
        pre = np.array([s.pre for s in net.synapses], dtype=np.int64)
        post = np.array([s.post for s in net.synapses], dtype=np.int64)
    else:
        pre, post = np.asarray(arrays["pre"], np.int64), np.asarray(arrays["post"], np.int64)
    if target == "cells":
        dead = np.zeros(N, dtype=bool)
        dead[rng.choice(N, size=int(round(frac * N)), replace=False)] = True
        cut = dead[pre] | dead[post] if len(pre) else np.zeros(0, bool)
    elif target == "synapses":
        dead = np.zeros(N, dtype=bool)
        cut = np.zeros(len(pre), dtype=bool)
        cut[rng.choice(len(pre), size=int(round(frac * len(pre))), replace=False)] = True
    else:
        raise ValueError(f"unknown lesion target {target!r} (use 'cells' or 'synapses')")
    if np.any(cut):
        if arrays is None:
            for i in np.nonzero(cut)[0]:
                net.synapses[i].weight = 0
        else:
            w = np.array(arrays["weight"], copy=True)
            w[cut] = 0
            arrays["weight"] = w
    return dead


def _spiking_readouts(module, genome, seeds, assay, reverse: bool = False) -> List[np.ndarray]:
    """Readout per stimulus (S,) for each seed. With `reverse` the stimuli run in reverse order (results are put
    back in the original order); with assay `reset` every stimulus starts from rest instead of from the state the
    previous one left; an assay `lesion` silences cells or synapses first (`_lesion`)."""
    from .spiking.batch import simulate_counts
    ticks, blank = int(assay.get("ticks", 100)), int(assay.get("blank", 0))
    stimuli: List[Dict[str, float]] = assay.get("stimuli") or [{}]
    readout = assay.get("readout", {})
    measure = readout.get("measure", "rate")
    lesion = assay.get("lesion")
    nets, exts, outs = [], [], []
    for s in seeds:
        net = grow(module.plan, genome, s)
        dead = _lesion(net, lesion, s) if lesion else np.zeros(net.num_neurons, bool)
        base = tonic_current(net, module.plan, genome)
        ext = np.tile(base, (len(stimuli), 1)).astype(np.int32)
        for k, stim in enumerate(stimuli):
            for region, current in stim.items():
                if region in module.plan.ids:
                    ext[k, region_of(net, module.plan, region)] += int(round(current))
        nets.append(net)
        exts.append(ext[::-1] if reverse else ext)
        idx = region_of(net, module.plan, readout["region"]) if readout.get("region") in module.plan.ids else np.zeros(0, int)
        outs.append((np.asarray(idx), dead))
    if assay.get("reset"):
        parts = [simulate_counts(nets, [e[k:k + 1] for e in exts], ticks=ticks, blank=blank, model=module.neuron_model)
                 for k in range(len(stimuli))]
        counts = np.concatenate(parts, axis=1)
    else:
        counts = simulate_counts(nets, exts, ticks=ticks, blank=blank, model=module.neuron_model)
    results = []
    for i, (idx, dead) in enumerate(outs):
        c = counts[i][:, idx].astype(float)                       # (S, cells)
        if c.shape[1]:
            c[:, dead[idx]] = 0.0                                 # lesioned cells are silent
        if measure == "rate":
            per_stim = c.mean(1) * 1000.0 / ticks if len(idx) else np.zeros(len(stimuli))
        else:
            per_stim = (c > 0).mean(1) if len(idx) else np.zeros(len(stimuli))
        results.append(per_stim[::-1] if reverse else per_stim)
    return results


def validate_module(module, assays: Sequence[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Runs the given assays, or those stored in `module.validation["assays"]`."""
    assays = assays if assays is not None else module.validation.get("assays", [])
    return [run_assay(module, a) for a in assays]
