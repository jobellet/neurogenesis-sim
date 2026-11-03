# neurogenesis-sim

**Grow spiking neural networks the way nervous systems are built, by hand, by genes, or both, and simulate them
cheaply.**
## Documentation
**<https://jobellet.github.io/neurogenesis-sim/>**: tutorials, use cases, integration guides, stage and API
reference, related work. **For AI assistants:** the whole documentation, with a generated status section (what
exists, what is not done, open pull requests), as one Markdown file to paste or upload into a chat:
[neurogenesis-sim-context.md](https://jobellet.github.io/neurogenesis-sim/neurogenesis-sim-context.md) (~70k tokens)
or the short [neurogenesis-sim-brief.md](https://jobellet.github.io/neurogenesis-sim/neurogenesis-sim-brief.md)
(~11k tokens); `python scripts/build_context.py` makes them locally. The site is built from `docs/` by `.github/workflows/docs.yml`; to build it locally:
`pip install -r docs/requirements.txt && sphinx-build -b html docs docs/_build/html`. Key files:
- `docs/ROADMAP.md`: target architecture (geometry, fields, tissue, stages, parameter sources, GUI), design rules and
  the task list.
- `AGENTS.md`: rules for contributors and agents (determinism, backward compatibility, low compute, tests).
- `docs/EXTENDING.md`: rules, plugins, knockouts, tonic currents, module projects.
- `docs/STAGES.md`: the registered stages, geometries, fields and sparse guidance: parameters, defaults, limits.
- `docs/NEURON_MODELS.md`: neuron models, units, cost estimates.
- `CONTRIBUTING.md`: code and module contributions.
- `docs/THIRD_PARTY.md`: software used and the literature behind each mechanism.
  
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

**Status (2026-11-02).** Implemented and tested: the spiking kernels and neuron models, cost estimates, genomes and
evolution, modules with a registry and validation assays, geometries and fields, a configurable schedule of developmental
stages (`docs/STAGES.md`), supervised fitting (CMA-ES), connectome data import, pharmacology profiles, branching arbors
with SWC I/O, SONATA export / import, the bridge, the browser viewer and the macOS app. In progress: the Windows / Linux
app (H5). Planned: the remaining stages of the second wave (C19, C20), further export formats (J3–J5: NIR, PyNN,
NeuroML 2), and lifting the remaining 31-tick delay clip in arbor synapses and the connectome importer (K4b; other
stages accept delays up to 255 ticks). Configurable stages are
young and their API may still change. Everything open is in `docs/ROADMAP.md` (tasks for parallel development, rules in
`AGENTS.md`); the generated status section of the AI context file (`scripts/build_context.py`) lists it in one place.

## What exists today
| Piece | Module | What it is |
|---|---|---|
| Spiking kernel | `neurogenesis.spiking` | Integer LIF neurons (bit-shift leak and synaptic decay, per-neuron threshold, refractory period, Poisson drivers, bursters, axonal delays up to 255 ticks through a multi-word spike history, neuron indices up to 2³², an array-backed synapse store). Identical spikes in Python (`reference`), JAX (`jax_backend`, CPU or GPU), the browser and the C library `nglif`. `batch.simulate_counts` runs many networks on sequences of stimuli. |
| Neuron models | `neurogenesis.spiking.models` | `lif_int` (default), `two_compartment` (soma + dendrite) and `hh` (Hodgkin–Huxley), switchable per simulation on the same network, sharing synapses, delays and drivers. See `docs/NEURON_MODELS.md`. |
| Cost estimates | `neurogenesis.cost` | Memory and time per model before running, calibrated on the actual machine (`python -m neurogenesis estimate --neurons 3e8 --synapses-per-neuron 5000`). Every simulation refuses networks that cannot fit. |
| Body plans and growth | `neurogenesis.development` | Regions (fixed or grown placement, roles, imposed sign) and allowed projections; one growth procedure: placement and sign → lateral-inhibition differentiation → molecular identity → axon guidance. Deterministic per development seed; parallel growth. |
| Developmental rules | `neurogenesis.development.rules` | Extension points in 5 phases. **placement:** mosaics. **guidance shift / target / probability:** identity-dependent targets and receptor expression, point-to-point topography, laminar targeting, no autapse, sign-specific projections. **weight:** sign-inverting receptors. Each rule is inactive unless its gene is present; plugins travel with plans. |
| Knockouts, tonic currents | `neurogenesis.development` | `knockout(genome, regions, projections)`; standing currents per cell type (`genome["tonic"]`). |
| Genomes | `neurogenesis.genome` | Nested dicts; genes addressed by paths (into arrays too), coded in [0, 1] for evolution, grouped by mechanism, saved as JSON. |
| Evolution | `neurogenesis.evolution` | Island model with fresh development seeds each generation; choice on validation seeds; audits on held-out seeds (fitness = worst + 0.25 × mean − cost). |
| Modules | `neurogenesis.modules` | `Module` = plan + genome + inputs / outputs + validation + provenance + neuron model + version, saved as JSON; `compose` assembles modules (prefixed names, each keeps its genes, plugins and rules merged); a local registry (`python -m neurogenesis install`, `registry.get`). |
| Validation | `neurogenesis.validation` | Declarative assays stored in modules (stimuli per region, readout, metric, gate, knockouts), rerun by `python -m neurogenesis validate module.json`. |
| Fitting | `neurogenesis.fitting`, `neurogenesis.evolution.semi_supervised` | `Fit` params fitted to data targets (cell counts, densities, layer thickness, connection statistics, firing rates) with CMA-ES over several development seeds (`python -m neurogenesis fit`); genes evolved with an inner fitting loop; Pareto evolution. |
| Development schedule | `neurogenesis.stages`, `neurogenesis.devcost` | A Project's ordered stages (seed, cell_cycle_clock, proliferate, apoptosis, migrate, sort, mosaic, express, temporal_competence, differentiate, critical_period_gate, grow_axons, fasciculate, choice_point, place / connect by hand, prune, scale, refine_by_activity, competitive_elimination, myelinate, freeze), each parameter a `Param`; cost per stage before running (`python -m neurogenesis estimate --project p.json`). Chunked growth streamed to disk for very large tissues (`neurogenesis.streaming`). See `docs/STAGES.md`. |
| Arbors, pharmacology, data | `neurogenesis.arbors`, `neurogenesis.pharmacology`, `neurogenesis.data` | Branching arbors (SWC I/O, `grow_arbors`, synapses with path-length delays); transmitter / receptor profiles compiled to signed weights by developmental context, and a per-cell chloride reversal potential that switches with maturation (`transporter_switch`); connectome manifests, verified downloads and streaming import (`python -m neurogenesis data fetch`); volume-transmitted neuromodulation (`neurogenesis.neuromodulation`) and passive dendritic attenuation (`neurogenesis.dendritic`). |
| Geometry and fields | `neurogenesis.geometry`, `neurogenesis.fields` | Primitives, CSG, meshes and voxel masks (`.npz`); grid, analytic, vector, label, layer-stack and pinwheel fields, gradients and distances; every field usable as a `Param`. |
| Interoperability | `neurogenesis.interop` | Export / import with a report of what is exact, approximated or dropped: SONATA (`python -m neurogenesis export net.json --format sonata --out dir`), exact round trip; one shared translation of the integer neuron into a current-based exponential LIF. |
| Bridge and apps | `neurogenesis.bridge`, `desktop/` | JSON-lines server (`python -m neurogenesis.bridge`), NGB1 binary networks, UI schema export (`python -m neurogenesis ui-schema`); native macOS app; Windows / Linux app in progress. |
| Analysis | `neurogenesis.analysis` | Frequency–current curves (from rest), mosaic regularity. |
| Viewer | `viz/` | Browser 3D viewer and sandbox (three.js): imports network JSON, shows neurons by role and sign, rasters, per-neuron inspection and editing. |

## Install and try
```
pip install -e ".[test]"                    # Python >= 3.10: numpy, jax (CPU; "jax[cuda12]" for GPU), matplotlib
cd viz && npm ci && npm run build:kernel && cd ..   # browser kernel, for the equivalence tests
JAX_PLATFORMS=cpu pytest -q
python examples/topographic_map.py --cpu    # a sensor sheet -> map circuit grown from a genome
python examples/hand_built_network.py      # supervised: every cell and synapse by hand
python examples/hand_drawn_column.py --cpu # semi-supervised: hand-drawn layers, genes choose cell types
python examples/pinwheel_sheet.py --cpu    # semi-supervised: density follows hand-placed pinwheels
python examples/evolved_development.py     # unsupervised: a genetic schedule evolved on a toy objective
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

## Continuous integration
GitHub Actions (`.github/workflows/ci.yml`), on every push:
- every test on Python 3.10 and 3.12;
- the browser kernel compiled, so that the Python / JAX / browser equivalence tests run and are never skipped;
- fixed CPU performance benchmarks on main, reported against the previous main run on the same machine type (report only; a regression above 30% is flagged);
- the cost estimator from the command line;
- the viewer type-checked and built.

## Reproducibility
- Same plan + genome + development seed → the same network, bit for bit.
- Same network + kernel seed → the same `lif_int` spikes in Python, JAX and the browser. Float models are deterministic
  per platform.
- Projects that depend on the toolbox should freeze fingerprints of the networks their results come from, and test them.

## Citing
See `CITATION.cff` (GitHub's "Cite this repository" button), and cite the methods and datasets you use
(`docs/THIRD_PARTY.md`).

## Licence
MIT (`LICENSE`). Third-party software and data keep their own licences (`docs/THIRD_PARTY.md`).
