"""Shareable modules: save / load, and composition of modules into a larger nervous system."""
import numpy as np

from neurogenesis.development import region_of
from neurogenesis.modules import Module, compose

from test_development import fp, sheet_plan, toy_genome


def toy_module(name="toy"):
    return Module(name=name, plan=sheet_plan(), genome=toy_genome(), inputs=["sheet"], outputs=["out"],
                  description="toy sheet -> map -> output", validation=dict(metric="none"), provenance=dict(author="test"))


def test_module_save_load_grows_the_same_network(tmp_path):
    m = toy_module()
    m.save(tmp_path / "m.json")
    m2 = Module.load(tmp_path / "m.json")
    assert fp(m2.grow(4)) == fp(m.grow(4)) and m2.inputs == ["sheet"] and m2.provenance["author"] == "test"


def test_composition_prefixes_regions_keeps_genes_and_links():
    a, b = toy_module("A"), toy_module("B")
    b.genome["count"]["map"] = 30
    b.genome["w_clip"] = 300
    link = dict(B=np.eye(3), c=np.zeros(3), sigma=0.4, p0=0.5, w=50.0)
    c = compose("AB", {"left": a, "right": b}, links=[("left.out", "right.map", link)], offsets={"right": (100, 0, 0)})
    assert c.inputs == ["left.sheet", "right.sheet"] and c.outputs == ["left.out", "right.out"]
    net = c.grow(0)
    p = c.plan
    assert len(region_of(net, p, "left.map")) == 60 and len(region_of(net, p, "right.map")) == 30
    assert len(region_of(net, p, "right.sheet")) == 64                                  # the module's own receptor gene
    lo, rm = set(region_of(net, p, "left.out").tolist()), set(region_of(net, p, "right.map").tolist())
    assert any(s.pre in lo and s.post in rm for s in net.synapses)
    rmap = set(region_of(net, p, "right.map").tolist()) | set(region_of(net, p, "right.inter").tolist())
    assert max(abs(s.weight) for s in net.synapses if s.pre in rmap and s.post in rmap) <= 300   # B's own weight clip
    assert min(net.neurons[i].x for i in region_of(net, p, "right.map")) >= 100
