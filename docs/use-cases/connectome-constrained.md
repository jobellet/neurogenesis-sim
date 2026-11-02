# Connectome-constrained development (planned)

**Idea.** Public connectomes give, for a whole nervous system or a part of it, every neuron's type and position and
the number of synapses between pairs of neurons. The toolbox will use them in two ways:

1. **Supervised import:** a subset of a connectome (filtered by cell type, region or neuron ids) becomes a network,
   simulated directly.
2. **Statistical targets for development:** cell counts per type, type × type synapse matrices, degree
   distributions, transmitter composition and topography (e.g. inputs from the same or neighbouring column) become
   targets that grown circuits are fitted to. Matching is statistical, at the cell-type level, never neuron by
   neuron; when several individuals exist, their spread sets the tolerance.

**What it builds on** (roadmap phases K, I, P, N, now implemented; see the tutorial on connectome data):
- larger networks (array-backed synapse store, 32-bit neuron indices, multi-word spike history for long delays);
- a dataset catalogue and streaming importer;
- transmitter → effect as data that depends on the receptor, the organism and the developmental stage
  (e.g. glutamate acting through inhibitory glutamate-gated chloride channels in invertebrates; GABA depolarising
  early in development);
- branching axons and dendrites, with delays from path length along the arbor, and skeleton import.

**First target.** A columnar motion-vision subcircuit of the fly optic lobe: Mi1, Tm3, Mi4 and Mi9 neurons
projecting onto T4 neurons, with hexagonal column coordinates as a hand-made field. An analysis of the FlyEM male CNS
connectome v1.0 (CC-BY 4.0) found Mi1 → T4 the strongest of these inputs (about 100–115 thousand synapses onto each
T4 subtype), followed by Tm3, Mi9 and Mi4.

```{admonition} PLACEHOLDER
:class: placeholder
The full example once phases I and P are merged: dataset download, the imported subset in the viewer, the grown
circuit next to it, and the comparison of their type-level statistics.
```
