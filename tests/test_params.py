import pytest
import numpy as np

from neurogenesis.params import (
    Const, Gene, Field, Fit, Expr, resolve, collect_genes, collect_project_genes,
    param_from_dict, param_to_dict
)


def test_resolve_const():
    assert resolve(Const(42.0), {}, {}, np.zeros((1, 3))) == 42.0
    assert resolve({"type": "Const", "value": 10}, {}, {}, np.zeros((1, 3))) == 10


def test_resolve_real_genome():
    # Toolbox genome contains real unnormalized values, e.g. count.map = 60
    genome = {"count": {"map": 60}}
    param = Gene(("count", "map"), lo=10, hi=100, integer=True)
    assert resolve(param, genome, {}, np.zeros((1, 3))) == 60

    # Projection tuple path in genome: ("guidance", ("sensory", "inter"), "w")
    genome_guidance = {
        "guidance": {
            ("sensory", "inter"): {"w": 45.5}
        }
    }
    param_proj = Gene(("guidance", ("sensory", "inter"), "w"))
    assert resolve(param_proj, genome_guidance, {}, np.zeros((1, 3))) == 45.5


def test_resolve_field():
    class DummyField:
        def sample(self, pos):
            return np.ones(len(pos)) * 5.0

    fields = {"dummy": DummyField()}
    param = Field("dummy")
    assert np.all(resolve(param, {}, fields, np.zeros((3, 3))) == 5.0)


def test_resolve_field_transform():
    class DummyField:
        def sample(self, pos):
            return np.array([-2.0, 3.0, -5.0])

    fields = {"grad": DummyField()}
    param_abs = Field("grad", transform="abs")
    assert np.all(resolve(param_abs, {}, fields, np.zeros((3, 3))) == np.array([2.0, 3.0, 5.0]))

    param_clip = Field("grad", transform="clip(-1, 2)")
    assert np.all(resolve(param_clip, {}, fields, np.zeros((3, 3))) == np.array([-1.0, 2.0, -1.0]))


def test_resolve_fit():
    param = Fit("target", 3.14, 0.0, 10.0)
    assert resolve(param, {}, {}, np.zeros((1, 3))) == 3.14


def test_resolve_expr_with_variables():
    # Expr accepts variable names from context
    param = Expr("2 * density + 5")
    assert resolve(param, {}, {}, context_vars={"density": 10}) == 25

    # ^ translates to exponentiation, NOT XOR!
    param_pow = Expr("x ^ 2")
    assert resolve(param_pow, {}, {}, context_vars={"x": 4}) == 16


def test_param_serialization_roundtrip():
    params = [
        Const(12.5),
        Gene(("count", "map"), lo=10.0, hi=100.0, integer=True),
        Field("gradient", transform="abs"),
        Fit("rate", 20.0, 5.0, 50.0),
        Expr("density * 2")
    ]
    for p in params:
        d = param_to_dict(p)
        p_rec = param_from_dict(d)
        assert type(p) == type(p_rec)
        d2 = param_to_dict(p_rec)
        assert d == d2


def test_collect_genes_evolution_format():
    # Returns (path, lo, hi, integer) tuples for evolution
    schedule = [
        {"params": {"p1": Gene(("count", "map"), lo=10, hi=100, integer=True), "p2": Const(1)}},
        {"params": {"p3": {"type": "Gene", "path": ["guidance", "w"], "lo": 0.0, "hi": 50.0}}}
    ]
    genes = collect_genes(schedule)
    assert len(genes) == 2
    assert genes[0] == (("count", "map"), 10.0, 100.0, True)
    assert genes[1] == (("guidance", "w"), 0.0, 50.0, False)


def test_collect_genes_finds_nested_genes():
    g_w = {"type": "Gene", "path": ["guidance", "0->1", "w"], "lo": 1.0, "hi": 9.0}
    project = {
        "schedule": [
            {"operator": "express", "params": {"morphogens": [{"axis": 0, "decay": {"type": "Gene", "path": "m.decay",
                                                                                    "lo": 0.1, "hi": 2.0}}]}},
            {"operator": "differentiate", "params": {"types": {"pyr": {"threshold": Gene(("types", "pyr"), 0, 1)},
                                                               "int": {"weights": [0.5, {"path": ["types", "int"],
                                                                                         "lo": 0, "hi": 3, "integer": True}]}}}},
            {"operator": "grow_axons", "params": {"guidance": [{"src": 0, "target": 1, "w": g_w, "sigma": 0.1}]}},
            {"operator": "grow_axons", "params": {"guidance": {"0->1": {"w": dict(g_w, lo=5.0)}}}},
        ],
        "fields": {"layers": {"type": "LayerStackField", "thicknesses": [
            {"type": "Gene", "path": ["layers", "l1"], "lo": 0.1, "hi": 0.5}, 0.3]}},
    }
    schedule_genes = collect_genes(project["schedule"])
    assert [g[0] for g in schedule_genes] == [("guidance", "0->1", "w"), ("m", "decay"), ("types", "int"), ("types", "pyr")]
    assert schedule_genes[0] == (("guidance", "0->1", "w"), 1.0, 9.0, False)  # first use wins, listed once
    assert schedule_genes[2] == (("types", "int"), 0.0, 3.0, True)
    all_genes = collect_project_genes(project)
    assert [g[0] for g in all_genes] == sorted([g[0] for g in schedule_genes] + [("layers", "l1")], key=str)
    assert collect_project_genes(project) == all_genes
    assert collect_project_genes({"schedule": [{"params": {"N": 10}}]}) == []


def test_param_from_dict_needs_type_unless_shape_is_exact():
    # Ordinary nested dicts stay plain values
    for d in ({"target": 1, "w": 2.0}, {"name": "a"}, {"name": "a", "size": 3}, {"path": "x"},
              {"value": 3, "title": "three"}, {"formula": "x", "doc": "y"}, {"src": 0, "target": 1, "p0": 0.5},
              {"type": "excitatory", "value": 2}, {"type": ["Gene"], "path": "x"}):
        p = param_from_dict(d)
        assert isinstance(p, Const) and p.value == d, d
    # Exact shapes and explicit types are Param sources
    assert param_from_dict({"value": 3}) == Const(3)
    assert param_from_dict({"path": ["a", "b"], "lo": 0, "hi": 2}) == Gene(("a", "b"), 0.0, 2.0)
    assert param_from_dict({"name": "f", "transform": "abs"}) == Field("f", "abs")
    assert param_from_dict({"target": "rate", "init": 1, "lo": 0, "hi": 2}) == Fit("rate", 1.0, 0.0, 2.0)
    assert param_from_dict({"formula": "2 * x"}) == Expr("2 * x")
    assert param_from_dict({"type": "Field", "name": "f"}) == Field("f")
    assert param_from_dict({"type": "Gene", "path": "a.b"}) == Gene("a.b")
    with pytest.raises(ValueError, match="missing"):
        param_from_dict({"type": "Fit", "target": "rate"})
