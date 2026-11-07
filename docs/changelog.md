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

## Earlier
- Integer LIF kernel identical in Python, JAX and the browser; neuron models `two_compartment` and `hh`; calibrated
  cost estimates; body plans, genomes, island evolution, modules; 3D browser viewer.

```{admonition} PLACEHOLDER
:class: placeholder
Versioned release notes generated from tagged releases.
```
