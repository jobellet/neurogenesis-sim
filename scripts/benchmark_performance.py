#!/usr/bin/env python3
"""Run fixed CPU benchmarks and compare them with an earlier result from the same machine.

Timings depend on the machine, so a baseline is only compared when its machine fingerprint matches (OS, CPU, cores,
Python, JAX). The comparison is a report by default: shared CI runners vary too much for a hard gate. Pass --enforce
to exit with status 1 on a regression (for local use against a baseline you recorded on the same machine):

    python scripts/benchmark_performance.py --output perf.json                       # record
    python scripts/benchmark_performance.py --baseline perf.json --enforce           # later, same machine
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path

import numpy as np

from neurogenesis import cost
from neurogenesis.performance import regressions
from neurogenesis.spatial import CellList
from neurogenesis.spiking.batch import simulate_counts


def _measure(fn, repeats=3):
    fn()  # warm up JAX compilation and caches
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def run_benchmarks():
    """Measure deterministic workloads sized to finish quickly on a CI CPU."""
    n, e, ticks = 2048, 32768, 40
    net = cost._random_network(n, e, seed=7103)
    currents = np.random.default_rng(7104).integers(0, 40, (1, n), dtype=np.int32)
    simulation = lambda: simulate_counts([net], [currents], ticks=ticks, model="lif_int", check_cost=False)

    rng = np.random.default_rng(7105)
    points = rng.random((5000, 3))
    queries = rng.random((500, 3))
    cell_list = CellList(points, cutoff=0.08, box=(np.zeros(3), np.ones(3)))
    spatial = lambda: cell_list.query_radius(queries, radius=0.08)
    return {
        "lif_int_2048n_32768e_40t": _measure(simulation),
        "cell_list_5000p_500q_r008": _measure(spatial),
    }


def machine():
    """What a timing depends on, besides the code."""
    import jax
    return {"system": platform.system(), "machine": platform.machine(), "processor": platform.processor(),
            "cpus": os.cpu_count(), "python": platform.python_version(), "jax": jax.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("performance.json"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--limit", type=float, default=1.3)
    parser.add_argument("--enforce", action="store_true", help="exit with status 1 on a regression")
    args = parser.parse_args()

    result = {"schema": 2, "machine": machine(), "benchmarks": run_benchmarks()}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for name, seconds in result["benchmarks"].items():
        print(f"{name}: {seconds:.6f}s")

    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text())
        if baseline.get("machine") != result["machine"]:
            print(f"Baseline recorded on another machine ({baseline.get('machine')}); timings not compared.")
            return
        bad = regressions(baseline, result, args.limit)
        for name, (before, after) in bad.items():
            print(f"::warning::performance regression {name}: {after:.6f}s vs {before:.6f}s ({after / before:.2f}x)")
        if bad and args.enforce:
            raise SystemExit(1)
        if not bad:
            print(f"All benchmarks are within {args.limit:.2f}x of the baseline.")
    elif args.baseline:
        print("No baseline yet; this run records one.")


if __name__ == "__main__":
    main()
