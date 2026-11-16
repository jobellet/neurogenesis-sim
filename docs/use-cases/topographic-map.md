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

## Quantitative 100-seed study
Across 100 development seeds (`0..99`), we sweep the chemoaffinity arbor spread $\sigma$ (`N_map = 200`, comparing
initial chemoaffinity against wave-driven coactivity filtering) and the number of map cells $N_{\text{map}}$
($\sigma = 0.12$):

```{figure} ../_static/media/topographic_study_100seeds.png
:width: 96%

Left: mean $\pm$ SD topographic Pearson correlation $r$ across 100 development seeds as a function of arbor spread $\sigma$, before and after wave-driven activity filtering (`docs/_scripts/make_media.py topo_study`). Right: precision scales smoothly with target cell count $N_{\text{map}}$.
```

| Arbor spread $\sigma$ ($N_{\text{map}} = 200$) | Chemoaffinity alone ($r$, mean $\pm$ SD) | Wave coactivity filter ($r$, mean $\pm$ SD) |
|---|---|---|
| `0.05` | `0.965 ± 0.099` | `0.965 ± 0.099` |
| `0.08` | `0.968 ± 0.007` | `0.968 ± 0.007` |
| `0.12` | `0.963 ± 0.007` | `0.958 ± 0.008` |
| `0.18` | `0.966 ± 0.006` | `0.956 ± 0.007` |
| `0.25` | `0.967 ± 0.005` | `0.953 ± 0.010` |
| `0.35` | `0.966 ± 0.005` | `0.930 ± 0.029` |
| `0.50` | `0.958 ± 0.006` | `0.811 ± 0.067` |

Varying target size at $\sigma = 0.12$ across 100 seeds raises precision and cuts across-seed variance monotonically:
`N_map = 50` gives `0.940 ± 0.016`, `100` gives `0.951 ± 0.010`, `200` gives `0.963 ± 0.007`, and `400` gives
`0.974 ± 0.004`. Because `B = diag(2, 2, 0)` already points every axon towards its topographic target, broad arbors
keep high mean centroid correlation while losing single-synapse selectivity; at very broad arbors ($\sigma \ge 0.35$),
global sweeps fire targets broadly and reduce selectivity if presynaptic thresholding trims weak branches.
