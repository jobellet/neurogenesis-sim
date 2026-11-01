import numpy as np
from neurogenesis.development.legacy_compiler import compile_plan_to_schedule
from neurogenesis.tissue import Tissue
from neurogenesis.development.plan import BodyPlan, Count, FixedPlacement, Region
from neurogenesis.development.grow import grow, knockout

def sheet_plan():
    labels = [[(i + 0.5) / 4, (j + 0.5) / 4, ch] for i in range(4) for j in range(4) for ch in (0.0, 1.0)]
    return BodyPlan(
        name="toy", regions=[
            Region("sheet", (0, 0, 0), (10, 10, 10), FixedPlacement(labels, counts=[Count(1, ("receptors",), 1, 4)] * len(labels),
                                                                    jitter=dict(kind="normal", sd=0.01, axes=(1, 1, 0))), role=1),
            Region("map", (20, 0, 0), (20, 20, 20)),
            Region("inter", (20, 30, 0), (10, 10, 10), sign="inh"),
            Region("out", (50, 0, 0), (5, 10, 10), FixedPlacement([[0.5, 0.25, 0.5], [0.5, 0.75, 0.5]]), role=2)],
        projections=[("sheet", "map"), ("map", "map"), ("map", "inter"), ("inter", "map"), ("map", "out")])

def toy_genome():
    g = dict(count=dict(map=60, inter=10), receptors=2, inh_weight_factor=2.0,
             migration=dict(map=dict(mean=np.full(3, 0.5), spread=0.3), inter=dict(mean=np.full(3, 0.5), spread=0.3)),
             inhibitory=dict(map=dict(a0=-1.4, a=np.zeros(3)), inter=dict(a0=0.0, a=np.zeros(3))),
             excitability=dict(map=dict(shift_v=5, shift_s=4)))
    g["guidance"] = {p: dict(B=np.eye(3), c=np.zeros(3), sigma=0.3, p0=0.5, w=100.0) for p in sheet_plan().projections}
    return g

def fp(net):
    return [(n.x, n.y, n.z, n.base_weight, n.threshold, n.shift_v, n.mode) for n in net.neurons], [(s.pre, s.post, s.weight, s.delay) for s in net.synapses]

def run_legacy_schedule(schedule, genome, seed, legacy_stream=True):
    assert legacy_stream, "Only legacy_stream=True is supported in this test runner"
    rng = np.random.default_rng(seed)
    tissue = Tissue.empty()
    for stage in schedule:
        tissue = stage.run(tissue, genome, {}, rng)
    return tissue

def test_legacy_compiler_equivalence():
    p, g = sheet_plan(), toy_genome()
    
    net_grow = grow(p, g, seed=42)
    
    schedule = compile_plan_to_schedule(p, g)
    tissue = run_legacy_schedule(schedule, g, seed=42, legacy_stream=True)
    net_compiler = tissue.to_network()
    
    assert fp(net_grow) == fp(net_compiler), "Fingerprints do not match!"

def test_legacy_compiler_equivalence_different_seed():
    p, g = sheet_plan(), toy_genome()
    
    net_grow = grow(p, g, seed=123)
    
    schedule = compile_plan_to_schedule(p, g)
    tissue = run_legacy_schedule(schedule, g, seed=123, legacy_stream=True)
    net_compiler = tissue.to_network()
    
    assert fp(net_grow) == fp(net_compiler), "Fingerprints do not match!"

def test_legacy_compiler_with_knockout():
    p, g = sheet_plan(), toy_genome()
    g_ko = knockout(g, regions=["map"])
    
    net_grow = grow(p, g_ko, seed=7)
    
    schedule = compile_plan_to_schedule(p, g_ko)
    tissue = run_legacy_schedule(schedule, g_ko, seed=7, legacy_stream=True)
    net_compiler = tissue.to_network()
    
    assert fp(net_grow) == fp(net_compiler), "Fingerprints do not match with knockout!"
