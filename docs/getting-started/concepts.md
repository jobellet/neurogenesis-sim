# Core concepts

```text
Project (JSON + .npz, versioned schema)
├── Geometry          2D / 3D shapes: primitives, meshes, voxel masks
├── Fields            hand-made or generated data on the geometry (gradients, layers, maps, point sets)
├── Genome            nested dict of genes (numbers addressed by paths), evolvable
├── Schedule          ordered list of stages; each stage = operator + parameters (Params)
└── Plan              the original BodyPlan, still usable (compiled into a default schedule)

Tissue  (struct of arrays that stages transform: positions, lineage, types, expression, signs, connectivity)
   │  developmental stages: seed_cells, proliferate, apoptosis, migrate, sort, express, differentiate,
   │                         grow_axons, prune, scale, myelinate, refine_by_activity, ...
   ▼
SNNNetwork  →  simulate (lif_int | two_compartment | hh)  →  spikes, rates, metrics  →  fitness / fit / module
```

## Body plan
A {py:class}`~neurogenesis.development.BodyPlan` lists **regions** (boxes in space with a placement rule, a role —
internal, input or output — and an optional imposed sign) and the **projections** allowed between them. `grow(plan,
genome, seed)` runs the fixed growth procedure: placement and sign → lateral-inhibition differentiation → molecular
identity → axon guidance. Same plan + genome + seed → the same network, bit for bit.

## Genome and genes
A genome is a nested dictionary of numbers and arrays. A **gene** is a path into it plus bounds, for example
`(("guidance", ("sensor", "map"), "sigma"), 0.02, 0.5)`. Genes are coded in [0, 1] for evolution
({py:func}`~neurogenesis.genome.to_unit`, {py:func}`~neurogenesis.genome.from_unit`) and saved as JSON
(projection keys become `"src->dst"`). Gene groups (`guidance_genes`, `body_genes`, ...) collect the genes of a
mechanism.

## Rules
Rules are small functions in five phases (placement, guidance shift / target / probability, weight) that modify the
growth procedure. A rule is **inactive unless its gene is present**, so adding it to a plan changes no existing
network, and rules never draw random numbers. See {doc}`../development/extending`.

## Stages and schedules (experimental)
A **stage** is a registered operator `Tissue × Params × rng → Tissue`. A **schedule** is an ordered list of stages,
each optionally repeated or conditioned (`when`). Each repetition gets its own random stream, derived from the
development seed and the stage name, so inserting a stage does not change the randomness of the others.

## Params
Every stage parameter is a **Param**, which says where its value comes from:

| Param | Meaning | JSON |
|---|---|---|
| `Const` | set by hand | `{"type": "Const", "value": 0.5}` |
| `Gene` | read from the genome (evolvable) | `{"type": "Gene", "path": ["death", "p"], "lo": 0, "hi": 0.5}` |
| `Field` | read from a field at each cell's position | `{"type": "Field", "name": "gradient", "transform": "log"}` |
| `Fit` | fitted to data (supervised) | `{"type": "Fit", "target": "...", "init": 1, "lo": 0, "hi": 2}` |
| `Expr` | a formula of other values | `{"type": "Expr", "formula": "2 * x"}` |

## Tissue
The {py:class}`~neurogenesis.tissue.Tissue` is the state that stages transform: positions (float64), parent and clone
ids (lineage), birth stage, generation, cycling flag, cell type, region, expression channels, sign, neuron parameters,
alive flag, and sparse connectivity (pre, post, weight, delay). `tissue.to_network()` compiles it into an `SNNNetwork`.

## Spiking network and neuron models
An `SNNNetwork` holds neurons (integer LIF parameters: leak shift, synaptic shift, threshold, refractory period;
or drivers: Poisson, burster) and synapses (weight, delay in ticks of 1 ms, up to 255). The same network runs with
`lif_int` (bit-identical across implementations), `two_compartment` or `hh`. See {doc}`../reference/neuron-models`.

## Evolution
{py:func}`~neurogenesis.evolution.evolve` runs one island: each generation is evaluated on **fresh development
seeds**, so selected genomes must work for every developmental outcome, not one lucky network. `choose` picks the
best on validation seeds, `audit` re-tests on held-out seeds (fitness = worst + 0.25 × mean − cost).

## Modules
A {py:class}`~neurogenesis.modules.Module` = plan + genome + inputs / outputs + validation + provenance + neuron model,
saved as JSON. `compose` assembles modules into a larger system (region names get a prefix, each module keeps its
genes, links add projections).

## Determinism
- Same inputs and seed → identical outputs (development and the integer kernel).
- Float models are deterministic per platform.
- Projects that depend on the toolbox should freeze **fingerprints** of the networks their results come from.
