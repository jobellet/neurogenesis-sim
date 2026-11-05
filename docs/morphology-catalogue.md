# Morphology Catalogue and Latent Sampling

The morphology catalogue (`neurogenesis.data.morphology_catalogue`) provides verified access to public neuronal
reconstruction banks (NeuroMorpho.Org, MICrONS). Manifests declare SHA-256 checksums, licence and metadata.
Reconstructions are cached locally under `~/.cache/neurogenesis/data/morphology/`.

## Continuous latent sampling

Cortical excitatory cells form a continuous morphological phenotype space rather than discrete types
(Weis, Hansel & Ecker 2021; DECEMber / PMC12155019). The toolbox samples morphologies from a continuous space
conditioned on context (region, layer, laminar depth, age) rather than cloning fixed stereotypes.

```python
from neurogenesis.data.morphology_catalogue import load_catalogue_cells
from neurogenesis.morphometry.latent import ContinuousMorphologySampler

stores, metadata = load_catalogue_cells("neuromorpho_sample")
sampler = ContinuousMorphologySampler(stores, metadata, shrinkage=0.2)
cells = sampler.sample_cells({"layer": "L23"}, n=10, rng=rng)
```

1. Each catalogue cell receives a descriptor vector: TMD persistence image + stratification density profile + scalar morphometrics.
2. Latent space via PCA (SVD); per condition $c$, fits a Gaussian $z \sim \mathcal{N}(\mu_c, \Sigma_c)$ with Ledoit–Wolf diagonal shrinkage.
3. `sample_cells`: draws $z$, computes Gaussian kernel weights against catalogue exemplars, and varies morphology continuously.

## Stage: instantiate_morphologies

`@register_stage("instantiate_morphologies")` samples morphologies for selected cells conditioned on their developmental context
and attaches them as `ArborStore` trees rooted at each cell's soma (`tissue.positions[cell]`).

```json
{
  "stage": "instantiate_morphologies",
  "catalogue": "datasets/morphology/neuromorpho_sample.json",
  "attachment_prob": 1.0,
  "n_neurites": 1,
  "cells": {"region": 0}
}
```

Neutral parameters (`attachment_prob: 0.0` or no catalogue) leave the tissue untouched. Existing connectivity is preserved.
Cost is bounded linearly by `max_nodes`.
