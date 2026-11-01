import pytest
import numpy as np

from neurogenesis.params import (
    Const, Gene, Field, Fit, Expr, resolve, collect_genes,
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
