# Changelog

## Unreleased (November 2026)
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

## Earlier
- Integer LIF kernel identical in Python, JAX and the browser; neuron models `two_compartment` and `hh`; calibrated
  cost estimates; body plans, genomes, island evolution, modules; 3D browser viewer.

```{admonition} PLACEHOLDER
:class: placeholder
Versioned release notes generated from tagged releases.
```
