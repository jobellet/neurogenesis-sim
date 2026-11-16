# Tutorial 9 — Synaptic plasticity

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/plasticity.ipynb)

`neurogenesis.spiking.plasticity` provides three rules, each usable **offline** (`apply` on a recorded spike train)
or **online**, tick by tick (`step`, no T × N memory):

| Rule | Class | Parameters |
|---|---|---|
| Pair-based STDP | `STDPRule` | `A_plus`, `A_minus`, `tau_plus`, `tau_minus`, `w_min`, `w_max`, `soft_bounds`, `integer_traces` |
| Hebbian with normalisation | `HebbianRule` | `eta`, `norm_target`, `norm_type` |
| Three-factor (eligibility trace × modulator) | `ThreeFactorRule` | `eta`, `tau_e` |

## Offline
```python
import jax.numpy as jnp
from neurogenesis.spiking.plasticity import STDPRule

rule = STDPRule(A_plus=1.0, A_minus=1.05, tau_plus=20, tau_minus=20, w_min=0, w_max=1000)
new_w = rule.apply(weights, pre, post, delays, spikes, original_weights=weights)   # spikes: (T, N) array
```

## Online
```python
tr_pre, tr_post = rule.init_state(num_neurons, num_synapses)
for t in range(T):
    weights, tr_pre, tr_post = rule.step(weights, pre, post, spikes[t], arrivals[t], tr_pre, tr_post)
```

## Inside development
The `refine_by_activity` stage (C11) runs a simulation inside a schedule and applies a rule, so that spontaneous
activity can shape connectivity before the network is used (see {doc}`schedules`).

`refine_by_activity` does nothing unless a `rule` is given, and keeps every synapse's sign (Dale's principle):
excitatory and inhibitory weights have separate bounds.

Each rule declares its cost (`declared_cost(num_neurons, num_synapses, ticks)`).

## Measured STDP window and wave-driven refinement
Measuring `STDPRule.apply` directly over spike pairs separated by $\Delta t = t_{\text{post}} - t_{\text{pre}} \in [-60, 60]$ ms
reproduces the asymmetric exponential potentiation/depression window, and running `refine_by_activity` with
propagating spontaneous waves shifts the distribution of synaptic weights:

```{figure} ../_static/media/plasticity_stdp_waves.png
:width: 95%

Left: weight change $\Delta w(\Delta t)$ measured from `STDPRule.apply` (`A_plus=1.0, A_minus=1.05, tau_plus=20, tau_minus=20`). Right: synaptic weight magnitudes before and after eight wave-driven `refine_by_activity` epochs on a 1D sensor $\to$ map network (`docs/_scripts/make_media.py plasticity`).
```

```python
from neurogenesis.stages import run_schedule

project = {
    "schedule": [
        # ... place cells and grow initial broad axons ...
        {"name": "waves", "operator": "refine_by_activity", "repeat": 8, "params": {
            "rule": "stdp", "ticks": 220, "A_plus": 35.0, "A_minus": 38.0,
            "tau_plus": 20.0, "tau_minus": 20.0, "w_min": 0.0, "w_max": 600.0, "restore_modes": True,
            "waves": {"sources": [[0.0, 15.0, 0.0], [30.0, 15.0, 0.0]], "speed": 0.3, "interval": 110,
                      "duration": 4, "amplitude": 1500, "cells": {"region": [0]}},
        }},
    ]
}
checkpoints = run_schedule(project, {}, seed=0, checkpoints=True)
```

```{figure} ../_static/media/plasticity_rf_sharpening.gif
:width: 65%
:class: gif-demo

Sensor-to-target weight matrix across eight sequential wave-driven STDP epochs: weights tighten around the topographic diagonal as mean receptive-field spread narrows.
```
