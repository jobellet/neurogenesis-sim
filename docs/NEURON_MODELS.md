# Neuron models and their cost

## Choosing a model
Every grown network runs with any registered model:
```python
from neurogenesis.spiking.batch import simulate_counts
counts = simulate_counts(nets, currents, ticks=300, model="hh")      # "lif_int" (default), "two_compartment", "hh"
```
All models share the same transmission layer: the same synapses, axonal delays (up to 31 ticks of 1 ms) and driver
neurons. The Poisson drivers and intrinsic bursters fire at exactly the same ticks in every model (tested). Models
differ in how a neuron integrates its inputs between spikes.

| Model | Level | Integration | Uses from the grown network | Known properties tested |
|---|---|---|---|---|
| `lif_int` | point neuron, integer | 1 update per tick | everything (leak and synaptic shifts, threshold, refractory period) | identical spikes in Python, JAX and the browser |
| `two_compartment` | soma + dendrite, intermediate | Euler, 4 substeps per tick | membrane time constant 2^shift_v ms, synaptic time constant 2^shift_s ms, threshold, refractory period | same rheobase as `lif_int`; maximum rate set by the refractory period; dendritic (synaptic) input attenuated relative to somatic input |
| `hh` | Hodgkin–Huxley point neuron (Na, K, leak) | exponential Euler for gates, 40 substeps of 0.025 ms | synaptic time constant; threshold and refractoriness come from the channels | rest near −65 mV; abrupt onset of repetitive firing (type II) near 6.3 µA/cm² from rest, at 50–60 Hz; about 65–70 Hz at 10 µA/cm² |

**Units.** External currents and synaptic weights keep the toolbox's integer units.
- **Hodgkin–Huxley:** 1 unit = 0.74 µA/cm², so its onset of repetitive firing falls at the integer neuron's rheobase (8.5 units).
- **Two compartments:** the conversion is set the same way.
- **Weights:** a synaptic weight w delivers the charge of a w-unit current lasting 1 ms.

This makes the models comparable on the same network, not quantitatively equivalent.

**Adding a model:** `neurogenesis.spiking.models.register_model(module)`. The module provides `name`, `description`,
`substeps`, `state_bytes`, `flops`, `init_state(net, seed)` and `tick(net, state, ext)`, and uses
`models.base.drivers` and `models.base.transmit`, so that drivers and delays behave as in every other model. Then add it
to the parametrised tests in `tests/test_models.py`.

## Knowing the cost before trying
```
python -m neurogenesis estimate --neurons 3e8 --synapses-per-neuron 5000 --seconds 1
```
For each model, the estimator gives:
- **memory**, counted array by array: neuron parameters and state, synapse arrays and their per-tick buffers, recorded counts;
- **the memory available** (free GPU memory if JAX runs on a GPU, else RAM);
- **the time** per simulated second.

**How the time is computed.** It comes from a throughput measured once per model and device: three short benchmarks,
fitting a fixed cost per tick, a cost per neuron-substep and a cost per synapse. The result is cached in
`~/.cache/neurogenesis/throughput.json`. The tests check that the estimate stays within a factor of 4 of the measured
time on a 3000-neuron, 120 000-synapse network.

**Guard rail.** Every batched simulation calls `cost.check` first:
- it refuses a network that does not fit in memory (`CostError`, unless `force=True`);
- it warns when a calibrated estimate exceeds one hour.

**Example on the development cluster CPU (2026-11-01; numbers depend on the machine):**

| Network | lif_int | two_compartment | hh |
|---|---|---|---|
| 10⁴ neurons, 10⁷ synapses | 250 MB; ~25 min / simulated s | 250 MB; ~47 min / simulated s | 250 MB; ~26 min / simulated s |
| 3 × 10⁸ neurons, 5000 synapses each (an order of magnitude for a primate ventral visual stream, illustrative only) | does not fit: 37.5 TB; ~7 years / simulated s | does not fit; ~13 years / s | does not fit; ~7 years / s |

On this CPU, synapses dominate both memory and time; the neuron model matters once neurons dominate. For 10⁶ neurons
without synapses, Hodgkin–Huxley costs about 50 times more than the integer neuron (40 substeps of a heavier update).
Large extrapolations are linear and ignore memory bandwidth and multi-device communication, so they are optimistic.
