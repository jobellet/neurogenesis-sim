from __future__ import annotations

from typing import Dict, Any, List, Optional
import numpy as np

from neurogenesis.development.plan import BodyPlan
from neurogenesis.stages.base import Stage, register_stage
from neurogenesis.development.grow import (
    step_placement_and_sign,
    step_differentiation,
    step_identity,
    step_create_neurons,
    step_axon_growth
)
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.params import Const

@register_stage("legacy_grow_stage")
class LegacyGrowStage:
    """Canonical stage that executes decomposed steps of legacy growth.
    
    All state is fully contained and serializable: takes plan data in params,
    updates Tissue directly without hidden global caches or private monkey-patched attributes.
    """
    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        plan_dict = params["plan"].value if hasattr(params["plan"], "value") else params["plan"]
        plan = BodyPlan.from_dict(plan_dict) if isinstance(plan_dict, dict) else plan_dict
        
        comps = [r.name for r in plan.regions]
        projections = plan.projections
        
        ko = genome.get("knockout", {})
        if ko:
            comps = [c for c in comps if c not in set(ko.get("regions", ()))]
            gone = {tuple(p) for p in ko.get("projections", ())}
            projections = [p for p in projections if p not in gone]

        # Call canonical steps from neurogenesis.development.grow
        local, kind = step_placement_and_sign(plan, comps, genome, rng)
        cells = step_differentiation(plan, comps, local, genome, rng)
        ident = step_identity(plan, comps, local, genome)
        neurons, start, absolute = step_create_neurons(plan, comps, local, kind, cells, genome)
        synapses = step_axon_growth(plan, projections, local, kind, ident, start, absolute, genome, rng)

        # Assemble into Tissue with float64 precision
        N = len(neurons)
        if N == 0:
            return Tissue.empty()

        positions = np.array([[n.x, n.y, n.z] for n in neurons], dtype=np.float64)
        directions = np.array([[n.dir_x, n.dir_y, n.dir_z] for n in neurons], dtype=np.float32)
        mode = np.array([n.mode for n in neurons], dtype=np.int32)
        shift_v = np.array([n.shift_v for n in neurons], dtype=np.int32)
        shift_s = np.array([n.shift_s for n in neurons], dtype=np.int32)
        base_weight = np.array([n.base_weight for n in neurons], dtype=np.int32)
        conn_radius = np.array([n.conn_radius for n in neurons], dtype=np.float32)
        conn_prob = np.array([n.conn_prob for n in neurons], dtype=np.float32)
        burst_period = np.array([n.burst_period for n in neurons], dtype=np.int32)
        burst_duty = np.array([n.burst_duty for n in neurons], dtype=np.int32)
        poisson_hz = np.array([n.poisson_hz for n in neurons], dtype=np.float64)
        refractory = np.array([n.refractory for n in neurons], dtype=np.int32)
        role = np.array([n.role for n in neurons], dtype=np.int32)
        compartment = np.array([n.compartment for n in neurons], dtype=np.int32)
        threshold = np.array([n.threshold for n in neurons], dtype=np.int32)
        sign = np.where(base_weight >= 0, np.ones(N, dtype=np.int8), np.full(N, -1, dtype=np.int8))

        t = Tissue.empty()
        t.add_cells(
            N,
            positions=positions,
            directions=directions,
            mode=mode,
            shift_v=shift_v,
            shift_s=shift_s,
            base_weight=base_weight,
            conn_radius=conn_radius,
            conn_prob=conn_prob,
            burst_period=burst_period,
            burst_duty=burst_duty,
            poisson_hz=poisson_hz,
            refractory=refractory,
            role=role,
            compartment=compartment,
            threshold=threshold,
            sign=sign
        )

        M = len(synapses)
        if M > 0:
            pre = np.array([s.pre for s in synapses], dtype=np.int32)
            post = np.array([s.post for s in synapses], dtype=np.int32)
            weight = np.array([s.weight for s in synapses], dtype=np.int32)
            delay = np.array([s.delay for s in synapses], dtype=np.int32)
            t.connectivity = SparseConnectivity(pre, post, weight, delay)

        return t


def compile_plan_to_schedule(plan: BodyPlan, genome: Optional[Dict[str, Any]] = None) -> List[Stage]:
    """Compiles a legacy BodyPlan into a schedule of declarative, serializable Stages.
    
    When executed via run_schedule(project, genome, seed, legacy_stream=True),
    reproduces development.grow() bit-for-bit with zero state duplication.
    """
    plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else plan
    stage = Stage(
        name="legacy_development",
        operator="legacy_grow_stage",
        params={"plan": Const(plan_dict)},
        repeat=1
    )
    return [stage]


def compile_plan_to_project(plan: BodyPlan, genome: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Wraps the compiled schedule into a complete, standard project dictionary."""
    schedule = compile_plan_to_schedule(plan, genome)
    return {
        "version": "1.0.0",
        "name": plan.name,
        "plugins": list(plan.plugins),
        "fields": {},
        "schedule": [
            {
                "name": s.name,
                "operator": s.operator,
                "params": {"plan": {"type": "Const", "value": s.params["plan"].value}},
                "repeat": s.repeat
            }
            for s in schedule
        ]
    }
