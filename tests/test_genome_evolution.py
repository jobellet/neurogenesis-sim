"""Genes (paths into nested genomes and arrays), [0, 1] coding, JSON; island evolution and robust audits."""
import json

import numpy as np

from neurogenesis.evolution import audit, choose, evolve, robust_value, seeds_of
from neurogenesis.genome import (body_genes, differentiation_genes, from_json, from_unit, get_gene, guidance_genes, identity_genes,
                                 set_gene, to_json, to_unit, typed_guidance_genes)
from neurogenesis.development import neutral_differentiation, neutral_identity, neutral_typed_guidance


def genome():
    g = dict(count=dict(r=40), excitability=dict(r=dict(shift_v=5, shift_s=4)),
             migration=dict(r=dict(mean=np.full(3, 0.5), spread=0.3)), inhibitory=dict(r=dict(a0=-1.0, a=np.zeros(3))),
             differentiation=dict(r=neutral_differentiation()), identity=dict(r=neutral_identity()))
    g["guidance"] = {("a", "r"): neutral_typed_guidance(dict(B=np.eye(3), c=np.zeros(3), sigma=0.3, p0=0.5, w=100.0))}
    return g


GENES = (body_genes("r") + differentiation_genes("r") + identity_genes("r") + guidance_genes("a", "r")
         + typed_guidance_genes("a", "r"))


def test_paths_reach_into_arrays():
    g = genome()
    set_gene(g, ("guidance", ("a", "r"), "B", 0, 2), 1.5)
    set_gene(g, ("identity", "r", "logits", 3, 1), -2.0)
    set_gene(g, ("differentiation", "r", "exc", "b", 1), 0.7)
    assert get_gene(g, ("guidance", ("a", "r"), "B", 0, 2)) == 1.5 and g["guidance"][("a", "r")]["B"][1, 1] == 1.0
    assert get_gene(g, ("identity", "r", "logits", 3, 1)) == -2.0 and get_gene(g, ("differentiation", "r", "exc", "b", 1)) == 0.7


def test_unit_coding_round_trip_and_integers():
    g = genome()
    u = np.random.default_rng(0).random(len(GENES))
    g2 = from_unit(g, GENES, u)
    assert isinstance(g2["count"]["r"], int) and isinstance(g2["excitability"]["r"]["shift_v"], int)
    cont = [k for k, (p, lo, hi) in enumerate(GENES) if p[0] not in ("count", "excitability")]
    assert np.allclose(to_unit(g2, GENES)[cont], u[cont])
    assert g["count"]["r"] == 40                                          # the original genome is not modified


def test_json_round_trip():
    g = from_unit(genome(), GENES, np.random.default_rng(1).random(len(GENES)))
    g3 = from_json(json.loads(json.dumps(to_json(g))))
    assert np.allclose(to_unit(g3, GENES), to_unit(g, GENES)) and ("a", "r") in g3["guidance"]


def test_island_evolution_improves_a_simple_objective_and_audit():
    base = dict(x=dict(a=0.0, b=0.0))
    genes = [(("x", "a"), -1.0, 1.0), (("x", "b"), -1.0, 1.0)]

    def evaluate(gs, seeds):
        fit = [-(g["x"]["a"] - 0.6) ** 2 - (g["x"]["b"] + 0.3) ** 2 for g in gs]
        return fit, [dict(seeds=list(seeds))] * len(gs)
    P, hist = evolve(base, genes, evaluate, island=0, pop=16, gens=30, seeds_per_gen=2)
    assert hist[-1]["best"] > hist[0]["best"] and hist[-1]["best"] > -0.01
    g, info = choose(base, genes, P, evaluate, (2000, 2001))
    assert abs(g["x"]["a"] - 0.6) < 0.1 and abs(g["x"]["b"] + 0.3) < 0.1
    assert seeds_of(0, 0, 2) != seeds_of(1, 0, 2)
    r = audit(lambda gg, s: dict(score=np.linspace(0.5, 1, len(s)), passed=np.ones(len(s), bool), cost=0.1), g, seeds=range(5))
    assert r["all_pass"] and r["worst"] == 0.5
    assert abs(robust_value(dict(score=[0.5, 1.0], cost=0.1)) - (0.5 + 0.25 * 0.75 - 0.1)) < 1e-12
