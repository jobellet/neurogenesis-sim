"""A layered sheet grown from progenitors: developmental pipeline example.

Pipeline:
  1. seed_cells in a Sheet2D (progenitor zone scaffold)
  2. cell_cycle_clock (C14) -> temporal_competence (C15) -> proliferate (C2) across 3 neurogenic cycles,
     where exiting progenitors freeze their exit generation and competence channels
  3. differentiate (C7) from competence channels at cycle exit (assigning deep, mid, superficial excitatory
     and superficial inhibitory phenotypes)
  4. migrate (C4) to the target layer of each cell's type in a LayerStackField, producing emergent inside-out
     laminar organization (Rakic 1974 Science; Angevine & Sidman 1961 Nature; McConnell & Kaznowski 1991 Science)
  5. grow_axons (C8) with laminar targeting (chemoaffinity)
  6. refine_by_activity (C11, STDP plasticity)
  7. prune (C10, threshold weak synapses)

Usage:
    python examples/layered_sheet.py [--out example_out] [--cpu] [--seed 42]
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from neurogenesis.project.io import Project  # noqa: E402
from neurogenesis.stages.base import run_schedule  # noqa: E402


def _spearmanr(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Spearman rank correlation with tie-averaged ranks (pure NumPy, no SciPy)."""
    def _rankdata(x: np.ndarray) -> np.ndarray:
        _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
        cs = np.cumsum(counts)
        starts = cs - counts
        avg_ranks = 0.5 * (starts + cs - 1)
        return avg_ranks[inv]

    ra = _rankdata(np.asarray(a, dtype=float))
    rb = _rankdata(np.asarray(b, dtype=float))
    da = ra - np.mean(ra)
    db = rb - np.mean(rb)
    denom = float(np.sqrt(np.sum(da * da) * np.sum(db * db)))
    if denom == 0.0:
        return 0.0, 1.0
    r = float(np.clip(np.sum(da * db) / denom, -1.0, 1.0))
    n = len(ra)
    if n <= 2 or abs(r) >= 1.0:
        return r, 0.0
    z = abs(r) * math.sqrt((n - 2) / max(1e-12, 1.0 - r * r))
    pval = math.erfc(z / math.sqrt(2.0))
    return r, pval


def build_project() -> Project:
    """Build the specification of the layered sheet developmental project."""
    geometry = {
        "sheet": {
            "type": "Sheet2D",
            "center": [20.0, 20.0, 0.0],
            "u_vec": [40.0, 0.0, 0.0],
            "v_vec": [0.0, 40.0, 0.0],
            "thickness": 0.5,
        }
    }

    fields = {
        "layers": {
            "type": "LayerStackField",
            "base_field": {
                "type": "AnalyticField",
                "expr": "z",
            },
            "thicknesses": [8.0, 8.0, 8.0],
            "labels": [0, 1, 2],
        },
    }

    genome = {
        "layer_scale": 1.0,
    }

    competence_channels = [
        {"channel": 0, "until": 1},
        {"channel": 1, "until": 2},
        {"channel": 2, "until": 3},
    ]
    q_table = [0.35, 0.5, 1.0]
    tc_table = [9.0, 13.0, 18.0]

    schedule = [
        {
            "name": "seed",
            "operator": "seed_cells",
            "params": {
                "geometry": "sheet",
                "N": 25,
                "region": 0,
                "cell_type": 0,
            },
        },
    ]

    for cc in range(1, 4):
        schedule.extend([
            {
                "name": f"clock_cc{cc}",
                "operator": "cell_cycle_clock",
                "params": {
                    "q_table": q_table,
                    "T_C": tc_table,
                },
            },
            {
                "name": f"competence_cc{cc}",
                "operator": "temporal_competence",
                "params": {
                    "channels": competence_channels,
                },
            },
            {
                "name": f"proliferate_cc{cc}",
                "operator": "proliferate",
                "params": {
                    "prob": 1.0,
                    "max_cells": 120,
                    "jitter": 0.1,
                },
            },
        ])

    schedule.extend([
        {
            "name": "differentiate_from_competence",
            "operator": "differentiate",
            "params": {
                "types": [
                    {"type_id": 2, "condition": "(expr[2] > 0.5) & (cell_id % 4 != 0)", "sign": 1, "base_weight": 600},
                    {"type_id": 3, "condition": "(expr[2] > 0.5) & (cell_id % 4 == 0)", "sign": -1, "base_weight": 400},
                    {"type_id": 1, "condition": "expr[1] > 0.5", "sign": 1, "base_weight": 500},
                    {"type_id": 0, "condition": "expr[0] > 0.5", "sign": 1, "base_weight": 300},
                ]
            },
        },
        {
            "name": "migrate_to_type_layer",
            "operator": "migrate",
            "params": {
                "steps": 30,
                "speed": 1.0,
                "direction": [0.0, 0.0, 1.0],
                "layer_field": "layers",
                "target_layer": {"type": "Expr", "formula": "np.minimum(cell_type, 2) * layer_scale"},
            },
        },
        {
            "name": "grow_axons",
            "operator": "grow_axons",
            "params": {
                "projections": ["0->0"],
                "conduction_velocity": 2.0,
                "guidance": {
                    "0->0": {
                        "p0": 0.2,
                        "sigma": 0.35,
                        "w": 500.0,
                        "rules_target": ["lamina"],
                        "lamina": [0.1, 0.5, 0.9],
                    }
                },
            },
        },
        {
            "name": "refine_by_activity",
            "operator": "refine_by_activity",
            "params": {
                "rule": "stdp",
                "ticks": 50,
                "sources": [0, 1, 2, 3, 4],
                "poisson_hz": 30.0,
                "A_plus": 2.0,
                "A_minus": 1.0,
                "w_min": 0.0,
                "w_max": 1000.0,
            },
        },
        {
            "name": "prune",
            "operator": "prune",
            "params": {
                "threshold": 20,
            },
        },
    ])

    return Project(
        geometry=geometry,
        fields=fields,
        genome=genome,
        schedule=schedule,
        metadata={
            "name": "Layered Sheet",
            "description": "Layered sheet grown from progenitors with emergent inside-out neurogenesis (C14 -> C15 -> differentiate -> migrate)",
        },
    )


