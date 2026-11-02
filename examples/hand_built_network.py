"""A fully hand-built network (supervised workflow, roadmap G2.4): every cell and synapse is given by hand.

Pipeline (a Project whose stages take no genes):
  1. place_by_hand: a ring of excitatory cells, a few inhibitory cells in its centre and one Poisson driver
  2. connect_by_hand: the driver -> ring cell 0 and the ring chain by explicit index lists, ring -> inhibition and
     inhibition -> ring by connection rules (cell type selectors, all pairs)
  3. freeze: validation (indices, delays, Dale's principle) and compilation to an SNNNetwork

The compiled network is then simulated with the integer reference kernel. Activity travels around the ring: the first
spike of ring cell k comes later than that of cell k - 1 (a synfire chain, Abeles 1991, Corticonics).

Usage:
    python examples/hand_built_network.py [--out example_out] [--ring 12] [--ticks 300]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from neurogenesis.project.io import Project  # noqa: E402
from neurogenesis.spiking.reference import IntegerSNNSimulator  # noqa: E402
from neurogenesis.stages.freeze import develop  # noqa: E402

RING, INH, DRIVER = 0, 1, 2          # cell types


def build_project(n_ring: int = 12, n_inh: int = 4) -> Project:
    """Positions, types and synapses of the hand-built ring."""
    phi = 2 * np.pi * np.arange(n_ring) / n_ring
    ring = np.stack([10 * np.cos(phi), 10 * np.sin(phi), np.zeros(n_ring)], 1)
    psi = 2 * np.pi * np.arange(n_inh) / n_inh
    inh = np.stack([2 * np.cos(psi), 2 * np.sin(psi), np.zeros(n_inh)], 1)
    driver = np.array([[14.0, 0.0, 0.0]])
    n = n_ring + n_inh + 1
    d = n - 1                                                          # index of the driver
    ring_idx = np.arange(n_ring)
    schedule = [
        {"name": "cells", "operator": "place_by_hand", "params": {
            "positions": np.concatenate([ring, inh, driver]).tolist(),
            "cell_type": [RING] * n_ring + [INH] * n_inh + [DRIVER],
            "sign": [1] * n_ring + [-1] * n_inh + [1],
            "mode": [0] * (n - 1) + [1],                                # the driver is a Poisson cell
            "threshold": [1024] * n,
            "base_weight": [1] * n}},
        {"name": "chain", "operator": "connect_by_hand", "params": {
            "pre": [d] + ring_idx[:-1].tolist(),
            "post": [0] + ring_idx[1:].tolist(),
            "weight": 2500, "delay": 2,
            "rules": [{"pre": {"cell_type": RING}, "post": {"cell_type": INH}, "prob": 1.0, "weight": 300, "delay": 1},
                      {"pre": {"cell_type": INH}, "post": {"cell_type": RING}, "prob": 1.0, "weight": 150, "delay": 1,
                       "dale": True}]}},
        {"name": "freeze", "operator": "freeze", "params": {"dale": True}},
    ]
    return Project(schedule=schedule, metadata={"name": "hand-built ring", "workflow": "supervised"})


def set_driver_rate(net, hz: float):
    for nd in net.neurons:
        if nd.mode == 1:
            nd.poisson_hz = hz
    return net


def first_spikes(sim, n_ring: int) -> np.ndarray:
    """Tick of the first spike of each ring cell (-1 if it never fired)."""
    first = np.full(n_ring, -1)
    for t, i in sim.spike_history:
        if i < n_ring and first[i] < 0:
            first[i] = t
    return first


def main():
    ap = argparse.ArgumentParser(description="Simulate a fully hand-built ring network.")
    ap.add_argument("--out", default="example_out")
    ap.add_argument("--ring", type=int, default=12)
    ap.add_argument("--ticks", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cpu", action="store_true", help="accepted for symmetry with the other examples (no JAX used)")
    args = ap.parse_args()

    proj = build_project(args.ring)
    net = set_driver_rate(develop(proj.to_dict(), {}, seed=0, dale=True), 20.0)
    sim = IntegerSNNSimulator(net, seed=args.seed)
    res = sim.run(ticks=args.ticks)
    first = first_spikes(sim, args.ring)
    order_ok = bool(np.all(first >= 0) and np.all(np.diff(first) > 0))
    stats = dict(neurons=net.num_neurons, synapses=net.num_synapses, total_spikes=res["total_spikes"],
                 first_spike_ticks=first.tolist(), propagates_in_order=order_ok)
    print(f"Hand-built network: {net.num_neurons} neurons, {net.num_synapses} synapses")
    print(f"First spike of each ring cell (ticks): {first.tolist()}")
    print(f"Activity travels around the ring in order: {order_ok}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    proj.save(out / "project.json")
    net.save_json(out / "network.json")
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    main()
