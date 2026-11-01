# Design principles

1. **General.** No species, organ, task or environment inside the toolbox. Projects bring their own regions, stimuli
   and objectives; species-specific data (transmitter profiles, datasets) are data files outside the core.
2. **Every parameter has a declared source.** By hand, from a field, from genes, fitted to data, or a formula — the
   same stage works in supervised, unsupervised and semi-supervised workflows.
3. **Deterministic.** Seeds in, identical networks and integer spikes out. Rules draw no random numbers; each stage
   repetition has its own random stream.
4. **Backward compatible.** New options are off by default; existing plans and genomes grow the same networks
   (checked by fingerprints).
5. **Low compute.** Linear in cells and synapses, local interactions through a shared cell list, integer kernels,
   struct-of-arrays. Every stage and model declares its cost, and the toolbox refuses what cannot fit before running.
6. **One kernel, several implementations, identical spikes.** Python, JAX, browser and C; any change to one is made to
   all, with equivalence tests.
7. **Robust to development.** Genomes are selected for working across development seeds, not for one network.
8. **Honest claims.** Results are statements about simulations; biological mechanisms are cited, and fidelity is not
   claimed beyond what is implemented and tested.
9. **Shareable.** Circuits are modules; extensions are plugins; apps learn the toolbox's stages and Params at run time.
