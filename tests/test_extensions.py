"""Extension points: placement and weight rules, exact topography, mosaics, sign-inverting receptors, knockouts, tonic
currents, and plugins that travel with a plan or module."""
import sys
from pathlib import Path

import numpy as np

from neurogenesis.analysis import nearest_neighbour_regularity
from neurogenesis.development import BodyPlan, grow, knockout, region_of, tonic_current
from neurogenesis.modules import Module

from test_development import fp, sheet_plan, toy_genome

sys.path.insert(0, str(Path(__file__).parent / "plugins"))


def _uv(net, plan, region):
    r = plan.region(region)
    return np.asarray([[(net.neurons[i].x - r.origin[0]) / r.size[0], (net.neurons[i].y - r.origin[1]) / r.size[1]]
                       for i in region_of(net, plan, region)])


def test_new_rules_are_inactive_without_their_genes():
    p, g = sheet_plan(), toy_genome()
    old = BodyPlan(p.name, p.regions, p.projections, rules=dict(shift=("identity_offset",), target=("lamina",),
                                                                 probability=("identity_expression", "no_autapse", "source_sign")))
    assert fp(grow(p, g, 9)) == fp(grow(old, g, 9))


def test_topographic_rule_maps_point_to_point():
    p, g = sheet_plan(), toy_genome()
    g["guidance"][("sheet", "map")].update(topographic=[1, 1, 0], sigma=0.08, p0=1.0)
    net = grow(p, g, 1, regions=["sheet", "map"], projections=[("sheet", "map")])
    pos = {i: np.asarray([net.neurons[i].x, net.neurons[i].y]) for i in range(net.num_neurons)}
    err = [np.abs(pos[s.pre] / 10 - (pos[s.post] - [20, 0]) / 20).max() for s in net.synapses]
    assert net.synapses and np.mean(err) < 0.15


def test_mosaic_makes_regular_spacing():
    p, g = sheet_plan(), toy_genome()
    g["migration"]["map"]["spread"] = 0.6
    rand = nearest_neighbour_regularity(_uv(grow(p, g, 3), p, "map"))
    g["mosaic"] = dict(map=dict(spacing=0.12, iters=40))
    reg = nearest_neighbour_regularity(_uv(grow(p, g, 3), p, "map"))
    assert reg > rand + 1.0


def test_sign_inverting_receptor():
    p, g = sheet_plan(), toy_genome()
    g["guidance"][("sheet", "map")]["receptor"] = "inverting"
    net = grow(p, g, 0, regions=["sheet", "map"], projections=[("sheet", "map")])
    assert net.synapses and all(s.weight < 0 for s in net.synapses)            # excitatory receptors, inhibitory effect


def test_knockout_removes_regions_and_projections_and_keeps_the_rest():
    p, g = sheet_plan(), toy_genome()
    wt = grow(p, g, 4)
    k = grow(p, knockout(g, regions=["inter"]), 4)
    assert len(region_of(k, p, "inter")) == 0 and len(region_of(k, p, "map")) == len(region_of(wt, p, "map"))
    k2 = grow(p, knockout(g, projections=[("map", "out")]), 4)
    out = set(region_of(k2, p, "out").tolist())
    assert not any(s.post in out for s in k2.synapses) and "knockout" not in g


def test_tonic_current():
    p, g = sheet_plan(), toy_genome()
    g["tonic"] = dict(map=35)
    net = grow(p, g, 0)
    t = tonic_current(net, p, g)
    assert set(t[region_of(net, p, "map")].tolist()) == {35} and t.sum() == 35 * len(region_of(net, p, "map"))


def test_plugin_rules_travel_with_a_module(tmp_path):
    p, g = sheet_plan(), toy_genome()
    p.plugins = ["demo_rules"]
    p.rules = dict(p.rules, weight=p.rules["weight"] + ("halve",))
    p.__post_init__()
    g["guidance"][("sheet", "map")]["halve"] = True
    m = Module("halved", p, g, inputs=["sheet"], outputs=["out"])
    m.save(tmp_path / "m.json")
    m2 = Module.load(tmp_path / "m.json")
    assert m2.plan.plugins == ["demo_rules"] and fp(m2.grow(2)) == fp(m.grow(2))
    sub = dict(regions=["sheet", "map"], projections=[("sheet", "map")])
    w_half = [s.weight for s in m.grow(2, **sub).synapses]
    w_full = [s.weight for s in grow(sheet_plan(), toy_genome(), 2, **sub).synapses]
    assert len(w_half) == len(w_full) and all(abs(2 * a - b) <= 1 for a, b in zip(w_half, w_full))


def test_composition_merges_plugins_rules_and_region_genes():
    from neurogenesis.modules import compose
    p, g = sheet_plan(), toy_genome()
    p.plugins = ["demo_rules"]
    p.rules = dict(p.rules, weight=p.rules["weight"] + ("halve",))
    g["tonic"] = dict(map=20)
    a = Module("A", p, g, inputs=["sheet"], outputs=["out"])
    b = Module("B", sheet_plan(), toy_genome(), inputs=["sheet"], outputs=["out"])
    c = compose("AB", {"a": a, "b": b})
    assert c.plan.plugins == ["demo_rules"] and "halve" in c.plan.rules["weight"]
    net = c.grow(0)
    t = tonic_current(net, c.plan, c.genome)
    assert set(t[region_of(net, c.plan, "a.map")].tolist()) == {20} and t[region_of(net, c.plan, "b.map")].sum() == 0
