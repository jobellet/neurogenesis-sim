from __future__ import annotations
import numpy as np
import weakref
from neurogenesis.development.plan import BodyPlan
from neurogenesis.stages.base import Stage, STAGE_REGISTRY, register_stage
from neurogenesis.development.grow import DEFAULT_EXCITABILITY
from neurogenesis.development.differentiation import differentiate, identities, sigmoid
from neurogenesis.development.rules import RULES, GuidanceContext, PlacementContext, WeightContext
import neurogenesis.tissue as nt
from neurogenesis.params import Const, Expr

# Use a cache to store plans by ID so stages can retrieve them without dynamic class generation
_PLAN_CACHE = {}

@register_stage("legacy_placement")
class LegacyPlacement:
    def __call__(self, tissue, params, genome, fields, rng):
        if not hasattr(tissue, '_legacy_local'):
            tissue._legacy_local = {}
            tissue._legacy_kind = {}
            tissue._legacy_start = {}
            tissue._legacy_cells = {}
            tissue._legacy_ident = {}
            
        plan = _PLAN_CACHE[int(params["plan_id"].value)]
        c = params["region"].formula
        
        reg = plan.region(c)
        if reg.grown:
            n = int(np.clip(round(genome["count"][c]), *reg.count_bounds))
            m = genome["migration"][c]
            local_pos = np.clip(m["mean"] + m["spread"] * rng.standard_normal((n, 3)), 0.0, 1.0)
            ctx = PlacementContext(c, local_pos, genome)
            for r in plan.rules.get("placement", ()):
                RULES["placement"][r](ctx)
            local_pos = ctx.pos
            ih = genome["inhibitory"][c]
            k = rng.random(n) < sigmoid(ih["a0"] + local_pos @ ih["a"])
        else:
            local_pos = reg.placement.place(genome, rng)
            k = np.zeros(len(local_pos), bool)
        if reg.sign == "inh":
            k[:] = True
        if reg.sign == "exc":
            k[:] = False
            
        tissue._legacy_local[c] = local_pos
        tissue._legacy_kind[c] = k
        return tissue

@register_stage("legacy_differentiation")
class LegacyDifferentiation:
    def __call__(self, tissue, params, genome, fields, rng):
        plan = _PLAN_CACHE[int(params["plan_id"].value)]
        c = params["region"].formula
        
        dg = genome.get("differentiation", {}).get(c)
        if dg is not None and plan.region(c).grown:
            ex = genome.get("excitability", {}).get(c, DEFAULT_EXCITABILITY)
            tissue._legacy_cells[c] = differentiate(dg, tissue._legacy_local[c], ex["shift_v"], ex["shift_s"], rng)
        return tissue

@register_stage("legacy_identity")
class LegacyIdentity:
    def __call__(self, tissue, params, genome, fields, rng):
        plan = _PLAN_CACHE[int(params["plan_id"].value)]
        c = params["region"].formula
        
        def _identity_code(genome, region):
            return genome.get("identity", {}).get(region) or genome.get("types", {}).get(region)
        
        code = _identity_code(genome, c)
        if code is not None:
            tissue._legacy_ident[c] = identities(code, tissue._legacy_local[c])
        return tissue

@register_stage("legacy_neuron_creation")
class LegacyNeuronCreation:
    def __call__(self, tissue, params, genome, fields, rng):
        plan = _PLAN_CACHE[int(params["plan_id"].value)]
        c = params["region"].formula
        
        local_pos = tissue._legacy_local[c]
        kind = tissue._legacy_kind[c]
        cells = tissue._legacy_cells.get(c)
        
        reg = plan.region(c)
        ex = genome.get("excitability", {}).get(c, DEFAULT_EXCITABILITY)
        
        n = len(local_pos)
        absolute = np.asarray(reg.origin) + np.asarray(reg.size) * local_pos
        
        shift_v = np.full(n, int(np.clip(round(ex["shift_v"]), 1, 10)), dtype=np.int32)
        shift_s = np.full(n, int(np.clip(round(ex["shift_s"]), 1, 10)), dtype=np.int32)
        mode = np.zeros(n, dtype=np.int32)
        burst_period = np.full(n, 200, dtype=np.int32)
        burst_duty = np.full(n, 24, dtype=np.int32)
        threshold = np.full(n, 1024, dtype=np.int32)
        
        if cells is not None:
            threshold = cells["threshold"].astype(np.int32)
            shift_v = cells["shift_v"].astype(np.int32)
            shift_s = cells["shift_s"].astype(np.int32)
            pacemaker = cells["pacemaker"]
            mode[pacemaker] = 2
            burst_period[pacemaker] = cells["period"][pacemaker]
            burst_duty[pacemaker] = cells["duty"][pacemaker]
            
        sign_arr = np.where(kind, -1, 1).astype(np.int8)
        
        tissue._legacy_start[c] = len(tissue.alive)
        
        tissue.add_cells(
            n,
            positions=absolute,
            compartment=np.full(n, plan.ids[c], dtype=np.int32),
            shift_v=shift_v,
            shift_s=shift_s,
            mode=mode,
            burst_period=burst_period,
            burst_duty=burst_duty,
            threshold=threshold,
            sign=sign_arr,
            refractory=np.full(n, reg.refractory, dtype=np.int32),
            role=np.full(n, reg.role, dtype=np.int32),
            base_weight=np.ones(n, dtype=np.int32)
        )
        return tissue

