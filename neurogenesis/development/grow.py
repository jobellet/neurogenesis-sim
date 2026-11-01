"""Development of a spiking network from a body plan and a genome.

Steps, in a fixed order (the random generator, seeded by the development seed, is consumed in this order):
1. placement, region by region: fixed labels (with genetic repeats and jitter) or migration of a genetic number of
   neurons; for grown regions, each neuron's sign (Dale's principle) from a genetic position-dependent probability;
2. differentiation (grown regions with genome["differentiation"][region]): per-neuron threshold, time constants and
   pacemaker identity by lateral inhibition;
3. molecular identity (regions with genome["identity"][region], legacy key "types"): deterministic, from position;
4. axon growth, projection by projection: guidance (neurogenesis.development.rules) gives each pair a connection
   probability; synapses get the projection's weight (x -inh_weight_factor for inhibitory neurons, +-10 % jitter, clipped)
   and a delay from the distance (conduction velocity).

Genome keys used (all optional except those of the regions and projections actually grown):
  count[r], migration[r] = {mean (3,), spread}, inhibitory[r] = {a0, a (3,)}, excitability[r] = {shift_v, shift_s},
  differentiation[r], identity[r] (or types[r]), guidance[(src, dst)] = {B (3x3), c (3,), sigma, p0, w, ...},
  inh_weight_factor (per projection "inh"), w_clip (default 512; per projection "wc").
"""
from __future__ import annotations

import numpy as np

from ..spiking.network import NeuronData, SNNNetwork, SynapseData
from .differentiation import differentiate, identities, sigmoid
from .plan import BodyPlan
from .rules import RULES, GuidanceContext, PlacementContext, WeightContext

DEFAULT_EXCITABILITY = dict(shift_v=5, shift_s=4)


def _identity_code(genome, region):
    return genome.get("identity", {}).get(region) or genome.get("types", {}).get(region)


