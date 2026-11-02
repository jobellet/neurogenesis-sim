"""Tests for F2: Removing eval and enforcing restricted safe expression evaluation."""
import numpy as np
import pytest

from neurogenesis.expressions import eval_expr
from neurogenesis.fields import AnalyticField
from neurogenesis.stages.differentiation import Differentiate
from neurogenesis.stages.base import run_schedule
from neurogenesis.tissue import Tissue
from neurogenesis.params import Const


def test_eval_expr_arithmetic_and_power():
    res = eval_expr("x + 2 * y - z / 2", {"x": 10.0, "y": 3.0, "z": 4.0})
    assert res == 14.0

    # Both ** and ^ should evaluate as power
    assert eval_expr("x ** 3", {"x": 2.0}) == 8.0
    assert eval_expr("x ^ 3", {"x": 2.0}) == 8.0


def test_eval_expr_numpy_ufuncs_and_constants():
    pts = np.array([0.0, np.pi / 2, np.pi])
    sin_vals = eval_expr("sin(x)", {"x": pts})
    np.testing.assert_allclose(sin_vals, [0.0, 1.0, 0.0], atol=1e-7)

    exp_vals = eval_expr("exp(x)", {"x": np.array([0.0, 1.0])})
    np.testing.assert_allclose(exp_vals, [1.0, np.e], atol=1e-7)

    # Calling via np. attribute
    cos_vals = eval_expr("np.cos(x)", {"x": pts, "np": np})
    np.testing.assert_allclose(cos_vals, [1.0, 0.0, -1.0], atol=1e-7)

    # Constants pi and e
    assert np.isclose(eval_expr("pi"), np.pi)
    assert np.isclose(eval_expr("e"), np.e)


def test_eval_expr_comparisons_and_boolean_logic():
    arr1 = np.array([1, 5, 10])
    arr2 = np.array([2, 5, 8])

    # Bitwise and chained comparisons
    gt = eval_expr("x > y", {"x": arr1, "y": arr2})
    np.testing.assert_array_equal(gt, [False, False, True])

    # Chained comparison
    between = eval_expr("2 < x < 8", {"x": arr1})
    np.testing.assert_array_equal(between, [False, True, False])

    # Boolean operators with arrays
    both = eval_expr("(x > 2) and (x < 8)", {"x": arr1})
    np.testing.assert_array_equal(both, [False, True, False])

    either = eval_expr("(x < 2) or (x > 8)", {"x": arr1})
    np.testing.assert_array_equal(either, [True, False, True])


def test_eval_expr_subscript_and_slice():
    mat = np.array([[10, 20], [30, 40], [50, 60]])
    col0 = eval_expr("m[:, 0]", {"m": mat})
    np.testing.assert_array_equal(col0, [10, 30, 50])

    row1 = eval_expr("m[1]", {"m": mat})
    np.testing.assert_array_equal(row1, [30, 40])


def test_eval_expr_security_blocks_arbitrary_code_execution():
    # Attempt import
    with pytest.raises((TypeError, ValueError)):
        eval_expr("__import__('os').system('ls')")

    # Attempt class hierarchy traversal
    with pytest.raises(ValueError, match="prohibited"):
        eval_expr("().__class__.__bases__[0].__subclasses__()")

    # Attempt calling open or eval
    with pytest.raises(ValueError, match="not found"):
        eval_expr("open('/etc/passwd')")

    # Attempt lambda
    with pytest.raises(TypeError, match="Disallowed expression syntax"):
        eval_expr("(lambda x: x)(5)")

    # Attempt comprehension
    with pytest.raises(TypeError, match="Disallowed expression syntax"):
        eval_expr("[x for x in (1, 2)]")


def test_analytic_field_uses_safe_eval():
    field = AnalyticField("sin(x) + cos(y) + z^2")
    pts = np.array([[0.0, 0.0, 2.0], [np.pi / 2, 0.0, 3.0]])
    vals = field.values(pts)
    np.testing.assert_allclose(vals, [5.0, 11.0], atol=1e-7)

    # Malicious expression in AnalyticField raises rather than executing
    bad_field = AnalyticField("__import__('os').system('echo pwned')")
    with pytest.raises((TypeError, ValueError)):
        bad_field.values(pts)


def test_differentiate_condition_raises_on_error_never_swallowed():
    stage = Differentiate()
    t = Tissue.empty(K=2)
    t.add_cells(3, expression=np.array([[0.1, 0.9], [0.8, 0.2], [0.5, 0.5]]))

    # Bad condition with syntax error must RAISE, not silently set mask to 0
    bad_params_syntax = {
        "types": Const([
            {
                "type_id": 1,
                "condition": "expr[0 > >> 5",  # syntax error
            }
        ])
    }
    with pytest.raises(SyntaxError):
        stage.run(t, bad_params_syntax, {}, {}, np.random.default_rng(1))

    # Bad condition with unknown variable must RAISE
    bad_params_var = {
        "types": Const([
            {
                "type_id": 1,
                "condition": "nonexistent_variable > 0",
            }
        ])
    }
    with pytest.raises(ValueError, match="not found"):
        stage.run(t, bad_params_var, {}, {}, np.random.default_rng(1))


def test_end_to_end_project_safe_eval():
    """Verify that run_schedule executes projects with safe expressions and raises on bad ones."""
    good_project = {
        "version": "1.0.0",
        "geometry": {
            "box": {
                "type": "Box",
                "center": [0.0, 0.0, 0.0],
                "size": [10.0, 10.0, 10.0]
            }
        },
        "fields": {
            "dist": {
                "type": "AnalyticField",
                "expr": "sqrt(x^2 + y^2 + z^2)"
            }
        },
        "schedule": [
            {
                "operator": "seed_cells",
                "params": {"N": 20, "geometry": "box"}
            },
            {
                "operator": "differentiate",
                "params": {
                    "types": [
                        {
                            "type_id": 1,
                            "condition": "field_dist < 3.0",
                            "sign": 1
                        },
                        {
                            "type_id": 2,
                            "condition": "field_dist >= 3.0",
                            "sign": -1
                        }
                    ]
                }
            }
        ]
    }
    tissue = run_schedule(good_project, genome={}, seed=42)
    assert len(tissue.alive) == 20
    assert np.all(np.isin(tissue.cell_type, [1, 2]))

    # Malicious injection attempt in schedule condition
    malicious_project = {
        "version": "1.0.0",
        "geometry": {
            "box": {
                "type": "Box",
                "center": [0.0, 0.0, 0.0],
                "size": [10.0, 10.0, 10.0]
            }
        },
        "schedule": [
            {
                "operator": "seed_cells",
                "params": {"N": 5, "geometry": "box"}
            },
            {
                "operator": "differentiate",
                "params": {
                    "types": [
                        {
                            "type_id": 1,
                            "condition": "__import__('sys').exit(1)"
                        }
                    ]
                }
            }
        ]
    }
    with pytest.raises((TypeError, ValueError)):
        run_schedule(malicious_project, genome={}, seed=42)