@register_stage("legacy_projection")
class LegacyProjection:
    def __call__(self, tissue, params, genome, fields, rng):
        plan = _PLAN_CACHE[int(params["plan_id"].value)]
        src = params["src"].formula
        dst = params["dst"].formula
        
        if src not in tissue._legacy_local or dst not in tissue._legacy_local:
            return tissue
            
        local_src = tissue._legacy_local[src]
        local_dst = tissue._legacy_local[dst]
        kind_src = tissue._legacy_kind[src]
        ident_src = tissue._legacy_ident.get(src)
        
        gd = genome["guidance"][(src, dst)]
        ctx = GuidanceContext(src, dst, local_src, local_dst, kind_src, ident_src, gd)
        ctx.shift = np.asarray(gd["c"])
        for r in plan.rules.get("shift", ()):
            RULES["shift"][r](ctx)
        ctx.target = sigmoid(4.0 * (local_src - 0.5) @ np.asarray(gd["B"]).T + ctx.shift)
        for r in plan.rules.get("target", ()):
            RULES["target"][r](ctx)
        d2 = ((local_dst[None, :, :] - ctx.target[:, None, :]) ** 2).sum(-1)
        ctx.p = gd["p0"] * np.exp(-d2 / (2 * gd["sigma"] ** 2))
        for r in plan.rules.get("probability", ()):
            RULES["probability"][r](ctx)
        pre_idx, post_idx = np.nonzero(rng.random(ctx.p.shape) < ctx.p)
        wc = int(gd.get("wc", genome.get("w_clip", 512)))
        inh = gd.get("inh", genome.get("inh_weight_factor"))
        ws = np.asarray([gd["w"] * (-inh if kind_src[i] else 1.0) * (0.9 + 0.2 * rng.random()) for i in pre_idx], float)
        wctx = WeightContext(src, dst, pre_idx, post_idx, ws, gd)
        for r in plan.rules.get("weight", ()):
            RULES["weight"][r](wctx)
            
        start_src = tissue._legacy_start[src]
        start_dst = tissue._legacy_start[dst]
        
        new_pre = []
        new_post = []
        new_weight = []
        new_delay = []
        
        for i, j, w in zip(pre_idx, post_idx, wctx.w):
            abs_src = np.asarray(plan.region(src).origin) + np.asarray(plan.region(src).size) * local_src[i]
            abs_dst = np.asarray(plan.region(dst).origin) + np.asarray(plan.region(dst).size) * local_dst[j]
            d = np.linalg.norm(abs_src - abs_dst)
            new_pre.append(int(start_src + i))
            new_post.append(int(start_dst + j))
            new_weight.append(int(np.clip(round(w), -wc, wc)))
            new_delay.append(int(np.clip(round(d / plan.conduction_velocity), 1, plan.max_delay)))
            
        if not hasattr(tissue, "_legacy_pre"):
            tissue._legacy_pre = []
            tissue._legacy_post = []
            tissue._legacy_weight = []
            tissue._legacy_delay = []
            
        tissue._legacy_pre.extend(new_pre)
        tissue._legacy_post.extend(new_post)
        tissue._legacy_weight.extend(new_weight)
        tissue._legacy_delay.extend(new_delay)
        
        return tissue

@register_stage("legacy_finalize")
class LegacyFinalize:
    def __call__(self, tissue, params, genome, fields, rng):
        if hasattr(tissue, "_legacy_pre"):
            tissue.connectivity = nt.SparseConnectivity(
                pre=np.array(tissue._legacy_pre, dtype=np.int32),
                post=np.array(tissue._legacy_post, dtype=np.int32),
                weight=np.array(tissue._legacy_weight, dtype=np.int32),
                delay=np.array(tissue._legacy_delay, dtype=np.int32)
            )
        
        for attr in ['_legacy_local', '_legacy_kind', '_legacy_start', '_legacy_cells', '_legacy_ident', '_legacy_pre', '_legacy_post', '_legacy_weight', '_legacy_delay']:
            if hasattr(tissue, attr):
                delattr(tissue, attr)
        return tissue


def compile_plan_to_schedule(plan: BodyPlan, genome: dict) -> list[Stage]:
    schedule = []
    
    plan_id = id(plan)
    _PLAN_CACHE[plan_id] = plan
    
    comps = [r.name for r in plan.regions]
    projections = plan.projections
    
    ko = genome.get("knockout", {})
    if ko:
        comps = [c for c in comps if c not in set(ko.get("regions", ()))]
        gone = {tuple(p) for p in ko.get("projections", ())}
        projections = [p for p in projections if p not in gone]
        
    for c in comps:
        schedule.append(Stage(
            name=f"placement_{c}",
            operator="legacy_placement",
            params={"plan_id": Const(float(plan_id)), "region": Expr(c)}
        ))
        
    for c in comps:
        schedule.append(Stage(
            name=f"differentiation_{c}",
            operator="legacy_differentiation",
            params={"plan_id": Const(float(plan_id)), "region": Expr(c)}
        ))
        
    for c in comps:
        schedule.append(Stage(
            name=f"identity_{c}",
            operator="legacy_identity",
            params={"plan_id": Const(float(plan_id)), "region": Expr(c)}
        ))
        
    for c in comps:
        schedule.append(Stage(
            name=f"neuron_creation_{c}",
            operator="legacy_neuron_creation",
            params={"plan_id": Const(float(plan_id)), "region": Expr(c)}
        ))
        
    for (src, dst) in projections:
        schedule.append(Stage(
            name=f"projection_{src}_{dst}",
            operator="legacy_projection",
            params={"plan_id": Const(float(plan_id)), "src": Expr(src), "dst": Expr(dst)}
        ))
        
    schedule.append(Stage(
        name="finalize",
        operator="legacy_finalize",
        params={"plan_id": Const(float(plan_id))}
    ))
    
    return schedule
