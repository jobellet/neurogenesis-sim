"""A column with hand-drawn layers where genes decide cell types within each layer (semi-supervised, roadmap G2.1).

Hand-made scaffold: a box-shaped column and a layer stack (three layers, thicknesses drawn by hand, depth measured from
the top). Genes: one gene per layer biases a regulatory variable towards the inhibitory fate, so the fraction of
inhibitory interneurons in each layer is genetic, while every cell's fate also depends on its own noisy expression.

Pipeline:
  1. seed_cells with a density (cells per unit volume) in the column
  2. express (K = 1): a neutral starting expression
  3. proliferate with expression noise: daughters and mothers get different expression
  4. express: input = 8 (E - 0.5) + gene of the cell's layer (the layer field, read per cell), Hill-free sigmoid
  5. differentiate: type = 2 x layer + (1 if expression > 0.5: inhibitory)
  6. connect_by_hand rules: local excitatory and inhibitory connections (distance-limited, Dale's principle)
  7. freeze
Then a short simulation with a few Poisson drivers reports the firing rate per layer.

Usage:
    python examples/hand_drawn_column.py [--out example_out] [--cpu] [--seed 0]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from neurogenesis.params import collect_project_genes  # noqa: E402
from neurogenesis.project.io import Project  # noqa: E402
from neurogenesis.stages.base import run_schedule  # noqa: E402
from neurogenesis.stages.freeze import freeze  # noqa: E402

THICKNESS = [0.3, 0.3, 0.4]          # hand-drawn layer thicknesses, from the top (z = 1) down


def build_project(inh_genes=(-3.0, 0.0, 1.5)) -> Project:
    geometry = {"column": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}}
    fields = {"layers": {"type": "LayerStackField", "base_field": {"type": "AnalyticField", "expr": "1 - z"},
                         "thicknesses": THICKNESS, "labels": [0, 1, 2]},
              "one": {"type": "AnalyticField", "expr": "1 + 0 * x"}}
    genome = {"inhibitory_bias": {f"L{k}": float(g) for k, g in enumerate(inh_genes)}}
    in_layer = lambda k: {"type": "Field", "name": "layers", "transform": f"1.0 * (x[:, 0] == {k})"}
    gene = lambda k: {"type": "Gene", "path": ["inhibitory_bias", f"L{k}"], "lo": -6.0, "hi": 6.0}
    types = []
    for k in range(3):
        types.append({"type_id": 2 * k, "condition": f"field_layers[:, 0] == {k}", "sign": 1, "base_weight": 1})
        types.append({"type_id": 2 * k + 1, "condition": f"(field_layers[:, 0] == {k}) & (expr[0] > 0.5)", "sign": -1,
                      "base_weight": 1})
    schedule = [
        {"name": "progenitors", "operator": "seed_cells", "params": {"geometry": "column", "density": 500}},
        {"name": "start_expression", "operator": "express", "params": {"K": 1, "decay": 1.0}},
        {"name": "divide", "operator": "proliferate", "params": {"prob": 0.6, "jitter": 0.02, "expression_noise": 0.25}},
        {"name": "fate", "operator": "express", "params": {
            "K": 1, "weights": [[8.0]], "decay": 1.0,
            "morphogens": [{"field": {"type": "Field", "name": "one"}, "weights": [-4.0]}]
                          + [{"field": in_layer(k), "weights": [gene(k)]} for k in range(3)]}},
        {"name": "types", "operator": "differentiate", "params": {"types": types}},
        {"name": "wiring", "operator": "connect_by_hand", "params": {"rules": [
            {"pre": "sign > 0", "prob": 0.15, "max_distance": 0.2, "weight": 250, "velocity": 0.02, "dale": True},
            {"pre": "sign < 0", "prob": 0.4, "max_distance": 0.15, "weight": 400, "velocity": 0.02, "dale": True}]}},
        {"name": "freeze", "operator": "freeze", "params": {"dale": True}},
    ]
    return Project(geometry=geometry, fields=fields, genome=genome, schedule=schedule,
                   metadata={"name": "hand-drawn column", "workflow": "semi-supervised"})


def layer_stats(tissue):
    layer = tissue.cell_type // 2
    inh = tissue.cell_type % 2 == 1
    return dict(cells_per_layer=np.bincount(layer, minlength=3).tolist(),
                inhibitory_fraction=[float(inh[layer == k].mean()) if np.any(layer == k) else 0.0 for k in range(3)])


def simulate(tissue, seed, ticks=300, drivers=20, hz=40.0):
    """Mean rate (Hz) per layer with `drivers` excitatory cells turned into Poisson drivers."""
    from neurogenesis.stages.refinement import simulate_tissue
    t = tissue.subset(np.arange(len(tissue.alive)))
    t.connectivity = tissue.connectivity
    t.threshold[:] = 1024
    exc = np.flatnonzero(t.sign > 0)
    d = np.random.default_rng(seed).choice(exc, size=min(drivers, len(exc)), replace=False)
    t.mode[d], t.poisson_hz[d] = 1, hz
    spikes = simulate_tissue(t, ticks, seed)
    layer = t.cell_type // 2
    rate = spikes.sum(0) * 1000.0 / ticks
    others = np.ones(len(rate), bool)
    others[d] = False
    return [float(rate[(layer == k) & others].mean()) for k in range(3)]


def main():
    ap = argparse.ArgumentParser(description="Grow a column on hand-drawn layers; genes choose cell types.")
    ap.add_argument("--out", default="example_out")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    if args.cpu:
        os.environ["JAX_PLATFORMS"] = "cpu"

    proj = build_project()
    d = proj.to_dict()
    tissue = run_schedule(d, proj.genome, args.seed)
    net = freeze(tissue, dale=True)
    stats = layer_stats(tissue)
    stats.update(synapses=int(len(tissue.connectivity.pre)), genes=[list(g[0]) for g in collect_project_genes(d)],
                 rate_per_layer_hz=simulate(tissue, args.seed))
    print(f"Column: {sum(stats['cells_per_layer'])} cells, {stats['synapses']} synapses")
    print(f"Cells per layer (top to bottom): {stats['cells_per_layer']} for thicknesses {THICKNESS}")
    print(f"Inhibitory fraction per layer: {[round(x, 3) for x in stats['inhibitory_fraction']]} "
          f"(genes {list(proj.genome['inhibitory_bias'].values())})")
    print(f"Firing rate per layer (Hz): {[round(x, 1) for x in stats['rate_per_layer_hz']]}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    proj.save(out / "project.json")
    net.save_json(out / "network.json")
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    main()
