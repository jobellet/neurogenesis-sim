"""A sheet with hand-placed orientation pinwheels whose cell density follows the map (semi-supervised, roadmap G2.2).

Hand-made scaffold: a flat sheet, an orientation map (`PinwheelField`) from four hand-placed pinwheels with charges
+-1/2, and the same pinwheel centres as a point set (`PointSetField`, distance to the nearest centre).
Development: progenitors seeded with a constant density proliferate with a probability that decays with distance to
the nearest pinwheel (a `Field` param with a transform), then migrate a little up a gradient towards the centres
(chemotaxis down the distance field). The density of cells therefore follows the map. Each cell's preferred
orientation is read from the map at its final position, and the map's pinwheels are recovered from a regular grid
(`find_pinwheels`).

Usage:
    python examples/pinwheel_sheet.py [--out example_out] [--seed 0]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from neurogenesis.fields import PinwheelField, find_pinwheels, pinwheel_map  # noqa: E402
from neurogenesis.project.io import Project  # noqa: E402
from neurogenesis.stages.base import _instantiate_fields, run_schedule  # noqa: E402

CENTRES = [[3.0, 3.0], [7.0, 7.0], [3.0, 7.0], [7.0, 3.0]]
CHARGES = [0.5, 0.5, -0.5, -0.5]
SIDE = 10.0


def build_project(prolif_peak=0.9, prolif_length=1.0, chemotaxis=0.05) -> Project:
    geometry = {"sheet": {"type": "Box", "center": [SIDE / 2, SIDE / 2, 0.0], "size": [SIDE, SIDE, 0.0]}}
    fields = {"orientation": {"type": "PinwheelField", "singularities": CENTRES, "charges": CHARGES},
              "centres": {"type": "PointSetField", "points": [c + [0.0] for c in CENTRES]}}
    schedule = [
        {"name": "progenitors", "operator": "seed_cells", "params": {"geometry": "sheet", "density": 4.0}},
        {"name": "divide", "operator": "proliferate", "repeat": 2, "params": {
            "prob": {"type": "Field", "name": "centres", "transform": f"{prolif_peak} * np.exp(-x / {prolif_length})"},
            "jitter": 0.1}},
        {"name": "gather", "operator": "migrate", "params": {
            "steps": 5, "chemotaxis_field": "centres", "chemotaxis": -chemotaxis, "boundary": "sheet",
            "gradient_step": 0.01}},
        {"name": "freeze", "operator": "freeze", "params": {}},
    ]
    return Project(geometry=geometry, fields=fields, schedule=schedule,
                   metadata={"name": "pinwheel sheet", "workflow": "semi-supervised"})


def analyse(tissue, project: Project, near: float = 1.5):
    d = project.to_dict()
    fields = _instantiate_fields({**d["geometry"], **d["fields"]})
    pos = tissue.positions[tissue.alive]
    dist = fields["centres"].values(pos)
    area_near = len(CENTRES) * np.pi * near ** 2
    density_near = float(np.sum(dist < near) / area_near)
    density_far = float(np.sum(dist >= near) / (SIDE * SIDE - area_near))
    theta = fields["orientation"].values(pos)
    hist = np.histogram(theta, bins=4, range=(0, np.pi))[0]
    _, angles, _ = pinwheel_map((np.zeros(2), np.full(2, SIDE)), 0.1, np.asarray(CENTRES), np.asarray(CHARGES))
    found, charges = find_pinwheels(angles, [0.0, 0.0], 0.1)
    return dict(cells=int(len(pos)), density_near=density_near, density_far=density_far,
                density_ratio=density_near / max(density_far, 1e-9), orientation_histogram=hist.tolist(),
                pinwheels_found=found.round(2).tolist(), pinwheel_charges=charges.tolist())


def main():
    ap = argparse.ArgumentParser(description="Grow a sheet whose density follows hand-placed orientation pinwheels.")
    ap.add_argument("--out", default="example_out")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()
    if args.cpu:
        os.environ["JAX_PLATFORMS"] = "cpu"
    proj = build_project()
    tissue = run_schedule(proj.to_dict(), proj.genome, args.seed)
    stats = analyse(tissue, proj)
    print(f"Sheet: {stats['cells']} cells")
    print(f"Density near pinwheels {stats['density_near']:.2f} vs far {stats['density_far']:.2f} cells per unit area "
          f"(ratio {stats['density_ratio']:.2f})")
    print(f"Preferred orientations (4 bins over [0, pi)): {stats['orientation_histogram']}")
    print(f"Pinwheels recovered from the map: {stats['pinwheels_found']} with charges {stats['pinwheel_charges']}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    proj.save(out / "project.json")
    tissue.to_network().save_json(out / "network.json")
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    main()
