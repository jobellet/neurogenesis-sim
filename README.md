# neurogenesis-sim

**Grow spiking neural networks the way nervous systems are built, by hand, by genes, or both, and simulate them
cheaply.**

neurogenesis-sim is a general toolbox for building circuits through development. You describe where tissue is (2D or 3D
shapes) and what is already known about it (layers, areas, maps, cell positions). You then choose a sequence of
developmental stages (cell division, migration, differentiation, axon growth, pruning, activity-dependent refinement
...), and for every parameter of every stage you decide whether it is:
- set **by hand**;
- read from a **hand-drawn field** (for example a layer boundary or an orientation map);
- controlled by **genes** (and then evolved);
- or **fitted to data**.

The result is an integer leaky integrate-and-fire network, or a more detailed one, that can be simulated, measured,
evolved and shared as a module.

| Workflow | What you specify | What development does |
|---|---|---|
| Supervised (by hand) | geometry, cells, connections or connection rules | compiles and simulates exactly what you specified |
| Unsupervised (genetic) | a genome and a schedule of stages | genes control every stage; evolution searches genomes that work for every developmental seed |
| Semi-supervised | a hand-made scaffold (e.g. cortical layers, cytochrome-oxidase blobs, pinwheel centres) plus a schedule | genes and fitted parameters work on top of the scaffold |

The toolbox makes no assumption about species, organ, task or environment. Projects that use it define their own
geometries, stages, stimuli and objectives, and can publish working circuits (for example a retina with ON/OFF ganglion
cells) as modules that others reuse as-is.

**Status (2026-11-01).** The spiking kernel, neuron models, cost estimates, body plans with a fixed growth procedure,
genomes, evolution, modules and a 3D viewer exist and are tested. Geometries, fields, configurable developmental stages,
supervised fitting and the GUI editors are planned: see `docs/ROADMAP.md`, written as tasks for parallel development
(and `AGENTS.md` for the rules every contributor follows).

## What exists today
| Piece | Module | What it is |
|---|---|---|
| Spiking kernel | `neurogenesis.spiking` | Integer LIF neurons (bit-shift leak and synaptic decay, per-neuron threshold, refractory period, Poisson drivers, bursters, axonal delays up to 31 ticks of 1 ms). Identical spikes in Python (`reference`), JAX (`jax_backend`, CPU or GPU) and the browser. `batch.simulate_counts` runs many networks on sequences of stimuli. |
| Neuron models | `neurogenesis.spiking.models` | `lif_int` (default), `two_compartment` (soma + dendrite) and `hh` (Hodgkin–Huxley), switchable per simulation on the same network, sharing synapses, delays and drivers. See `docs/NEURON_MODELS.md`. |
| Cost estimates | `neurogenesis.cost` | Memory and time per model before running, calibrated on the actual machine (`python -m neurogenesis estimate --neurons 3e8 --synapses-per-neuron 5000`). Every simulation refuses networks that cannot fit. |
| Body plans and growth | `neurogenesis.development` | Regions (fixed or grown placement, roles, imposed sign) and allowed projections; one growth procedure: placement and sign → lateral-inhibition differentiation → molecular identity → axon guidance. Deterministic per development seed; parallel growth. |
| Developmental rules | `neurogenesis.development.rules` | Extension points in 5 phases. **placement:** mosaics. **guidance shift / target / probability:** identity-dependent targets and receptor expression, point-to-point topography, laminar targeting, no autapse, sign-specific projections. **weight:** sign-inverting receptors. Each rule is inactive unless its gene is present; plugins travel with plans. |
| Knockouts, tonic currents | `neurogenesis.development` | `knockout(genome, regions, projections)`; standing currents per cell type (`genome["tonic"]`). |
| Genomes | `neurogenesis.genome` | Nested dicts; genes addressed by paths (into arrays too), coded in [0, 1] for evolution, grouped by mechanism, saved as JSON. |
| Evolution | `neurogenesis.evolution` | Island model with fresh development seeds each generation; choice on validation seeds; audits on held-out seeds (fitness = worst + 0.25 × mean − cost). |
| Modules | `neurogenesis.modules` | `Module` = plan + genome + inputs / outputs + validation + provenance + neuron model, saved as JSON; `compose` assembles modules (prefixed names, each keeps its genes, plugins and rules merged). |
| Analysis | `neurogenesis.analysis` | Frequency–current curves (from rest), mosaic regularity. |
| Viewer | `viz/` | Browser 3D viewer and sandbox (three.js): imports network JSON, shows neurons by role and sign, rasters, per-neuron inspection and editing. |

## Install and try
```
pip install -e ".[test]"                    # Python >= 3.10: numpy, jax (CPU; "jax[cuda12]" for GPU), matplotlib
cd viz && npm ci && npm run build:kernel && cd ..   # browser kernel, for the equivalence tests
JAX_PLATFORMS=cpu pytest -q
python examples/topographic_map.py --cpu    # a sensor sheet -> map circuit grown from a genome
python -m neurogenesis estimate --neurons 1e5 --synapses-per-neuron 1000 --seconds 1
cd viz && npm run dev                       # viewer at http://localhost:5173; import example_out/network.json
```

```python
from neurogenesis.development import BodyPlan, FixedPlacement, Region, grow
from neurogenesis.spiking.batch import simulate_counts
from neurogenesis.modules import Module

plan = BodyPlan("demo", regions=[Region("sensor", (0, 0, 0), (30, 30, 5), FixedPlacement(labels), role=1),
                                 Region("map", (50, 0, 0), (30, 30, 10))], projections=[("sensor", "map")])
net = grow(plan, genome, seed=0)                              # an SNNNetwork; net.save_json("network.json")
counts = simulate_counts([net], [currents], ticks=100, model="lif_int")   # or "two_compartment", "hh"
Module("demo", plan, genome, inputs=["sensor"], outputs=["map"]).save("demo.module.json")
```

## Documentation
- `docs/ROADMAP.md`: target architecture (geometry, fields, tissue, stages, parameter sources, GUI), design rules and
  the task list.
- `AGENTS.md`: rules for contributors and agents (determinism, backward compatibility, low compute, tests).
- `docs/EXTENDING.md`: rules, plugins, knockouts, tonic currents, module projects.
- `docs/NEURON_MODELS.md`: neuron models, units, cost estimates.
- `CONTRIBUTING.md`: code and module contributions.
- `docs/THIRD_PARTY.md`: software used and the literature behind each mechanism.

## Continuous integration
GitHub Actions (`.github/workflows/ci.yml`), on every push:
- every test on Python 3.10 and 3.12;
- the browser kernel compiled, so that the Python / JAX / browser equivalence tests run and are never skipped;
- the cost estimator from the command line;
- the viewer type-checked and built.

## Reproducibility
- Same plan + genome + development seed → the same network, bit for bit.
- Same network + kernel seed → the same `lif_int` spikes in Python, JAX and the browser. Float models are deterministic
  per platform.
- Projects that depend on the toolbox should freeze fingerprints of the networks their results come from, and test them.

## Licence
MIT (`LICENSE`).
