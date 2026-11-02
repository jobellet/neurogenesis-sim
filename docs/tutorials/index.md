# Tutorials

Each tutorial runs on a laptop CPU in a few minutes. Set `JAX_PLATFORMS=cpu` if you have no GPU.

| # | Tutorial | You will learn |
|---|---|---|
| 1 | {doc}`cli` | every command of `python -m neurogenesis` and of the bridge |
| 2 | {doc}`first-network` | body plans, genomes, `grow`, stimulation and readout |
| 3 | {doc}`neuron-models-cost` | switching neuron models, f–I curves, cost estimates |
| 4 | {doc}`genomes-evolution` | genes, [0, 1] coding, island evolution, audits |
| 5 | {doc}`schedules` | Projects, stages, Params, checkpoints (experimental) |
| 6 | {doc}`fields-geometry` | geometries and fields (experimental) |
| 7 | {doc}`rules-plugins` | writing your own developmental rule and stage |
| 8 | {doc}`modules` | saving, loading and composing modules |
| 9 | {doc}`plasticity` | STDP, Hebbian and three-factor rules |
| 10 | {doc}`viewer` | the browser viewer |
| 11 | {doc}`desktop-apps` | the macOS, Windows and Linux apps |
| 12 | {doc}`fitting-validation` | fitting `Fit` params to data, semi-supervised and Pareto evolution, validation assays, the module registry |
| 13 | {doc}`connectome-data` | connectome manifests, downloads and streaming import |

```{toctree}
:hidden:

cli
first-network
neuron-models-cost
genomes-evolution
schedules
fields-geometry
rules-plugins
modules
plasticity
viewer
desktop-apps
fitting-validation
connectome-data
```

```{admonition} PLACEHOLDER
:class: placeholder
Jupyter notebook versions of every tutorial (rendered with myst-nb, runnable on Binder / Colab), and a video
walkthrough of tutorials 1–4.
```
