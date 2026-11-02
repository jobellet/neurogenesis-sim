# Running grown networks in other simulators

The toolbox's own kernels are deliberately simple and fast (integer LIF with bit-identical spikes across
implementations). For detailed or large-scale simulation, grown networks can be handed to established simulators.

| Simulator | Route today | Planned |
|---|---|---|
| Brian 2 (Stimberg et al. 2019) | build `Synapses` from `net.to_csr()` arrays; delays in ms = ticks | exporter |
| NEST (Gewaltig & Diesmann 2007) | `nest.Connect` with arrays from `net.to_csr()` | SONATA export |
| NEURON (Hines & Carnevale 1997) | positions + connectivity; morphologies when phase N lands | SWC + SONATA export |
| PyNN (Davison et al. 2009) | `FromListConnector` from the synapse list | PyNN exporter |

Example (Brian 2; a sketch, not yet tested against a Brian 2 release compatible with the toolbox's NumPy version):
```python
import numpy as np
from brian2 import NeuronGroup, Synapses, ms

row_ptr, col_idx, w, d = net.to_csr()
pre = np.repeat(np.arange(net.num_neurons), np.diff(row_ptr))
G = NeuronGroup(net.num_neurons, "dv/dt = -v / (20*ms) : 1", threshold="v > 1", reset="v = 0", method="exact")
S = Synapses(G, G, "w : 1", on_pre="v_post += w")
S.connect(i=pre, j=col_idx.astype(int))
S.w = w / 1024.0                     # integer weights relative to the default threshold (1024)
S.delay = d * ms
```
The neuron equations here are a stand-in; map the toolbox's parameters (leak and synaptic shifts, thresholds,
refractory periods, drivers) to the target model explicitly when results must be comparable.

```{admonition} PLACEHOLDER
:class: placeholder
Validated exporters (SONATA, NeuroML, PyNN) with tests comparing spike statistics between the toolbox kernel and
the target simulator on the same network.
```
