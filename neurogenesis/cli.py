"""Command Line Interface (CLI) for SNN Morphogenetic Network Generation & Simulation.

Usage:
  python -m neurogenesis generate --neurons 1000 --morphology column --out network.json
  python -m neurogenesis simulate --network network.json --ticks 1000 --raster raster.png
  python -m neurogenesis stats --network network.json
  python -m neurogenesis export-presets --out-dir presets/
  python -m neurogenesis generate --neurons 500 --weight-scale 0.2 --refractory 3 --out column_unsaturated.json
  python -m neurogenesis estimate --project project.json
  python -m neurogenesis fit --project project.json --targets targets.json --out genome.json
  python -m neurogenesis validate module.json
  python -m neurogenesis install module.json
"""

from __future__ import annotations

import argparse
import json
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


def cmd_estimate(args: argparse.Namespace) -> None:
    """Memory and time of a simulation for each neuron model, on this machine (calibrates once per model and device);
    with --project, of a development schedule (per stage)."""
    if args.project:
        from .devcost import estimate_development, format_rows
        from .project.io import Project
        project = Project.load(args.project).to_dict()
        e = estimate_development(project, calibrated=not args.no_calibrate)
        print(format_rows(e))
        print(e["verdict"])
        if not e["fits"]:
            raise SystemExit(2)
        if not args.neurons:
            return
    if not args.neurons:
        raise SystemExit("estimate: give --neurons or --project")
    from .cost import estimate
    n = int(float(args.neurons))
    e = int(n * float(args.synapses_per_neuron))
    ticks = int(float(args.seconds) * 1000)
    models = args.model or ["lif_int", "two_compartment", "hh"]
    print(f"{n:,} neurons, {e:,} synapses, {args.seconds} simulated s ({ticks:,} ticks of 1 ms)")
    for m in models:
        r = estimate(m, n, e, ticks)
        print(f"  {m:16s} {r['verdict']}")


def cmd_fit(args: argparse.Namespace) -> None:
    """Fits a Project's Fit params to targets (E2); writes the genome with the fitted values."""
    from .fitting import fit
    from .genome.io import from_json, to_json
    from .project.io import Project
    project = Project.load(args.project)
    targets = json.loads(Path(args.targets).read_text())
    targets = targets.get("targets", targets) if isinstance(targets, dict) else targets
    seeds = [int(s) for s in args.seeds.split(",")]
    r = fit(project.to_dict(), targets, seeds=seeds, genome=project.genome, iterations=args.iterations, seed=args.seed,
            log=lambda h: print(f"  iteration {h['iteration']:3d}  best loss {h['best']:.4g}"))
    for k, v in r.values.items():
        print(f"{k} = {v:.6g}")
    print(f"loss {r.loss:.4g}; metrics per seed: {r.metrics}")
    Path(args.out).write_text(json.dumps(to_json(r.genome), indent=1))
    print(f"✓ genome with fitted values saved to {Path(args.out).resolve()}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Reruns the assays stored in a module (E4); exit status 1 if any fails."""
    from .modules.module import Module
    from .validation import validate_module
    module = Module.load(args.module)
    assays = None
    if args.assays:
        a = json.loads(Path(args.assays).read_text())
        assays = a.get("assays", a) if isinstance(a, dict) else a
    results = validate_module(module, assays)
    if not results:
        print(f"{module.name}: no assays (add them to validation['assays'])")
    for r in results:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']}: pass fraction {r['pass_fraction']:.2f}, values {r['values']}")
    if any(not r["ok"] for r in results):
        raise SystemExit(1)


def cmd_install(args: argparse.Namespace) -> None:
    from .modules.registry import install
    e = install(args.module, catalogue=args.catalogue, force=args.force)
    print(f"✓ installed {e['name']} {e['version']} (toolbox {e['toolbox']})")


def cmd_modules(args: argparse.Namespace) -> None:
    from .modules.registry import list_modules
    for e in list_modules(args.catalogue):
        print(f"{e['name']:24s} {e['version']:10s} toolbox {e['toolbox']:14s} {e.get('description', '')[:60]}")


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

    # Subcommand: estimate
    p_est = subparsers.add_parser("estimate", help="Memory and time of a simulation per neuron model, before running it")
    p_est.add_argument("--neurons", help="number of neurons (e.g. 3e8)")
    p_est.add_argument("--project", help="Project JSON: estimate its development schedule, stage by stage")
    p_est.add_argument("--no-calibrate", action="store_true", help="do not run the development benchmark (time unknown until calibrated)")
    p_est.add_argument("--synapses-per-neuron", default="1000", help="mean number of synapses per neuron")
    p_est.add_argument("--seconds", default="1", help="simulated seconds")
    p_est.add_argument("--model", action="append", help="neuron model (repeatable; default: all)")
    p_est.set_defaults(func=cmd_estimate)

    p_fit = subparsers.add_parser("fit", help="Fit a Project's Fit params to data targets (CMA-ES)")
    p_fit.add_argument("--project", required=True, help="Project JSON")
    p_fit.add_argument("--targets", required=True, help="JSON list of targets (or {\"targets\": [...]})")
    p_fit.add_argument("--seeds", default="0,1,2", help="development seeds per evaluation (comma-separated)")
    p_fit.add_argument("--iterations", type=int, default=30)
    p_fit.add_argument("--seed", type=int, default=0, help="optimiser seed")
    p_fit.add_argument("--out", default="fitted_genome.json")
    p_fit.set_defaults(func=cmd_fit)

    p_val = subparsers.add_parser("validate", help="Rerun the validation assays of a module")
    p_val.add_argument("module", help="module JSON")
    p_val.add_argument("--assays", help="JSON list of assays to run instead of the module's own")
    p_val.set_defaults(func=cmd_validate)

    p_ins = subparsers.add_parser("install", help="Install a module into the local catalogue")
    p_ins.add_argument("module", help="module JSON")
    p_ins.add_argument("--catalogue", help="catalogue directory (default $NEUROGENESIS_MODULES or ~/.cache/neurogenesis/modules)")
    p_ins.add_argument("--force", action="store_true", help="replace an installed module of the same version")
    p_ins.set_defaults(func=cmd_install)

    p_mod = subparsers.add_parser("modules", help="List installed modules")
    p_mod.add_argument("--catalogue", help="catalogue directory")
    p_mod.set_defaults(func=cmd_modules)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
