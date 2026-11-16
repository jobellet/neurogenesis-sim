# Connectome-constrained development

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/use-cases/connectome-constrained.ipynb)

**Idea.** Public connectomes give, for a whole nervous system or a part of it, every neuron's type and position and
the number of synapses between pairs of neurons. The toolbox uses them in two ways:

1. **Supervised import:** a subset of a connectome (filtered by cell type, region or neuron ids) becomes a network,
   simulated directly ({doc}`../tutorials/connectome-data`).
2. **Statistical targets for development:** cell counts per type, type × type synapse matrices, degree
   distributions, transmitter composition and topography (e.g. inputs from the same or neighbouring column) become
   targets that grown circuits are fitted to. Matching is statistical, at the cell-type level, never neuron by
   neuron; when several individuals exist, their spread sets the tolerance.

**What it builds on** (roadmap phases K, I, P, N):
- larger networks (array-backed synapse store, 32-bit neuron indices, multi-word spike history for delays up to 255 ticks);
- a dataset catalogue and streaming importer (`neurogenesis.data`);
- transmitter → effect as data that depends on the receptor, the organism and the developmental stage
  (e.g. glutamate acting through inhibitory glutamate-gated chloride channels in invertebrates; GABA depolarising
  early in development);
- branching axons and dendrites, with delays from path length along the arbor, and skeleton import.

**First target.** A columnar motion-vision subcircuit of the fly optic lobe: Mi1, Tm3, Mi4 and Mi9 neurons
projecting onto T4 neurons, with hexagonal column coordinates as a hand-made field. An analysis of the FlyEM male CNS
connectome v1.0 (CC-BY 4.0) found Mi1 → T4 the strongest of these inputs (about 100–115 thousand synapses onto each
T4 subtype), followed by Tm3, Mi9 and Mi4.

## Worked example: 7-column optic-lobe circuit
`examples/optic_lobe_column.py` generates a 7-column hexagonal connectome dataset with cholinergic (`Mi1`, `Tm3`),
GABAergic (`Mi4`), and glutamatergic (`Mi9` onto `T4`) cell types, imports it via `import_connectome`, extracts
type-level fitting targets (`extract_fitting_targets`), fits `grow_axons` `Fit` parameters with CMA-ES
(`neurogenesis.fitting.fit`), and compares the grown circuit on a held-out developmental seed (`seed=2`) using
`compare_type_statistics`:

```bash
python examples/optic_lobe_column.py
```

```{figure} ../_static/media/optic_lobe_comparison.png
:width: 98%

Left: cell types across 7 hexagonal columns of the imported connectome (`63` cells, `186` edges). Centre: type $\times$ type synapse matrix of the connectome. Right: type $\times$ type synapse matrix of the fitted developmental schedule (`seed=2`, `187` edges, matrix cosine similarity `0.991`).
```

| Measure (`compare_type_statistics`) | Value (seed 2 vs. connectome) |
|---|---|
| Cell count L1 relative error | `0.000` (`[14, 14, 14, 7, 14]` for `Mi1, Mi4, Mi9, T4, Tm3`) |
| Type $\times$ type matrix cosine similarity | `0.991` (`187` grown vs. `186` reference edges) |
| Mean degree relative error | `0.188` |
