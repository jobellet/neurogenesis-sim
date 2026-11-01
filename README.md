# neurogenesis-sim

Spiking neural networks grown from genes. A **body plan** says which regions exist and which projections may grow
between them. A **genome** sets everything that develops: neuron numbers, migration, cell fates, molecular identities
and axon guidance. **Development** turns the two into an integer leaky integrate-and-fire network. **Evolution** searches
genomes that work in every individual they grow, whatever the developmental randomness. **Modules** package a plan, a
genome and their validation, so that a working circuit (for example a retina) can be reused by others as-is.

The toolbox makes no assumption about species, task or environment; projects that use it define their own plans,
stimuli and objectives.

## Install
```
pip install -e .                 # Python >= 3.10: numpy, jax (CPU; on GPU install "jax[cuda12]"), matplotlib
pip install -e ".[test]" && pytest
cd viz && npm ci && npm run dev  # 3D viewer at http://localhost:5173 (Node >= 18)
```

## Concepts
| Piece | Module | What it is |
|---|---|---|
| Spiking kernel | `neurogenesis.spiking` | Integer LIF neurons: bit-shift leak and synaptic decay, per-neuron threshold, refractory period, Poisson drivers, intrinsic bursters, axonal delays up to 31 ticks. Three implementations give the same spikes bit for bit: `reference` (Python), `jax_backend` (CPU or GPU, `jax.vmap` over networks) and the browser kernel (`viz/src/sim/kernel.ts`). `batch.simulate_counts` runs many networks on sequences of stimuli. |
| Neuron models | `neurogenesis.spiking.models` | `lif_int` (default), `two_compartment` (soma + dendrite) and `hh` (Hodgkin–Huxley), switchable per simulation on the same grown network (`simulate_counts(..., model=)`), with the same synapses, delays and drivers. See `docs/NEURON_MODELS.md`. |
| Cost estimates | `neurogenesis.cost` | Memory and time of a simulation per model, before running it, calibrated on the actual machine (`python -m neurogenesis estimate --neurons 3e8 --synapses-per-neuron 5000`). Every simulation refuses networks that cannot fit. |
| Body plan | `neurogenesis.development.BodyPlan` | Regions (`Region`: box in space, fixed or grown placement, role input / internal / output, imposed sign, refractory period) and allowed projections, in growth order. Plain data, saved as JSON. |
| Genome | `neurogenesis.genome` | A nested dict. Genes are addressed by paths (`("guidance", ("a", "b"), "B", 0, 1)`), coded in [0, 1] for evolution (`from_unit`, `to_unit`) and grouped by mechanism (`guidance_genes`, `body_genes`, `differentiation_genes`, `identity_genes`, ...). |
| Development | `neurogenesis.development.grow` | Placement and sign → differentiation (lateral inhibition, Notch–Delta type) → molecular identity → axon growth (positional chemoaffinity plus registered guidance rules). Deterministic for a given development seed; `grow_many` grows in parallel processes with identical results. |
| Developmental rules | `neurogenesis.development.rules` | The extension points of growth, in five phases: placement (e.g. mosaics), guidance shift / target / probability (identity-dependent targets and receptor expression, point-to-point topography, laminar targeting, no autapse, projections made only by excitatory or inhibitory neurons), and synaptic weight (e.g. sign-inverting receptors). Each built-in rule acts only when its gene is present. New mechanisms: `@register(phase, name)`, listed in the plan, shipped as plan `plugins`. See `docs/EXTENDING.md`. |
| Knockouts, tonic currents | `neurogenesis.development` | `knockout(genome, regions, projections)` for virtual knockouts; `tonic_current` for standing currents of cell types (`genome["tonic"]`). |
| Evolution | `neurogenesis.evolution` | Island model on [0, 1] gene vectors with fresh development seeds every generation; choice on validation seeds; audits on held-out seeds (`robust_value` = worst + 0.25 × mean − cost). |
| Modules | `neurogenesis.modules` | `Module` = plan + genome + inputs / outputs + validation + provenance, saved as JSON (`neurogenesis-module/1`). `compose` assembles modules into a larger system: region names are prefixed, each module keeps its genes, and links add new projections. |
| Viewer | `viz/` | Browser sandbox (three.js): imports any network JSON, shows neurons by role and sign, rasters, per-neuron inspection and editing. |

## Minimal example
```
python examples/topographic_map.py --cpu
```
grows a sensor sheet → map circuit, stimulates two corners, prints where the map responds, and writes
`example_out/network.json` (open it in the viewer) and `example_out/module.json` (a shareable module).

```python
from neurogenesis.development import BodyPlan, FixedPlacement, Region, grow
from neurogenesis.modules import Module

plan = BodyPlan("demo", regions=[Region("sensor", (0, 0, 0), (30, 30, 5), FixedPlacement(labels), role=1),
                                 Region("map", (50, 0, 0), (30, 30, 10))], projections=[("sensor", "map")])
net = grow(plan, genome, seed=0)            # an SNNNetwork; net.save_json("network.json") for the viewer
Module("demo", plan, genome, inputs=["sensor"], outputs=["map"]).save("demo.module.json")
```

## Continuous integration
GitHub Actions (`.github/workflows/ci.yml`), on every push:
- every test on Python 3.10 and 3.12: every neuron model, development, evolution, modules and cost estimates;
- the browser kernel compiled, so that the Python / JAX / browser equivalence tests run and are never skipped;
- the cost estimator from the command line;
- the 3D viewer type-checked and built.

## Reproducibility
- Same plan + genome + development seed → the same network, bit for bit (tests: `tests/test_development.py`).
- Same network + kernel seed → the same spikes in Python, JAX and the browser (`tests/test_kernel.py`; the browser test
  needs `cd viz && npm run build:kernel` once).
- Projects that depend on the toolbox should freeze fingerprints of the networks their results come from, and test them.

## Extending
`docs/EXTENDING.md`: where new biology goes (regions, rules, plugins), how to organise a module project (plan, assay,
capacity test, evolution, audit with knockouts), and how to compose other people's modules.

## Contributing a module
See `CONTRIBUTING.md`: a module comes with its plan, genome, interface, the stimuli and metrics used to validate it, and
its pass rate on development seeds never used during its design or evolution.

## Licence
MIT (`LICENSE`). Third-party software and the literature behind each mechanism: `docs/THIRD_PARTY.md`.
