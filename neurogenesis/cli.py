"""Command Line Interface (CLI) for SNN Morphogenetic Network Generation & Simulation.

Usage:
  python -m neurogenesis generate --neurons 1000 --morphology column --out network.json
  python -m neurogenesis simulate --network network.json --ticks 1000 --raster raster.png
  python -m neurogenesis stats --network network.json
  python -m neurogenesis export-presets --out-dir presets/
  python -m neurogenesis generate --neurons 500 --weight-scale 0.2 --refractory 3 --out column_unsaturated.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .spiking.morphology import MorphogeneticEngine
from .spiking.network import SNNNetwork
from .spiking.reference import IntegerSNNSimulator


def cmd_generate(args: argparse.Namespace) -> None:
    print(f"Generating SNN population ({args.neurons} neurons, morphology: '{args.morphology}')...")

    if args.morphology == "column":
        net = MorphogeneticEngine.generate_cortical_column(
            num_neurons=args.neurons,
            radius=args.radius,
            height=args.height,
            exc_ratio=args.exc_ratio,
            pace_ratio=args.pace_ratio,
            conduction_velocity=args.conduction_velocity,
            seed=args.seed,
            weight_scale=args.weight_scale,
            inh_scale=args.inh_scale,
            refractory=args.refractory,
        )
    elif args.morphology == "layered":
        net = MorphogeneticEngine.generate_layered_network(
            num_neurons=args.neurons,
            num_layers=args.layers,
            conduction_velocity=args.conduction_velocity,
            seed=args.seed,
        )
    elif args.morphology == "microcircuit":
        net = MorphogeneticEngine.generate_microcircuit(
            num_neurons=args.neurons,
            conduction_velocity=args.conduction_velocity,
            seed=args.seed,
        )
    else:
        net = MorphogeneticEngine.generate_cortical_column(
            num_neurons=args.neurons,
            seed=args.seed,
        )

    out_path = Path(args.out)
    net.save_json(out_path)
    print(f"✓ Network successfully saved to {out_path.resolve()}")
    print(f"  Neurons: {net.num_neurons:,} | Synapses: {net.num_synapses:,}")


def cmd_simulate(args: argparse.Namespace) -> None:
    print(f"Loading network from {args.network}...")
    net = SNNNetwork.load_json(args.network)
    print(f"Simulating {net.num_neurons} neurons for {args.ticks} ticks (seed={args.seed})...")

    sim = IntegerSNNSimulator(net, seed=args.seed)
    res = sim.run(ticks=args.ticks)

    print(f"✓ Simulation Complete:")
    print(f"  Total spikes emitted: {res['total_spikes']:,}")
    print(f"  Mean population rate: {res['mean_population_hz']} Hz")

    if args.raster:
        raster_path = Path(args.raster)
        raster_path.parent.mkdir(parents=True, exist_ok=True)
        sim.plot_raster(str(raster_path))
        print(f"✓ Spike raster plot saved to {raster_path.resolve()}")


def cmd_stats(args: argparse.Namespace) -> None:
    net = SNNNetwork.load_json(args.network)
    stats = net.compute_statistics()
    print(f"\n--- SNN Topology & Biophysical Statistics: {net.morphology} ---")
    print(json.dumps(stats, indent=2))


def cmd_export_presets(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting standard presets to {out_dir.resolve()}...")

    # Preset 1: Cortical Column 1000
    col1000 = MorphogeneticEngine.generate_cortical_column(1000, seed=42)
    col1000.save_json(out_dir / "cortical_column_1000.json")

    # Preset 2: Microcircuit 100
    micro100 = MorphogeneticEngine.generate_microcircuit(100, seed=42)
    micro100.save_json(out_dir / "microcircuit_100.json")

    # Preset 3: Layered Sheets 600
    layered600 = MorphogeneticEngine.generate_layered_network(600, seed=42)
    layered600.save_json(out_dir / "layered_sheets_600.json")

    print(f"✓ Exported 3 presets to {out_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m neurogenesis",
        description="3D Spiking Neural Network (SNN) Morphogenetic Engine & CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: generate
    p_gen = subparsers.add_parser("generate", help="Generate 3D SNN population via morphogenetic rules")
    p_gen.add_argument("--neurons", type=int, default=1000, help="Number of neurons (default: 1000)")
    p_gen.add_argument(
        "--morphology",
        choices=["column", "layered", "microcircuit"],
        default="column",
        help="Morphological architecture",
    )
    p_gen.add_argument("--exc-ratio", type=float, default=0.80, help="Excitatory neuron ratio (default: 0.80)")
    p_gen.add_argument("--pace-ratio", type=float, default=0.05, help="Pacemaker driver ratio (default: 0.05)")
    p_gen.add_argument("--radius", type=float, default=30.0, help="Column radius (default: 30.0)")
    p_gen.add_argument("--height", type=float, default=150.0, help="Column height (default: 150.0)")
    p_gen.add_argument("--layers", type=int, default=4, help="Number of layers if layered morphology (default: 4)")
    p_gen.add_argument("--conduction-velocity", type=float, default=4.0, help="Axonal conduction velocity")
    p_gen.add_argument("--seed", type=int, default=42, help="Random seed")
    p_gen.add_argument("--weight-scale", type=float, default=1.0, help="Scale of all base weights (column only; 0.2 = provisional unsaturated regime)")
    p_gen.add_argument("--inh-scale", type=float, default=1.0, help="Extra factor on inhibitory weights (column only)")
    p_gen.add_argument("--refractory", type=int, default=0, help="Absolute refractory period in ticks (column only; 3 = provisional regime)")
    p_gen.add_argument("--out", type=str, default="network.json", help="Output JSON path (default: network.json)")
    p_gen.set_defaults(func=cmd_generate)

    # Subcommand: simulate
    p_sim = subparsers.add_parser("simulate", help="Run integer-only headless SNN simulation")
    p_sim.add_argument("--network", type=str, required=True, help="Input network JSON file")
    p_sim.add_argument("--ticks", type=int, default=1000, help="Ticks to simulate (default: 1000)")
    p_sim.add_argument("--raster", type=str, default=None, help="Output PNG path for spike raster plot")
    p_sim.add_argument("--seed", type=int, default=12345, help="Simulation PRNG seed")
    p_sim.set_defaults(func=cmd_simulate)

    # Subcommand: stats
    p_stat = subparsers.add_parser("stats", help="Compute topology and degree statistics of a network")
    p_stat.add_argument("--network", type=str, required=True, help="Input network JSON file")
    p_stat.set_defaults(func=cmd_stats)

    # Subcommand: export-presets
    p_pre = subparsers.add_parser("export-presets", help="Export standard JSON network presets")
    p_pre.add_argument("--out-dir", type=str, default="presets", help="Output directory (default: presets)")
    p_pre.set_defaults(func=cmd_export_presets)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