def grow(plan: BodyPlan, genome: dict, seed: int = 0, regions=None, projections=None, name: str | None = None) -> SNNNetwork:
    """Develop one individual. regions / projections: a subset of the plan (default: all, in plan order)."""
    rng = np.random.default_rng(seed)
    comps = list(regions) if regions is not None else [r.name for r in plan.regions]
    projections = [tuple(p) for p in projections] if projections is not None else plan.projections
    allowed = set(plan.projections)
    assert set(projections) <= allowed, "only projections listed in the plan may grow"
    ko = genome.get("knockout", {})                                       # virtual knockouts (neurogenesis.development.knockout)
    if ko:
        comps = [c for c in comps if c not in set(ko.get("regions", ()))]
        gone = {tuple(p) for p in ko.get("projections", ())}
        projections = [p for p in projections if p not in gone]
    local, kind = {}, {}
    for c in comps:                                                       # 1. placement and sign
        reg = plan.region(c)
        if reg.grown:
            n = int(np.clip(round(genome["count"][c]), *reg.count_bounds))
            m = genome["migration"][c]
            local[c] = np.clip(m["mean"] + m["spread"] * rng.standard_normal((n, 3)), 0.0, 1.0)
            ctx = PlacementContext(c, local[c], genome)
            for r in plan.rules.get("placement", ()):
                RULES["placement"][r](ctx)
            local[c] = ctx.pos
            ih = genome["inhibitory"][c]
            kind[c] = rng.random(n) < sigmoid(ih["a0"] + local[c] @ ih["a"])
        else:
            local[c] = reg.placement.place(genome, rng)
            kind[c] = np.zeros(len(local[c]), bool)
        if reg.sign == "inh":
            kind[c][:] = True
        if reg.sign == "exc":
            kind[c][:] = False
    cells = {}                                                            # 2. differentiation
    for c in comps:
        dg = genome.get("differentiation", {}).get(c)
        if dg is not None and plan.region(c).grown:
            ex = genome.get("excitability", {}).get(c, DEFAULT_EXCITABILITY)
            cells[c] = differentiate(dg, local[c], ex["shift_v"], ex["shift_s"], rng)
    ident = {}                                                            # 3. molecular identity
    for c in comps:
        code = _identity_code(genome, c)
        if code is not None:
            ident[c] = identities(code, local[c])
    start, k = {}, 0
    for c in comps:
        start[c] = k
        k += len(local[c])
    absolute = {c: np.asarray(plan.region(c).origin) + np.asarray(plan.region(c).size) * local[c] for c in comps}
    neurons = []
    for c in comps:
        reg = plan.region(c)
        ex = genome.get("excitability", {}).get(c, DEFAULT_EXCITABILITY)
        for i in range(len(local[c])):
            x, y, z = absolute[c][i]
            nd = NeuronData(id=len(neurons), x=float(x), y=float(y), z=float(z), dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0,
                            shift_v=int(np.clip(round(ex["shift_v"]), 1, 10)), shift_s=int(np.clip(round(ex["shift_s"]), 1, 10)),
                            base_weight=-1 if kind[c][i] else 1, conn_radius=0.0, conn_prob=0.0,
                            refractory=reg.refractory, role=reg.role, compartment=plan.ids[c])
            if c in cells:
                cl = cells[c]
                nd.threshold, nd.shift_v, nd.shift_s = int(cl["threshold"][i]), int(cl["shift_v"][i]), int(cl["shift_s"][i])
                if cl["pacemaker"][i]:
                    nd.mode, nd.burst_period, nd.burst_duty = 2, cl["period"], cl["duty"]
            neurons.append(nd)
    synapses = []                                                         # 4. axon growth
    for (src, dst) in projections:
        if src not in local or dst not in local:
            continue
        gd = genome["guidance"][(src, dst)]
        ctx = GuidanceContext(src, dst, local[src], local[dst], kind[src], ident.get(src), gd)
        ctx.shift = np.asarray(gd["c"])
        for r in plan.rules.get("shift", ()):
            RULES["shift"][r](ctx)
        ctx.target = sigmoid(4.0 * (local[src] - 0.5) @ np.asarray(gd["B"]).T + ctx.shift)
        for r in plan.rules.get("target", ()):
            RULES["target"][r](ctx)
        d2 = ((local[dst][None, :, :] - ctx.target[:, None, :]) ** 2).sum(-1)
        ctx.p = gd["p0"] * np.exp(-d2 / (2 * gd["sigma"] ** 2))
        for r in plan.rules.get("probability", ()):
            RULES["probability"][r](ctx)
        pre, post = np.nonzero(rng.random(ctx.p.shape) < ctx.p)
        wc = int(gd.get("wc", genome.get("w_clip", 512)))
        inh = gd.get("inh", genome.get("inh_weight_factor"))
        ws = np.asarray([gd["w"] * (-inh if kind[src][i] else 1.0) * (0.9 + 0.2 * rng.random()) for i in pre], float)
        wctx = WeightContext(src, dst, pre, post, ws, gd)
        for r in plan.rules.get("weight", ()):
            RULES["weight"][r](wctx)
        for i, j, w in zip(pre, post, wctx.w):
            d = np.linalg.norm(absolute[src][i] - absolute[dst][j])
            synapses.append(SynapseData(pre=int(start[src] + i), post=int(start[dst] + j), weight=int(np.clip(round(w), -wc, wc)),
                                        delay=int(np.clip(round(d / plan.conduction_velocity), 1, plan.max_delay))))
    return SNNNetwork(morphology=name or plan.name, neurons=neurons, synapses=synapses)


def region_of(net: SNNNetwork, plan: BodyPlan, region: str) -> np.ndarray:
    """Indices of the neurons of a region in a grown network."""
    cid = plan.ids[region]
    return np.asarray([i for i, n in enumerate(net.neurons) if n.compartment == cid], int)


def knockout(genome: dict, regions=(), projections=()) -> dict:
    """Copy of a genome with virtual knockouts: the listed regions never form, the listed projections never grow (their
    guidance receptor is deleted). Development of everything else uses the same random stream order, so a knockout is
    compared with its own wild type at the same development seed."""
    import copy
    g = copy.copy(genome)
    ko = dict(genome.get("knockout", {}))
    ko["regions"] = sorted(set(ko.get("regions", ())) | set(regions))
    ko["projections"] = sorted({tuple(p) for p in ko.get("projections", ())} | {tuple(p) for p in projections})
    g["knockout"] = ko
    return g


def tonic_current(net: SNNNetwork, plan: BodyPlan, genome: dict) -> np.ndarray:
    """Intrinsic standing current of each neuron (int32, per tick), from genome["tonic"][region] (default 0): for cells
    depolarised at rest by their own channels. Add it to the external current of every tick of a simulation."""
    out = np.zeros(net.num_neurons, np.int32)
    for c, v in genome.get("tonic", {}).items():
        if c in plan.ids:
            out[region_of(net, plan, c)] = int(round(v))
    return out
