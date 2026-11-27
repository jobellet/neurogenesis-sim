# Neuron models and their cost

## Choosing a model
Every grown network runs with any registered model:
```python
from neurogenesis.spiking.batch import simulate_counts
counts = simulate_counts(nets, currents, ticks=300, model="hh")      # "lif_int" (default), "two_compartment", "hh"
```
All models share the same transmission layer: the same synapses, axonal delays (up to 255 ticks of 1 ms) and driver
neurons. The Poisson drivers and intrinsic bursters fire at exactly the same ticks in every model (tested). Models
differ in how a neuron integrates its inputs between spikes.

| Model | Level | Integration | Uses from the grown network | Known properties tested |
|---|---|---|---|---|
| `lif_int` | point neuron, integer | 1 update per tick | everything (leak and synaptic shifts, threshold, refractory period) | identical spikes in Python, JAX and the browser |
| `two_compartment` | soma + dendrite, intermediate | Euler, 4 substeps per tick | membrane time constant 2^shift_v ms, synaptic time constant 2^shift_s ms, threshold, refractory period | same rheobase as `lif_int`; maximum rate set by the refractory period; dendritic (synaptic) input attenuated relative to somatic input |
| `hh` | Hodgkin–Huxley point neuron (Na, K, leak) | exponential Euler for gates, 40 substeps of 0.025 ms | synaptic time constant; threshold and refractoriness come from the channels | rest near −65 mV; abrupt onset of repetitive firing (type II) near 6.3 µA/cm² from rest, at 50–60 Hz; about 65–70 Hz at 10 µA/cm² |
| `hh_table` | `hh` with tabulated gates | as `hh`, gate factors read from tables over voltage (0.05 mV, linear interpolation) | as `hh` | f–I curve within 2 Hz of `hh`, same onset |

**Units.** External currents and synaptic weights keep the toolbox's integer units.
- **Hodgkin–Huxley:** 1 unit = 0.74 µA/cm², so its onset of repetitive firing falls at the integer neuron's rheobase (8.5 units).
- **Two compartments:** the conversion is set the same way.
- **Weights:** a synaptic weight w delivers the charge of a w-unit current lasting 1 ms.

This makes the models comparable on the same network, not quantitatively equivalent.

## Slow intrinsic currents without Hodgkin–Huxley gates
`neurogenesis.spiking.currents` adds channel-like dynamics to any model at one float per neuron and about 6 operations
per tick. The currents are computed outside the kernel and given to it as external current, so the integer kernel and
its equivalent implementations are unchanged.

| Function | What it reduces | Behaviour kept (tested) |
|---|---|---|
| `t_current` | low-threshold T-type calcium current, in its integrate-and-fire-or-burst form: an inactivation variable recovers below a potential `v_h` and decays above it | rebound burst after a long enough hyperpolarisation; no current in a neuron held depolarised (tonic mode) |
| `recovery_current` | any gated current linearised around an operating point: du/dt = (kappa v − u) / tau, jump `d` per spike | sag and partial return under a hyperpolarising step (kappa > 0); spike-frequency adaptation (d > 0) |

Not kept: the all-or-none shape of the low-threshold spike and anything that depends on large voltage excursions of a
linearised gate. With neutral parameters (g = 0; kappa = 0, d = 0) the currents are zero.

**Adding a model:** `neurogenesis.spiking.models.register_model(module)`. The module provides `name`, `description`,
`substeps`, `state_bytes`, `flops`, `init_state(net, seed)` and `tick(net, state, ext)`, and uses
`models.base.drivers` and `models.base.transmit`, so that drivers and delays behave as in every other model. Then add it
to the parametrised tests in `tests/test_models.py`.

## Tabulated gates (`hh_table`)
`hh_table` is `hh` with the two numbers that the exponential Euler update needs per gate, x_inf(V) and
exp(−dt (α + β)) (Rush & Larsen 1978), read from tables over voltage instead of computed with exponentials at each
substep, as detailed simulators usually do (GENESIS: Bower & Beeman 1998; NEURON: Hines & Carnevale 2000). The gate
updates then no longer depend on a platform's `exp`, which matters for a port to `nglif` or the browser. In JAX on a
CPU the table lookups are **not** faster than vectorised exponentials (measured: about 1.3 × the time of `hh`), so
`hh` stays the default.

## Checking the integration step
Float models use fixed substeps, and fixed-step integration can move spike times and even change network
synchrony (Hansel et al. 1998; Brette et al. 2007). `neurogenesis.analysis.step_convergence(net, model, ext)` runs a
network with the model's substeps and with twice as many and reports how much the spikes change (`rate_change`,
`matched` within ±1 tick, `max_count_change`). The defaults pass on test networks: isolated cells keep their spikes
within one tick, recurrent networks change their total rate by less than 5 % (`tests/test_step_convergence.py`).
`lif_int` is defined on the 1 ms tick and has no smaller step.

## Textbook phenomena (scoreboard)
Classic experiments on tiny hand-built networks, each a test with a known answer (`tests/test_textbook_phenomena.py`;
inputs over time with `neurogenesis.analysis.spike_raster`). Firing features follow the list of Izhikevich (2004);
"no" means the model does not show it, "–" that it is not tested.

| Feature | `lif_int` | `two_compartment` | `hh` | Test |
|---|---|---|---|---|
| tonic spiking | yes | yes | yes | f–I curves |
| type I onset (low rates near rheobase) | yes | – | no | onset of firing (Hodgkin 1948) |
| type II onset (abrupt, near 50 Hz) | no | – | yes | onset of firing (Hodgkin 1948) |
| strength–duration curve | yes | – | yes | Lapicque (1907) |
| maximum rate set by the refractory period | yes | yes | (channels) | refractory period |
| integrator (temporal summation) | yes | – | – | summation window grows with the membrane time constant |
| accommodation to slow ramps | no | no | yes | Hodgkin & Huxley (1952) |
| rebound spike after inhibition | no (yes with `t_current`) | no | yes | release from hyperpolarisation |
| spike-frequency adaptation | with `recovery_current` | – | – | `tests/test_currents.py` |
| phasic spiking, bursting modes, latency, subthreshold oscillations, resonance, bistability, inhibition-induced spiking | – | – | – | not tested |

Circuits with `lif_int`: lateral inhibition enhances an edge (Hartline & Ratliff 1957); detectors on two delay lines
code the timing difference of their inputs by place (Jeffress 1948); recurrent excitation holds persistent activity
that a pulse switches on and off (bistable, cf. Wilson & Cowan 1972); mutual inhibition makes a flip-flop. Two cells
with mutual inhibition do **not** alternate (no half-centre oscillation, Wang & Rinzel 1992) without an added slow
current, in `lif_int` or `hh`.

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
