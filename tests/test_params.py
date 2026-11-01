import numpy as np

from neurogenesis.params import Const, Gene, Field, Fit, Expr, resolve, collect_genes

def test_resolve_const():
    assert resolve(Const(4.2), {}, {}, np.zeros((1, 3))) == 4.2

def test_resolve_gene():
    genome = {"layer1": {"density": 0.5}}
    param = Gene("layer1.density", 10.0, 20.0)
    # 0.5 -> 15.0
    assert resolve(param, genome, {}, np.zeros((1, 3))) == 15.0

def test_resolve_gene_integer():
    genome = {"layer1": {"density": 0.5}}
    param = Gene("layer1.density", 10.0, 21.0, integer=True)
    # 0.5 -> 15.5 -> 16
    assert resolve(param, genome, {}, np.zeros((1, 3))) == 16.0

def test_resolve_field_callable():
    def mock_field(positions):
        # return z coordinate
        return positions[:, 2]
    
    positions = np.array([[0, 0, 1], [0, 0, 2], [0, 0, 3]], dtype=float)
    res = resolve(Field("depth"), {}, {"depth": mock_field}, positions)
    np.testing.assert_array_equal(res, [1.0, 2.0, 3.0])
    
    # test with subset of cells
    res_subset = resolve(Field("depth"), {}, {"depth": mock_field}, positions, np.array([0, 2]))
    np.testing.assert_array_equal(res_subset, [1.0, 3.0])

def test_resolve_field_sample_method():
    class MockField:
        def sample(self, positions):
            return positions[:, 0]
            
    positions = np.array([[10, 0, 0], [20, 0, 0]], dtype=float)
    res = resolve(Field("x_val"), {}, {"x_val": MockField()}, positions)
    np.testing.assert_array_equal(res, [10.0, 20.0])

def test_resolve_fit():
    assert resolve(Fit("target1", init=5.5, lo=1.0, hi=10.0), {}, {}, np.zeros((1, 3))) == 5.5

def test_collect_genes():
    schedule = [
        {"params": {"p1": Gene("a.b", 0, 1), "p2": Const(1)}},
        {"params": {"p3": {"type": "Gene", "path": "c.d", "lo": 0, "hi": 1}}}
    ]
    genes = collect_genes(schedule)
    assert genes == ["a.b", "c.d"]

def test_resolve_expr():
    res = resolve(Expr("2 * (3 + 4)"), {}, {}, np.zeros((1, 3)))
    assert res == 14.0
