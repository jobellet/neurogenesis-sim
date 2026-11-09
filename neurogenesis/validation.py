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

Structural assays: with `"target"` (or a readout `measure`) naming a registered target (`data.targets`) or any
fitting metric that needs no simulation (e.g. `reciprocity`, `simplex_count`, `triad_count`, `weight_stat`,
`arbor`), the value is that measure of each seed's grown tissue, with `options` passed to it, and is gated as above.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

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


def _structural_target(name) -> Optional[TargetSpec]:
    """The target spec of a structural (non-spiking) target or fitting metric `name`, else None."""
    if not name or name in MEASURES:
        return None
    try:
        spec = get_target(name)
    except KeyError:
        return None
    return None if spec.requires_spiking else spec


def run_assay(module, assay: Dict[str, Any]) -> Dict[str, Any]:
    """Runs one assay on a module. Returns dict(name, values per seed, passed per seed, pass_fraction, ok)."""
    genome = module.genome
    ko = assay.get("knockout")
    if ko:
        genome = knockout(genome, regions=ko.get("regions", ()), projections=[tuple(p) for p in ko.get("projections", ())])
    seeds = [int(s) for s in assay.get("seeds", HELD_OUT[:5])]

    readout = assay.get("readout", {})
    # Check if this assay specifies an objective target (a registered target or any fitting metric)
    target_name = assay.get("target") or readout.get("target") or readout.get("measure")
    target_spec = _structural_target(target_name)

    if target_spec is not None:
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
    from .spiking.batch import simulate_counts
    ticks, blank = int(assay.get("ticks", 100)), int(assay.get("blank", 0))
    stimuli: List[Dict[str, float]] = assay.get("stimuli") or [{}]
    measure = readout.get("measure", "rate")
    if measure not in MEASURES:
        raise ValueError(f"unknown readout measure {measure!r} (use {MEASURES})")
    nets, exts, outs = [], [], []
    for s in seeds:
        net = grow(module.plan, genome, s)
        base = tonic_current(net, module.plan, genome)
        ext = np.tile(base, (len(stimuli), 1)).astype(np.int32)
        for k, stim in enumerate(stimuli):
            for region, current in stim.items():
                if region in module.plan.ids:
                    ext[k, region_of(net, module.plan, region)] += int(round(current))
        nets.append(net)
        exts.append(ext)
        outs.append(region_of(net, module.plan, readout["region"]) if readout.get("region") in module.plan.ids else np.zeros(0, int))
    counts = simulate_counts(nets, exts, ticks=ticks, blank=blank, model=module.neuron_model)
    values = []
    for i, idx in enumerate(outs):
        c = counts[i][:, idx]                                     # (S, cells)
        if measure == "rate":
            per_stim = c.mean(1) * 1000.0 / ticks if len(idx) else np.zeros(len(stimuli))
        else:
            per_stim = (c > 0).mean(1) if len(idx) else np.zeros(len(stimuli))
        values.append(_metric(per_stim, assay.get("metric", "mean")))
    gate = assay.get("gate", {})
    passed = [_gate(v, gate) for v in values]
    frac = float(np.mean(passed))
    return dict(name=assay.get("name", "assay"), seeds=seeds, values=[round(v, 4) for v in values], passed=passed,
                pass_fraction=frac, ok=frac >= float(assay.get("pass_fraction", 1.0)))


def validate_module(module, assays: Sequence[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Runs the given assays, or those stored in `module.validation["assays"]`."""
    assays = assays if assays is not None else module.validation.get("assays", [])
    return [run_assay(module, a) for a in assays]
