# Changelog

## Unreleased (November 2026)
- Fix: cell selectors given to `grow_arbors` (`cells`), `secrete_cue` (`cells`) and `refine_by_activity` (wave `cells`)
  through `run_schedule` arrive as `Const(dict)` and were ignored (every cell selected); they now select. `refine_by_activity`
  `sources` also accepts a {region, cell_type} selector (before: cell ids only). Projects that relied on the old behaviour
  get it back by omitting the selector (`tests/test_schedule_selectors.py`).
- Cues released by cells and two-phase arbor growth (C27): `secrete_cue` (`neurogenesis.stages.guidance`) makes selected
  cells (by type or ligand expression) or their arbor terminals sources of a `CueField` (exp(−r/λ), cell-list
  evaluation); `grow_arbors` gains `guidance` (several cues, per-cell receptor gains from expression, unit or relative
  gradient sensing) and a pathfinding → arbor switch at a target threshold (`target_field`, `arbor_*`,
  `confine_to_target`). Off by default; existing networks unchanged (`tests/test_cell_cues.py`). Rationale and
  references: `docs/background/cell-cues-and-target-recognition.md`.
- `neurogenesis.spiking.currents`: slow intrinsic currents without Hodgkin–Huxley gates, given to any model as external
  current: `t_current` (low-threshold burst current, integrate-and-fire-or-burst form) and `recovery_current` (one linear
  recovery variable: sag, resonance, adaptation). Zero with neutral parameters (`tests/test_currents.py`,
  `docs/NEURON_MODELS.md`).
- Neuromorphic Intermediate Representation (NIR) export and import (J3, `neurogenesis.interop.nir`):
  - `export_nir(net, path, **opts)` and `import_nir(path)` registered in `neurogenesis.interop` (`format="nir"`).
  - Translates integer LIF networks into NIR computation graphs using `nir.CubaLIF` nodes with continuous-time ODE parameters from the shared dynamics mapping.
  - Segregates Poisson / burster drivers into dedicated external input channels (`drivers="input"`) or drops them with explicit warnings (`drivers="drop"`).
  - Honest `ExportReport` telemetry detailing exact parameters, approximations (discretisation, missing refractory periods/delays), and dropped attributes.
  - Low-compute enforcement: dense weight matrices bounded at $N \le 2048$ cells ($O(N^2)$ scaling invariant).
  - Round-trip support reconstructing valid `SNNNetwork` instances from NIR graphs.
- Partner selection stage (C18, `partner_select` in `neurogenesis.stages.partner`, PR #89):
  - Recognition channels and transmitter-receptor compatibility filtering on candidate synapses.
- Configurable development: Project schema (A1), Tissue (A2), Params and stage scheduler (A3, A4), legacy plans
  compiled into schedules with identical networks (A5).
- Geometry (primitives, CSG, meshes, voxel masks) and fields (grids, analytic fields, layer stacks, operations, maps).
- Stage library C1–C12 (experimental; fix wave in progress).
- Cell list (D1) and sparse guidance (D2); online plasticity (E1).
- Bridge (`python -m neurogenesis.bridge`), NGB1 format, portable C kernel `nglif` with golden fixtures, macOS app.
- This documentation site.
- Analysis package `neurogenesis.analysis` (measures only, one module per kind: `cells`, `structure`, `criticality`;
  old imports kept): modularity, within-group fraction and synapse lengths; criticality measures (branching parameter
  by multistep regression, avalanche exponents with KS-chosen xmin, crackling scaling relation). Package layout page
  (grow / simulate / measure).
- `neurogenesis.spiking.numba_backend`: event-driven CPU kernel with the same `lif_int` spikes (optional extra `fast`).
- `express` weight matrices accept Genes; `arbor_synapses` `max_delay` and `axon_velocity_by_type`.
- `neurogenesis.analysis.geometry`: cross-validated PCA (`cvpca`), participation ratio, connectivity dimensionality.
- `neurogenesis.evolution.strategies.evolve_es`: evolution strategies on [0, 1] gene vectors, beside the island model
  (Salimans et al. 2017): one centre, antithetic variants evaluated on the same seeds, centred-rank or z-score shaping,
  SGD or Adam steps, frozen genes; the centre is evaluated every generation. Same `evaluate(genomes, seeds)` as
  `islands.evolve` (`tests/test_evolution_strategies.py`).
- Front page (J12, part): a browser playground that grows and evolves a toy cortical map with a JavaScript port of the
  toolbox (`docs/_static/ngjs/ng-core.js`: the `lif_int` kernel with spikes identical to Python, gene coding,
  `seeds_of`, `coactivity`, competitive elimination, 2D stages) and animates the founder and the champion through six
  stages (`docs/getting-started/playground.md`). It replaces the scripted animation, whose fitness curve and readout
  were drawn, not computed; the front-page code example now uses functions that exist and runs
  (`tests/test_docs_playground.py`), and the figure captions describe what the figures show.
- Fixes to the discovery platform (PR #107):
  - `set_gene` and `from_unit` again raise `KeyError` on a gene path missing from the genome (a misspelled gene no
    longer becomes a silent dead gene); `create=True` adds missing keys.
  - `collect_project_genes` and `collect_fits` include the `pharmacology` and `drugs` sections in `neurogenesis.params`
    itself, instead of `neurogenesis.fitting` replacing them at import (their result depended on whether `fitting` had
    been imported).
  - The 1.2.0 Project sections (`targets`, `compute_cost`, `provenance`) are fields of `Project`, instead of being
    patched in at validation time.
  - The duplicate catalogue card `cortical_alpha_microcircuit.json` is removed.
  - Viewer, live target score: the dominant frequency and the variability index are computed by the simulation worker
    at 1-ms resolution, in simulated time (`viz/src/sim/rhythm.ts`). Before, they came from one tick's spike count
    sampled once per display frame (about 20 simulated ms), with frequencies computed as if each sample were 1 ms.
    The E/I and arbor sliders scale the baseline adjacency weights instead of compounding on already-scaled ones.

## Earlier (0.1.0 baseline)
- Integer LIF kernel (`lif_int`) with bit-identical spikes in Python, JAX, the browser, and C (`nglif`); neuron models
  `two_compartment` and `hh`; calibrated cost estimates; `BodyPlan`, genomes, island evolution, and shareable modules;
  3D browser viewer.
- Release builds and installer packages for macOS, Windows, and Linux are built automatically on `v*` tags by
  `.github/workflows/release.yml` and `.github/workflows/avalonia-app.yml`.
