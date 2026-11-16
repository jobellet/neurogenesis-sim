# Large batches and clusters

- **Batched simulation.** `simulate_counts(nets, stimuli, ...)` pads and stacks many networks and runs them in one JAX
  call, on CPU or GPU. Use it for populations in evolution.
- **Parallel growth.** `neurogenesis.development.parallel.grow_many(calls)` grows many (plan, genome, seed) calls in
  worker processes (`set_workers(n)` sets their number).
- **Islands.** Run one evolution island per process or per job (`island=0, 1, ...`; the development seeds of islands
  never overlap), then `choose` among the final populations on validation seeds.
- **Cost first.** `python -m neurogenesis estimate` (or `neurogenesis.cost.check`) before submitting large jobs; the
  calibration cache is per machine, so calibrate on the compute node.

```bash
# one island per SLURM array task
#SBATCH --array=0-7
JAX_PLATFORMS=cpu python scripts/evolve.py --island $SLURM_ARRAY_TASK_ID --out runs/island_$SLURM_ARRAY_TASK_ID
```

## Environment setup and GPU selection
On CPU nodes, pin `JAX_PLATFORMS=cpu` so JAX does not warn or probe for absent GPUs. On GPU nodes, install
`pip install -U "jax[cuda12]"` in a clean virtual environment, select a single GPU via `CUDA_VISIBLE_DEVICES=$SLURM_LOCALID`,
and prevent XLA from pre-allocating all device RAM when sharing a node:

```bash
export XLA_PYTHON_CLIENT_MEM_FRACTION=0.75
python -m neurogenesis estimate --neurons 1e5 --synapses-per-neuron 1000 --seconds 1
```

Because `neurogenesis.cost` caches calibration constants per device in `~/.cache/neurogenesis/throughput.json`, run
`estimate` once on the compute node (or set `NEUROGENESIS_CACHE` to a node-local scratch directory).

## Checkpointing, resuming, and gathering islands
Each island can save its population (`to_json`) after every generation (or in `log`) and resume from the last saved
generation if a SLURM job hits its wall-time limit:

```python
import json
from pathlib import Path
from neurogenesis.evolution import audit, choose, evolve, HELD_OUT, VALIDATION
from neurogenesis.genome import from_json, from_unit, to_json, to_unit

# Inside each SLURM array worker (island = SLURM_ARRAY_TASK_ID):
ckpt = Path(f"runs/island_{island}.json")
u0 = np.asarray(json.loads(ckpt.read_text())["pop_u"]) if ckpt.exists() else None
# Pass u0 as starting population or evolve in chunks of 10 generations, saving P and history after each chunk.
pop, hist = evolve(founder, genes, evaluate, island=island, pop=32, gens=40, seeds_per_gen=4)
ckpt.write_text(json.dumps({"island": island, "pop_u": pop.tolist(), "best": hist[-1]["best"]}))
```

Once all array jobs finish, gather all island populations in a single post-processing job and run `choose` on validation
seeds followed by `audit` on held-out seeds (`neurogenesis.evolution.robust`):

```python
all_u = np.vstack([np.asarray(json.loads(p.read_text())["pop_u"]) for p in sorted(Path("runs").glob("island_*.json"))])
best_genome, val_info = choose(founder, genes, all_u, evaluate, seeds=VALIDATION)
report = audit(evaluate_one, best_genome, seeds=HELD_OUT)
```

## Measured batch scaling of `simulate_counts`
`simulate_counts` pads networks to multiples of 128 neurons and power-of-2 synapse buckets, compiling each bucket shape
once and running the batch in a single vectorized JAX `vmap` call. Measured on a laptop CPU (`N = 200` neurons,
`1,149` synapses, `100` ticks, after XLA compilation):

| Batch size (`B` networks) | Total wall time (ms) | Time per network (ms) |
|---|---|---|
| 1 | 16.69 | 16.69 |
| 2 | 18.47 | 9.24 |
| 4 | 32.86 | 8.22 |
| 16 | 147.81 | 9.24 |
| 32 | 276.34 | 8.64 |
| 64 | 826.66 | 12.92 |
