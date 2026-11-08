import numpy as np, json, argparse; from pathlib import Path
from neurogenesis.project.io import Project; from neurogenesis.stages.base import run_schedule
from neurogenesis.pharmacology import Profile, Receptor, compile_weights
from neurogenesis.expressions import eval_expr; from neurogenesis.genome.genes import from_unit; from neurogenesis.evolution.islands import evolve
def build_project():
    g = {k: {"p0": 0.2, "w": 10.0} for k in ("0->0", "0->1", "1->0", "1->1")}
    s = [{"name": "seed", "operator": "seed_cells", "params": {"N": 60, "geometry": "b"}},
         {"name": "diff", "operator": "differentiate", "params": {"types": [{"type_id": 0, "sign": 1}, {"type_id": 1, "condition": "z > 0.5", "sign": -1}]}},
         {"name": "axons", "operator": "grow_axons", "params": {"projections": list(g), "exact": True, "guidance": g}}]
    return Project(geometry={"b": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}}, genome={"drug_dose": 1.5, "g_ampa": 0.8}, schedule=s)
def target_lfp_alpha(tissue, g):
    prof = Profile("gaba_ampa", receptors=[Receptor("ampa", sign=1, gain=float(g["g_ampa"])), Receptor("gabaa", sign=-1, gain=float(eval_expr("drug_dose * 1.5", g)))])
    tissue.connectivity.receptor_class = tissue.cell_type[tissue.connectivity.pre].astype(np.uint8)
    compile_weights(tissue, prof); w = tissue.connectivity.weight
    return float(np.exp(-0.5 * ((np.sum(w[w > 0]) / max(1.0, np.sum(np.abs(w[w < 0]))) - 4.0) / 0.8) ** 2))
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="."); ap.add_argument("--cpu", action="store_true")
    out = Path(ap.parse_known_args()[0].out); out.mkdir(parents=True, exist_ok=True)
    p = build_project(); d = p.to_dict(); genes = [(("drug_dose",), 0.1, 4.0), (("g_ampa",), 0.5, 3.0)]
    ev = lambda pop, seeds: ([float(np.mean([target_lfp_alpha(run_schedule(d, g, s), g) for s in (0, 1)])) for g in pop], [{} for _ in pop])
    P, hist = evolve(p.genome, genes, ev, island=42, pop=12, gens=4, seeds_per_gen=2, elite=2, parents=4, sigma=0.2)
    best = from_unit(p.genome, genes, P[0]); p.genome = best; tissue = run_schedule(d, best, 0)
    stats = {"first_best": hist[0]["best"], "final_best": hist[-1]["best"], "genes": [list(x[0]) for x in genes], "best_genome": {k: float(v) for k, v in best.items()}}
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    p.save(out / "project.json"); tissue.to_network().save_json(out / "network.json")
    print(f"Alpha fitness: {hist[0]['best']:.3f} -> {hist[-1]['best']:.3f}")
if __name__ == "__main__": main()
