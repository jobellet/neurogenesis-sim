"""Development: plans, placement, signs, differentiation, identities, guidance rules, determinism, JSON, parallel growth."""
import numpy as np
import pytest

from neurogenesis.development import (BodyPlan, Count, FixedPlacement, Region, grow, grow_many, neutral_differentiation,
                                      neutral_identity, neutral_typed_guidance, region_of, register, set_workers)


def sheet_plan():
    """A 4 x 4 sensor sheet (2 receptor channels, a genetic number of receptors per site), a grown map, 2 output pools."""
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


def test_growth_is_deterministic_and_seed_dependent():
    p, g = sheet_plan(), toy_genome()
    assert fp(grow(p, g, 3)) == fp(grow(p, g, 3))
    assert fp(grow(p, g, 3)) != fp(grow(p, g, 4))


def test_placement_counts_roles_and_signs():
    p, g = sheet_plan(), toy_genome()
    net = grow(p, g, 0)
    assert len(region_of(net, p, "sheet")) == 32 * 2 and len(region_of(net, p, "map")) == 60 and len(region_of(net, p, "out")) == 2
    assert all(net.neurons[i].role == 1 for i in region_of(net, p, "sheet")) and all(net.neurons[i].role == 2 for i in region_of(net, p, "out"))
    assert all(net.neurons[i].base_weight < 0 for i in region_of(net, p, "inter"))
    g["receptors"] = 9                                                  # clipped to the Count bounds (1..4)
    assert len(region_of(grow(p, g, 0), p, "sheet")) == 32 * 4
    del g["receptors"]                                                  # missing gene: the Count default (1)
    assert len(region_of(grow(p, g, 0), p, "sheet")) == 32


def test_projections_must_be_in_the_plan_and_subsets_grow():
    p, g = sheet_plan(), toy_genome()
    with pytest.raises(AssertionError):
        grow(p, g, 0, projections=[("out", "sheet")])
    net = grow(p, g, 0, regions=["sheet", "map"], projections=[("sheet", "map")])
    assert net.num_neurons == 64 + 60 and all(net.neurons[s.post].compartment == p.ids["map"] for s in net.synapses)


def test_topographic_guidance_preserves_position():
    p, g = sheet_plan(), toy_genome()
    g["guidance"][("sheet", "map")].update(B=np.diag([2.0, 2.0, 0.0]), sigma=0.1, p0=0.9)
    net = grow(p, g, 1, regions=["sheet", "map"], projections=[("sheet", "map")])
    pos = np.asarray([[n.x, n.y] for n in net.neurons])
    pre, post = np.asarray([(s.pre, s.post) for s in net.synapses]).T
    src = (pos[pre] - [0, 0]) / 10
    dst = (pos[post] - [20, 0]) / 20
    assert np.corrcoef(src[:, 0], dst[:, 0])[0, 1] > 0.8 and np.corrcoef(src[:, 1], dst[:, 1])[0, 1] > 0.8


def test_guidance_rules_source_sign_lamina_and_identity():
    p, g = sheet_plan(), toy_genome()
    g["guidance"][("map", "map")]["source"] = "inh"
    net = grow(p, g, 2)
    m = set(region_of(net, p, "map").tolist())
    mm = [s for s in net.synapses if s.pre in m and s.post in m]
    assert mm and all(net.neurons[s.pre].base_weight < 0 for s in mm)
    g = toy_genome()
    g["guidance"][("sheet", "map")].update(lamina=[0.1, 0.9], sigma=0.08, p0=1.0)       # channel 0 -> w 0.1, channel 1 -> w 0.9
    net = grow(p, g, 2, regions=["sheet", "map"], projections=[("sheet", "map")])
    zs = {0: [], 1: []}
    for s in net.synapses:
        zs[int(round(net.neurons[s.pre].z / 10))].append((net.neurons[s.post].z - 0) / 20)
    assert np.mean(zs[0]) < 0.35 and np.mean(zs[1]) > 0.65
    g = toy_genome()
    g["identity"] = dict(map=neutral_identity())
    g["guidance"][("map", "out")] = neutral_typed_guidance(g["guidance"][("map", "out")])
    assert fp(grow(p, g, 5)) == fp(grow(p, toy_genome(), 5))                          # neutral identities: no effect
    g["identity"]["map"]["logits"][1] = [0.0, 8.0, 0.0, 0.0]                          # identity 1 where u > 0
    g["guidance"][("map", "out")]["type_s"][0] = 0.0                                  # identity 0 does not project
    net = grow(p, g, 5)
    mp = region_of(net, p, "map")
    us = {i: (net.neurons[i].x - 20) / 20 for i in mp}
    pre = [s.pre for s in net.synapses if s.pre in us and net.neurons[s.post].compartment == p.ids["out"]]
    assert pre and min(us[i] for i in pre) >= 0.0


def test_differentiation_sets_neuron_properties():
    p, g = sheet_plan(), toy_genome()
    dg = neutral_differentiation()
    g["differentiation"] = dict(map=dg)
    assert all(net_n.threshold == 1024 for net_n in grow(p, g, 0).neurons)
    dg.update(theta0=0.5, pace=dict(b0=8.0, c=0.0, r=0.2), period=60.0)
    net = grow(p, g, 0)
    th = [net.neurons[i].threshold for i in region_of(net, p, "map")]
    assert min(th) > 1024 and all(net.neurons[i].mode == 2 for i in region_of(net, p, "map"))


def test_custom_rule_can_be_registered():
    @register("probability", "only_first_half")
    def only_first_half(ctx):
        ctx.p = ctx.p * (np.arange(len(ctx.p)) < len(ctx.p) // 2)[:, None]
    p, g = sheet_plan(), toy_genome()
    p.rules = dict(p.rules, probability=p.rules["probability"] + ("only_first_half",))
    net = grow(p, g, 0, regions=["sheet", "map"], projections=[("sheet", "map")])
    assert max(s.pre for s in net.synapses) < 32


def test_plan_json_round_trip(tmp_path):
    p, g = sheet_plan(), toy_genome()
    p.save(tmp_path / "plan.json")
    q = BodyPlan.load(tmp_path / "plan.json")
    assert fp(grow(q, g, 7)) == fp(grow(p, g, 7))


def test_parallel_growth_equals_serial():
    p, g = sheet_plan(), toy_genome()
    calls = [dict(plan=p, genome=g, seed=s) for s in range(4)]
    serial = [fp(n) for n in grow_many(calls)]
    set_workers(2)
    try:
        parallel = [fp(n) for n in grow_many(calls)]
    finally:
        set_workers(0)
    assert serial == parallel
