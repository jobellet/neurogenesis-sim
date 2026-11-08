# Tutorial 12 — Fit to data, validate, share

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/fitting-validation.ipynb)

This tutorial covers three tools that work on top of a Project or a module:
- **fitting** `Fit` params to measured targets (`neurogenesis.fitting`, task E2);
- **semi-supervised evolution**: genes evolved while `Fit` params are refitted, and Pareto fronts
  (`neurogenesis.evolution.semi_supervised`, E3);
- **validation assays** stored in modules, and the **module registry** (`neurogenesis.validation`,
  `neurogenesis.modules.registry`, E4 and G1).

## Fit params to targets
A `Fit(target, init, lo, hi)` param is a free number named `target`. Until it is fitted it resolves to `init`. Fitted
values are stored in the genome under `"__fit__"`, so the same genome always develops the same tissue.

```python
from neurogenesis.fitting import fit

project["schedule"][1]["params"]["prob"] = {"target": "p_div", "init": 0.1, "lo": 0.0, "hi": 1.0}
targets = [{"metric": "cell_count", "value": 300, "scale": 10},
           {"metric": "layer_thickness", "cell_type": 1, "axis": 2, "value": 0.2, "scale": 0.02}]
r = fit(project, targets, seeds=(0, 1, 2), iterations=30)
r.values          # {"p_div": 0.73...}
r.genome          # the base genome plus {"__fit__": {"p_div": 0.73...}}
```

Each target is `{"metric", "value", "scale" (tolerance), "weight", ...metric options}`. The loss is the mean over the
development seeds of Σ weight · ((metric − value) / scale)². Several seeds per evaluation make the fit robust to
developmental noise. The optimiser is a CMA-ES on the [0, 1]-coded values (gradient free, deterministic for a given
`seed`).

| Metric | Options | Value |
|---|---|---|
| `cell_count` | `region`, `cell_type` | number of living cells |
| `density` | `volume` (required), selectors | cells per unit volume |
| `layer_thickness` | `axis` (0, 1, 2 or a vector), `lower`, `upper` percentiles (5, 95), selectors | extent of the cells along the axis |
| `synapse_count`, `mean_in_degree` | `pre_region`, `pre_cell_type`, `post_region`, `post_cell_type` | synapses; synapses per post cell |
| `connection_probability` | pre / post selectors, `d_min`, `d_max` | fraction of pairs at that distance that are connected |
| `firing_rate` | selectors, `ticks` (500), `ext_current` (0), `sim_seed` | mean rate (Hz) in a `lif_int` simulation |

Add your own with `@register_metric("name")` on a function `(tissue, options) -> float`.

**What the data can constrain.** Before searching, `fit` measures the Jacobian of the metrics with respect to the Fit
values (central differences over ±5 % of each range, on the fitting seeds; `neurogenesis.fitting.jacobian`) and warns:
- about a Fit param that moves no target metric. It cannot be fitted from these targets: the model does not use it, a clip
  masks it, or no target sees it. Drop it or add a target it affects;
- about a target that no Fit param moves. It cannot be matched whatever the fitted values: drop it, give it weight 0 (a
  diagnostic) or add a Fit param that acts on it.

`FitResult.jacobian` and `FitResult.identifiability` (`identifiability_report`: the params and targets above, the singular
values of the Jacobian scaled by each target's tolerance and weight, and its rank) keep the result. The check costs
2 × params × seeds developments; `fit(..., check_identifiability=False)` skips it. It is a local check at the starting
point: a param can matter elsewhere in its range, and correlated params are not detected (a rank below the number of
params says that some combination is unconstrained).

From the command line:
```
python -m neurogenesis fit --project project.json --targets targets.json --seeds 0,1,2 --out fitted_genome.json
```

## Evolve genes while refitting
`inner_fit_evaluator` wraps any evaluator of `islands.evolve`: each genome is first fitted to the data targets, then
scored. With `refit=False` the `Fit` values are kept as they are ("fixed").

```python
from neurogenesis.evolution.islands import evolve
from neurogenesis.evolution.semi_supervised import inner_fit_evaluator

ev = inner_fit_evaluator(project, targets, my_evaluate, fit_seeds=(0,), iterations=5)
P, hist = evolve(base_genome, genes, ev, pop=16, gens=20)
hist[-1]["best_info"]["fit"]          # fitted values of the best genome
```

For several objectives, `evolve_pareto(base, genes, evaluate)` takes an evaluator returning an array
(population × objectives, all maximised) and keeps the population on the Pareto front (non-dominated sorting and
crowding distance, as NSGA-II). `pareto_front(F)` returns the non-dominated rows.

## Validation assays
An assay is a JSON dict stored in `module.validation["assays"]`:
```json
{"name": "responds", "ticks": 100, "blank": 20, "seeds": [1000, 1001, 1002],
 "stimuli": [{}, {"sensor": 300}],
 "readout": {"region": "map", "measure": "rate"},
 "metric": "difference", "gate": {"min": 20.0}, "pass_fraction": 1.0}
```
Each seed grows one individual, runs the stimuli in sequence and computes the metric (`mean`, `difference`
(last − first), `ratio`, `selectivity`, `stimulus:<k>`) of the readout (`rate` in Hz or `fraction_active`). Add
`"knockout": {"regions": [...], "projections": [[src, dst]]}` for a knockout assay.

```
python -m neurogenesis validate module.json            # exit status 1 if an assay fails
```

## Module registry
Modules carry a semantic `version` and the toolbox versions they work with (`toolbox`, e.g. `">=0.1, <0.2"`).
```
python -m neurogenesis install module.json             # refused if incompatible with this toolbox
python -m neurogenesis modules                         # list the catalogue
```
```python
from neurogenesis.modules.registry import get
m = get("topographic map")              # latest version compatible with this toolbox
m = get("topographic map", "1.2.0")     # a given version (checksum verified)
```
The catalogue lives in `$NEUROGENESIS_MODULES` (default `~/.cache/neurogenesis/modules`).
