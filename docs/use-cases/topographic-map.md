# Topographic projection grown from genes

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/use-cases/topographic-map.ipynb)

**Question.** Can a projection that preserves neighbourhoods (a topographic map) be specified by a handful of
guidance genes, and does it hold for every developmental seed?

**Model.** A fixed 6 × 6 sensor sheet projects onto a map of 200 cells whose number and positions come from the
genome. Each sensor axon aims at an affine function of its own position (positional chemoaffinity; Sperry 1963) and
connects to map cells near that target with a Gaussian probability.

```{figure} ../_static/media/topographic_map_growth.gif
:width: 80%
:class: gif-demo

The circuit appearing step by step (see the frame titles for what each frame adds).
```

```{figure} ../_static/media/topographic_precision.png
:width: 65%

Sensor position against the mean position of its targets in the map, for the grown network.
```

**Run it.**
```bash
python examples/topographic_map.py --cpu
```
```text
stimulus at corner (0, 0): 4 map neurons fire, spike-weighted mean u of the map 0.09
stimulus at corner (1, 1): 7 map neurons fire, spike-weighted mean u of the map 0.74
```
In this simulation, opposite corners of the sheet drive opposite sides of the map.

**Going further.**
- Make `sigma`, `B` and `c` genes (`guidance_genes("sensor", "map")`) and evolve them for topographic precision
  across development seeds ({doc}`../tutorials/genomes-evolution`).
- Add the `topographic` target rule or a refinement stage with correlated activity (retinal-wave-like) to sharpen
  the map (Willshaw & von der Malsburg 1976).

```{admonition} PLACEHOLDER
:class: placeholder
A quantitative study: precision vs sigma and number of map cells, across 100 development seeds, with and without
activity-dependent refinement.
```
