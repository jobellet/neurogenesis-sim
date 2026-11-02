"""A fully genetic development, evolved on a toy objective (unsupervised, roadmap G2.3).

Every stage parameter that matters is a gene (`Gene` params, collected automatically with `collect_genes`):
  1. seed_cells: a few progenitors at the bottom of a box
  2. proliferate (gene: division probability), twice
  3. migrate upwards (gene: speed)
  4. express + differentiate: cells become type 1 where sigmoid(w_z z + b) > 0.5 (genes: w_z, b)
  5. proliferate differentiated cells only (an `Expr` param: gene x (cell_type == 1))
  6. grow_axons inside the box (gene: peak connection probability p0)
  7. freeze
Toy objective: 40 cells of type 0, 60 of type 1 and 400 synapses, in every individual (worst case over the
development seeds, as `evolution.robust`). The island model (`evolution.islands.evolve`) improves it in a few
generations.

Usage:
    python examples/evolved_development.py [--out example_out] [--gens 30] [--pop 16]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from neurogenesis.evolution.islands import evolve  # noqa: E402
from neurogenesis.params import collect_genes  # noqa: E402
from neurogenesis.project.io import Project  # noqa: E402
from neurogenesis.stages.base import run_schedule  # noqa: E402

TARGET = dict(type0=40, type1=60, synapses=400)
G = lambda path, lo, hi: {"type": "Gene", "path": path, "lo": lo, "hi": hi}


def build_project() -> Project:
    geometry = {"box": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}}
    fields = {"one": {"type": "AnalyticField", "expr": "1 + 0 * x"}, "height": {"type": "AnalyticField", "expr": "z"}}
    genome = {"div": 0.3, "speed": 0.02, "w_z": 5.0, "bias": -2.0, "div2": 0.1, "p0": 0.05}
    schedule = [
        {"name": "seed", "operator": "seed_cells", "params": {"N": 12, "position": [0.5, 0.5, 0.05], "jitter": 0.1}},
        {"name": "divide", "operator": "proliferate", "repeat": 2, "params": {"prob": G(["div"], 0.0, 1.0), "jitter": 0.05}},
        {"name": "rise", "operator": "migrate", "params": {"steps": 10, "speed": G(["speed"], 0.0, 0.1),
                                                           "direction": [0.0, 0.0, 1.0], "boundary": "box"}},
        {"name": "express", "operator": "express", "params": {"K": 1, "decay": 1.0, "morphogens": [
            {"field": {"type": "Field", "name": "height"}, "weights": [G(["w_z"], -20.0, 20.0)]},
            {"field": {"type": "Field", "name": "one"}, "weights": [G(["bias"], -10.0, 10.0)]}]}},
        {"name": "fate", "operator": "differentiate", "params": {"types": [
            {"type_id": 0, "sign": 1, "base_weight": 1}, {"type_id": 1, "condition": "expr[0] > 0.5", "sign": 1}]}},
        {"name": "divide_differentiated", "operator": "proliferate",
         "params": {"prob": {"type": "Expr", "formula": "div2 * (cell_type == 1)"}, "jitter": 0.05}},
        {"name": "axons", "operator": "grow_axons", "params": {
            "projections": ["0->0"], "exact": True, "conduction_velocity": 0.1,
            "guidance": {"0->0": {"p0": G(["p0"], 0.0, 0.5), "sigma": 0.3, "w": 200.0}}}},
        {"name": "freeze", "operator": "freeze", "params": {}},
    ]
    return Project(geometry=geometry, fields=fields, genome=genome, schedule=schedule,
                   metadata={"name": "evolved development", "workflow": "unsupervised"})


def genes_of(project_dict):
    """Evolution genes: every Gene param of the schedule, plus the gene read by the Expr param."""
    genes = [(path, lo, hi) for path, lo, hi, _ in collect_genes(project_dict["schedule"])]
    return genes + [(("div2",), 0.0, 1.0)]


def score(tissue) -> float:
    """1 - mean relative error to the targets (1 is perfect)."""
    n0, n1 = int(np.sum(tissue.cell_type == 0)), int(np.sum(tissue.cell_type == 1))
    e = len(tissue.connectivity.pre)
    err = [abs(n0 - TARGET["type0"]) / TARGET["type0"], abs(n1 - TARGET["type1"]) / TARGET["type1"],
           abs(e - TARGET["synapses"]) / TARGET["synapses"]]
    return 1.0 - float(np.mean(np.minimum(err, 1.0)))


def make_evaluator(project_dict):
    def evaluate(genomes, seeds):
        fit, info = [], []
        for g in genomes:
            s = [score(run_schedule(project_dict, g, int(seed))) for seed in seeds]
            fit.append(min(s) + 0.25 * float(np.mean(s)))
            info.append(dict(worst=min(s), mean=float(np.mean(s))))
        return fit, info
    return evaluate


def main():
    ap = argparse.ArgumentParser(description="Evolve a fully genetic development on a toy objective.")
    ap.add_argument("--out", default="example_out")
    ap.add_argument("--gens", type=int, default=30)
    ap.add_argument("--pop", type=int, default=16)
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()
    if args.cpu:
        os.environ["JAX_PLATFORMS"] = "cpu"
    proj = build_project()
    d = proj.to_dict()
    genes = genes_of(d)
    P, hist = evolve(proj.genome, genes, make_evaluator(d), pop=args.pop, gens=args.gens, seeds_per_gen=2, elite=2,
                     parents=4, sigma=0.15, log=lambda h: print(f"generation {h['generation']}: best {h['best']:.3f}"))
    from neurogenesis.genome.genes import from_unit
    best = from_unit(proj.genome, genes, P[0])
    tissue = run_schedule(d, best, 0)
    stats = dict(first_best=hist[0]["best"], final_best=hist[-1]["best"], genes=[list(g[0]) for g in genes],
                 cells_type0=int(np.sum(tissue.cell_type == 0)), cells_type1=int(np.sum(tissue.cell_type == 1)),
                 synapses=int(len(tissue.connectivity.pre)), best_genome={k: float(best[k]) for k in proj.genome})
    print(f"Best individual: {stats['cells_type0']} type-0 cells, {stats['cells_type1']} type-1 cells, "
          f"{stats['synapses']} synapses (target {TARGET})")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    Project(**{**d, "genome": best}).save(out / "project.json")
    tissue.to_network().save_json(out / "network.json")
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    main()
