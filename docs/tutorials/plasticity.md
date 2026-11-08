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

```{admonition} PLACEHOLDER
:class: placeholder
Figures: the STDP window measured from the implementation; weight distributions before and after refinement by
spontaneous waves; a GIF of receptive fields sharpening during activity-dependent refinement.
```
