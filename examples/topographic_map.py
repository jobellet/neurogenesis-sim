"""Minimal example: grow a topographic sensor -> map circuit from a genome, stimulate one corner, save it for the viewer.

    python examples/topographic_map.py [--out out_dir] [--cpu]
Writes network.json (open it in the 3D viewer: cd viz && npm run dev, then "Import") and module.json (shareable module).
"""
import argparse
import os
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="example_out")
ap.add_argument("--cpu", action="store_true")
args = ap.parse_args()
if args.cpu:
    os.environ["JAX_PLATFORMS"] = "cpu"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from neurogenesis.development import BodyPlan, FixedPlacement, Region, grow, region_of  # noqa: E402
from neurogenesis.modules import Module  # noqa: E402
from neurogenesis.spiking.batch import simulate_counts  # noqa: E402


def make_plan(side=6):
    sheet = [[(i + 0.5) / side, (j + 0.5) / side, 0.5] for i in range(side) for j in range(side)]
    return BodyPlan(name="topographic map", regions=[
        Region("sensor", origin=(0, 0, 0), size=(30, 30, 5), placement=FixedPlacement(sheet), role=1),
        Region("map", origin=(50, 0, 0), size=(30, 30, 10))],
        projections=[("sensor", "map")])


def make_genome():
    return dict(count=dict(map=200), inh_weight_factor=2.0, w_clip=2047,
                migration=dict(map=dict(mean=np.full(3, 0.5), spread=0.35)),
                inhibitory=dict(map=dict(a0=-6.0, a=np.zeros(3))),          # all excitatory in practice
                guidance={("sensor", "map"): dict(B=np.diag([2.0, 2.0, 0.0]), c=np.zeros(3), sigma=0.12, p0=0.9, w=900.0)})


def main():
    plan, genome = make_plan(), make_genome()
    net = grow(plan, genome, seed=0)
    sensor, mp = region_of(net, plan, "sensor"), region_of(net, plan, "map")
    ext = np.zeros((2, net.num_neurons), np.int32)
    ext[0, sensor[0]] = 120                                                # one corner of the sheet
    ext[1, sensor[-1]] = 120                                               # the opposite corner
    counts = simulate_counts([net], [ext], ticks=50, blank=40)[0]           # 40 silent ticks before each stimulus
    u = np.asarray([(net.neurons[i].x - 50) / 30 for i in mp])
    for k, name in enumerate(("corner (0, 0)", "corner (1, 1)")):
        c = counts[k, mp]
        print(f"stimulus at {name}: {int((c > 0).sum())} map neurons fire, spike-weighted mean u of the map {(u * c).sum() / c.sum():.2f}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    net.save_json(out / "network.json")
    Module("topographic map", plan, genome, inputs=["sensor"], outputs=["map"],
           description="sensor sheet -> topographic map").save(out / "module.json")
    print("wrote", out / "network.json", "and", out / "module.json")
    return counts, u, mp


if __name__ == "__main__":
    main()
