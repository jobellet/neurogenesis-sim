# Tutorial 3 — Neuron models and cost

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/neuron-models-cost.ipynb)

## Switching models on the same network
Every grown network runs with every registered model:
```python
from neurogenesis.spiking.batch import simulate_counts
for model in ("lif_int", "two_compartment", "hh"):
    counts = simulate_counts([net], [ext], ticks=300, model=model)
```
The models share synapses, axonal delays and driver neurons (Poisson drivers and bursters fire at the same ticks in
every model). They differ in how a neuron integrates its inputs between spikes.

| Model | Level | Integration |
|---|---|---|
| `lif_int` | integer point neuron | one update per tick; identical spikes in Python, JAX, the browser and C |
| `two_compartment` | soma + dendrite | Euler, 4 substeps per tick |
| `hh` | Hodgkin–Huxley (Na, K, leak) | exponential Euler, 40 substeps of 0.025 ms |

```{figure} ../_static/media/raster_models.png
:width: 90%

The grown topographic map (seed 0) simulated with the three models. Input: current 40 into one column of the sensor sheet for 40 ticks (grey bands), sweeping across the sheet, with 20 silent ticks between. Neurons are sorted by x, so the map response moves with the stimulus in all three models.
```

## Frequency–current curves
```python
import numpy as np
from neurogenesis.analysis import fi_curve
currents = np.arange(0, 40, 1)
for model in ("lif_int", "two_compartment", "hh"):
    p = fi_curve(currents, model=model)     # firing probability per tick; each current starts from rest
    rates_hz = 1000 * p                     # one tick = 1 ms
```

```{figure} ../_static/media/fi_curves.png
:width: 70%

f–I curves of the three models with the default integer parameters (shift_v=5, shift_s=4, threshold=1024,
refractory=3).
```

Units: 1 current unit = 0.74 µA/cm² in the Hodgkin–Huxley model, chosen so that its onset of repetitive firing falls
at the integer neuron's rheobase. This makes the models comparable on the same network, not quantitatively
equivalent. Details: {doc}`../reference/neuron-models`.

## Cost: know before you try
```python
from neurogenesis.cost import estimate, check, CostError
e = estimate("hh", n_neurons=100_000, n_synapses=10**8, ticks=1000)
print(e["verdict"])
check("hh", 3 * 10**8, 3 * 10**8 * 5000, 1000)   # raises CostError: does not fit in memory
```
- Memory is counted array by array (neuron state, synapse arrays, delay buffers, records).
- Time comes from a throughput calibrated once per model and device (cached in
  `~/.cache/neurogenesis/throughput.json`).
- `simulate_counts` calls `check` first; pass `force=True` to override.

```{admonition} PLACEHOLDER
:class: placeholder
A table of measured throughput on reference hardware (laptop CPU, workstation GPU, Apple silicon) and a
"which model can I afford?" interactive calculator.
```
