import pytest

from neurogenesis.performance import regressions


def test_performance_regression_threshold_is_strictly_over_thirty_percent():
    baseline = {"benchmarks": {"a": 2.0}}
    assert regressions(baseline, {"benchmarks": {"a": 2.6}}) == {}
    assert regressions(baseline, {"benchmarks": {"a": 2.61}}) == {"a": (2.0, 2.61)}


def test_performance_comparison_rejects_incomplete_results():
    with pytest.raises(ValueError, match="missing benchmarks"):
        regressions({"benchmarks": {"a": 1.0}}, {"benchmarks": {}})
