"""Development of a spiking network from a body plan and a genome.

Refactored into decomposed stage functions so that both legacy grow()
and the compiled schedule (A5) execute the exact same canonical implementations.
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from ..spiking.network import NeuronData, SNNNetwork, SynapseData
from .differentiation import differentiate, identities, sigmoid
from .plan import BodyPlan
from .rules import RULES, GuidanceContext, PlacementContext, WeightContext
from ..tissue import Tissue, SparseConnectivity

DEFAULT_EXCITABILITY = dict(shift_v=5, shift_s=4)


def _identity_code(genome, region):
    return genome.get("identity", {}).get(region) or genome.get("types", {}).get(region)


def step_placement_and_sign(
    plan: BodyPlan,
    comps: List[str],
    genome: dict,
    rng: np.random.Generator
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Step 1: Placement, region by region, and sign determination."""
    local: Dict[str, np.ndarray] = {}
    kind: Dict[str, np.ndarray] = {}
    for c in comps:
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
    return local, kind


def step_differentiation(
    plan: BodyPlan,
    comps: List[str],
    local: Dict[str, np.ndarray],
    genome: dict,
    rng: np.random.Generator
) -> Dict[str, Any]:
    """Step 2: Differentiation of cells in grown regions."""
    cells: Dict[str, Any] = {}
    for c in comps:
        dg = genome.get("differentiation", {}).get(c)
        if dg is not None and plan.region(c).grown:
            ex = genome.get("excitability", {}).get(c, DEFAULT_EXCITABILITY)
            cells[c] = differentiate(dg, local[c], ex["shift_v"], ex["shift_s"], rng)
    return cells


def step_identity(
    plan: BodyPlan,
    comps: List[str],
    local: Dict[str, np.ndarray],
    genome: dict
) -> Dict[str, np.ndarray]:
    """Step 3: Deterministic molecular identity."""
    ident: Dict[str, np.ndarray] = {}
    for c in comps:
        code = _identity_code(genome, c)
        if code is not None:
            ident[c] = identities(code, local[c])
    return ident


def step_create_neurons(
    plan: BodyPlan,
    comps: List[str],
    local: Dict[str, np.ndarray],
    kind: Dict[str, np.ndarray],
    cells: Dict[str, Any],
    genome: dict
) -> Tuple[List[NeuronData], Dict[str, int], Dict[str, np.ndarray]]:
    """Assemble NeuronData objects and calculate start offsets and absolute positions."""
    start: Dict[str, int] = {}
    k = 0
    for c in comps:
        start[c] = k
        k += len(local[c])
    absolute = {c: np.asarray(plan.region(c).origin) + np.asarray(plan.region(c).size) * local[c] for c in comps}
    
    neurons: List[NeuronData] = []
    for c in comps:
        reg = plan.region(c)
        ex = genome.get("excitability", {}).get(c, DEFAULT_EXCITABILITY)
        for i in range(len(local[c])):
            x, y, z = absolute[c][i]
            nd = NeuronData(
                id=len(neurons), x=float(x), y=float(y), z=float(z),
                dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0,
                shift_v=int(np.clip(round(ex["shift_v"]), 1, 10)),
                shift_s=int(np.clip(round(ex["shift_s"]), 1, 10)),
                base_weight=-1 if kind[c][i] else 1,
                conn_radius=0.0, conn_prob=0.0,
                refractory=reg.refractory, role=reg.role,
                compartment=plan.ids[c]
            )
            if c in cells:
                cl = cells[c]
                nd.threshold = int(cl["threshold"][i])
                nd.shift_v = int(cl["shift_v"][i])
                nd.shift_s = int(cl["shift_s"][i])
                if cl["pacemaker"][i]:
                    nd.mode, nd.burst_period, nd.burst_duty = 2, cl["period"], cl["duty"]
            neurons.append(nd)
    return neurons, start, absolute


def step_axon_growth(
    plan: BodyPlan,
    projections: List[Tuple[str, str]],
    local: Dict[str, np.ndarray],
    kind: Dict[str, np.ndarray],
    ident: Dict[str, np.ndarray],
    start: Dict[str, int],
    absolute: Dict[str, np.ndarray],
    genome: dict,
    rng: np.random.Generator
) -> List[SynapseData]:
    """Step 4: Axon growth and synaptogenesis."""
    synapses: List[SynapseData] = []
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
            synapses.append(SynapseData(
                pre=int(start[src] + i),
                post=int(start[dst] + j),
                weight=int(np.clip(round(w), -wc, wc)),
                delay=int(np.clip(round(d / plan.conduction_velocity), 1, plan.max_delay))
            ))
    return synapses


def grow(plan: BodyPlan, genome: dict, seed: int = 0, regions=None, projections=None, name: str | None = None) -> SNNNetwork:
    """Develop one individual. regions / projections: a subset of the plan (default: all, in plan order)."""
    rng = np.random.default_rng(seed)
    comps = list(regions) if regions is not None else [r.name for r in plan.regions]
    projections = [tuple(p) for p in projections] if projections is not None else plan.projections
    allowed = set(plan.projections)
    assert set(projections) <= allowed, "only projections listed in the plan may grow"
    
    ko = genome.get("knockout", {})
    if ko:
        comps = [c for c in comps if c not in set(ko.get("regions", ()))]
        gone = {tuple(p) for p in ko.get("projections", ())}
        projections = [p for p in projections if p not in gone]
        
    local, kind = step_placement_and_sign(plan, comps, genome, rng)
    cells = step_differentiation(plan, comps, local, genome, rng)
    ident = step_identity(plan, comps, local, genome)
    neurons, start, absolute = step_create_neurons(plan, comps, local, kind, cells, genome)
    synapses = step_axon_growth(plan, projections, local, kind, ident, start, absolute, genome, rng)
    
    return SNNNetwork(morphology=name or plan.name, neurons=neurons, synapses=synapses)


def region_of(net: SNNNetwork, plan: BodyPlan, region: str) -> np.ndarray:
    """Indices of the neurons of a region in a grown network."""
    cid = plan.ids[region]
    return np.asarray([i for i, n in enumerate(net.neurons) if n.compartment == cid], int)


def knockout(genome: dict, regions=(), projections=()) -> dict:
    """Copy of a genome with virtual knockouts: the listed regions never form, the listed projections never grow."""
    import copy
    g = copy.copy(genome)
    ko = dict(genome.get("knockout", {}))
    ko["regions"] = sorted(set(ko.get("regions", ())) | set(regions))
    ko["projections"] = sorted({tuple(p) for p in ko.get("projections", ())} | {tuple(p) for p in projections})
    g["knockout"] = ko
    return g


def tonic_current(net: SNNNetwork, plan: BodyPlan, genome: dict) -> np.ndarray:
    """Intrinsic standing current of each neuron (int32, per tick), from genome["tonic"][region] (default 0)."""
    out = np.zeros(net.num_neurons, np.int32)
    for c, v in genome.get("tonic", {}).items():
        if c in plan.ids:
            out[region_of(net, plan, c)] = int(round(v))
    return out
