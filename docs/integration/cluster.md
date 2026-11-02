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

```{admonition} PLACEHOLDER
:class: placeholder
A complete cluster recipe (SLURM and a cloud alternative): environment setup, GPU selection, checkpoint / resume of
evolution, gathering islands, and measured scaling of simulate_counts with the number of networks.
```
