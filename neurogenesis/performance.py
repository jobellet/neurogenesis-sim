"""Comparison helpers for fixed performance benchmarks."""
from __future__ import annotations


def regressions(baseline: dict, current: dict, limit: float = 1.3) -> dict[str, tuple[float, float]]:
    """Return benchmark timings slower than ``limit`` times their baseline."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    before = baseline.get("benchmarks", {})
    after = current.get("benchmarks", {})
    if not before:
        raise ValueError("baseline has no benchmarks")
    missing = sorted(set(before) - set(after))
    if missing:
        raise ValueError(f"current results are missing benchmarks: {', '.join(missing)}")
    bad = {}
    for name, baseline_seconds in before.items():
        current_seconds = after[name]
        if baseline_seconds <= 0 or current_seconds < 0:
            raise ValueError(f"benchmark timings must be positive: {name}")
        if current_seconds > baseline_seconds * limit:
            bad[name] = (baseline_seconds, current_seconds)
    return bad
