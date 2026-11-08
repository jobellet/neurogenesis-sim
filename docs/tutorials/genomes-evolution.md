# Tutorial 4 — Genes and evolution

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/genomes-evolution.ipynb)

## Genes are paths into the genome
```python
from neurogenesis.genome import get_gene, set_gene, guidance_genes, body_genes

set_gene(genome, ("guidance", ("sensor", "map"), "sigma"), 0.2)
set_gene(genome, ("guidance", ("sensor", "map"), "B", 0, 0), 1.5)     # paths reach into arrays
print(get_gene(genome, ("count", "map")))

genes = guidance_genes("sensor", "map") + body_genes("map")          # [(path, low, high), ...]
```
Gene groups collect the genes of one mechanism: `body_genes`, `guidance_genes`, `field_genes`,
`differentiation_genes`, `identity_genes`, `typed_guidance_genes`. You can also write the list by hand.

## [0, 1] coding and JSON
```python
from neurogenesis.genome import to_unit, from_unit, to_json, from_json
u = to_unit(genome, genes)            # numpy vector in [0, 1]
g2 = from_unit(genome, genes, u)      # a new genome (the original is not modified); counts stay integers
d = to_json(g2)                       # JSON-ready: projection keys become "sensor->map"
```

## Evolving one island
`evaluate(genomes, seeds)` returns one fitness per genome and an info dict per genome. **Every generation gets fresh
development seeds**, so the fitness of a genome is about all the networks it can grow, not one lucky individual.

```python
import numpy as np
from neurogenesis.development import grow
from neurogenesis.spiking.batch import simulate_counts
from neurogenesis.evolution import evolve, choose, audit

def evaluate(genomes, seeds):
    fits, infos = [], []
    for g in genomes:
        per_seed = []
        for s in seeds:
            net = grow(plan, g, seed=s)
            counts = simulate_counts([net], [make_stimuli(net)], ticks=50, blank=40)[0]
            per_seed.append(score(counts))          # your task metric
        per_seed = np.asarray(per_seed)
        fits.append(per_seed.min() + 0.25 * per_seed.mean())   # robust: the worst seed matters most
        infos.append(dict(per_seed=per_seed.tolist()))
    return fits, infos

P, history = evolve(genome, genes, evaluate, island=0, pop=32, gens=40, seeds_per_gen=4)
best, info = choose(genome, genes, P, evaluate, seeds=(2000, 2001, 2002, 2003))   # validation seeds
```
Run several islands (`island=0, 1, 2, ...`) in parallel processes and choose among their final populations. Then
**audit** the chosen genome on held-out seeds never used during the search (`neurogenesis.evolution.audit`), including
knockouts that should break the function.

```{figure} ../_static/media/evolution_progress.png
:width: 75%

A small run of `evolve` on the topographic-map example: one island of 12 genomes, 3 fresh development seeds per generation, 4 guidance genes (B[0,0], B[1,1], B[0,1], sigma), toy score = topographic correlation of the projection. Best and median fitness (worst + 0.25 × mean over seeds) per generation.
```

## Before you evolve: a capacity test
Evolution can only find what the architecture can do. First set the genome **by hand** (or with an oracle wiring)
and check that the task is solvable. If it is not, no search will find it, and the time is better spent on the plan.

```{admonition} PLACEHOLDER
:class: placeholder
Tutorial on multi-island runs on a cluster (SLURM array jobs), checkpointing and resuming evolution, and a gallery of
evolved modules with their audit reports.
```