def analyze_circuit(tissue):
    """Compute cells per layer, layer connection matrix, delay distribution, and birth-cycle rank correlation."""
    num_types = 4
    cells_per_type = np.bincount(tissue.cell_type, minlength=num_types)

    conn_matrix = np.zeros((num_types, num_types), dtype=int)
    if tissue.connectivity is not None and len(tissue.connectivity.pre) > 0:
        pre_types = tissue.cell_type[tissue.connectivity.pre]
        post_types = tissue.cell_type[tissue.connectivity.post]
        for src, dst in zip(pre_types, post_types):
            if 0 <= src < num_types and 0 <= dst < num_types:
                conn_matrix[src, dst] += 1

        delays = np.asarray(tissue.connectivity.delay, dtype=int)
        delay_min = int(np.min(delays))
        delay_max = int(np.max(delays))
        delay_mean = float(np.mean(delays))
        inhibitory_synapses = int(np.sum(tissue.connectivity.weight < 0))
        excitatory_synapses = int(np.sum(tissue.connectivity.weight > 0))
    else:
        delays = np.array([], dtype=int)
        delay_min, delay_max, delay_mean = 0, 0, 0.0
        inhibitory_synapses = 0
        excitatory_synapses = 0

    corr, pval = _spearmanr(tissue.generation, tissue.positions[:, 2])

    return {
        "cells_per_type": cells_per_type.tolist(),
        "connection_matrix": conn_matrix.tolist(),
        "delay_min": delay_min,
        "delay_max": delay_max,
        "delay_mean": delay_mean,
        "inhibitory_synapses": inhibitory_synapses,
        "excitatory_synapses": excitatory_synapses,
        "birth_order_rank_corr": float(corr),
        "birth_order_p_value": float(pval),
        "total_cells": int(np.sum(tissue.alive)),
        "total_synapses": int(len(tissue.connectivity.pre)) if tissue.connectivity else 0,
    }


def main():
    ap = argparse.ArgumentParser(description="Grow a layered sheet from progenitors.")
    ap.add_argument("--out", default="example_out", help="Output directory for network.json and project.json")
    ap.add_argument("--cpu", action="store_true", help="Force JAX CPU execution")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for development and simulation")
    args = ap.parse_args()

    if args.cpu:
        os.environ["JAX_PLATFORMS"] = "cpu"

    proj = build_project()
    tissue = run_schedule(proj.to_dict(), genome=proj.genome, seed=args.seed)
    stats = analyze_circuit(tissue)

    print(f"Layered sheet grown: {stats['total_cells']} cells, {stats['total_synapses']} synapses "
          f"({stats['excitatory_synapses']} exc, {stats['inhibitory_synapses']} inh).")
    print(f"Cells per type (0: deep exc, 1: mid exc, 2: superficial exc, 3: superficial inh): {stats['cells_per_type']}")
    print(f"Birth cycle vs laminar depth rank correlation: {stats['birth_order_rank_corr']:.3f} (p={stats['birth_order_p_value']:.2e})")
    print("Connection matrix (pre \\ post):")
    for row in stats["connection_matrix"]:
        print(f"  {row}")
    print(f"Delay distribution: min={stats['delay_min']}, max={stats['delay_max']}, mean={stats['delay_mean']:.2f}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    proj.save(out_dir / "project.json")

    net = tissue.to_network()
    net.save_json(out_dir / "network.json")
    with open(out_dir / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
