# Running grown networks in other simulators

The toolbox's own kernels are deliberately simple and fast (integer LIF with bit-identical spikes across
implementations). For detailed or large-scale simulation, grown networks are handed to established simulators through
interchange formats (roadmap phase J).

## SONATA (available)
```bash
python -m neurogenesis export network.json --format sonata --out circuit/    # prints an export report
python -m neurogenesis import circuit/ --format sonata --out back.json       # back.json == network.json
```
```python
from neurogenesis.interop import export_network, import_network
report = export_network(net, "sonata", "circuit")    # needs: pip install "neurogenesis-sim[sonata]" (h5py)
print(report)                                         # exact / approximated / dropped, as JSON
net2 = import_network("sonata", "circuit")
```
The directory holds `circuit_config.json`, `network/nodes.h5`, `network/edges.h5`, the node and edge type tables and
NEST `iaf_psc_exp` parameter files: the layout of the SONATA format (Dai et al. 2020), read by BMTK (which runs NEST and
NEURON), libsonata, PyNN (`pyNN.serialization.import_from_sonata`) and Connectome-Manipulator. Every toolbox field is
also stored raw, so reading the circuit back gives the same network bit for bit (tested), and the edge indices are
checked with libsonata.

## How the integer neuron is translated
All exporters share one translation (`neurogenesis.interop.dynamics`), into a current-based exponential LIF
(NEST `iaf_psc_exp`, PyNN `IF_curr_exp`):

| Toolbox | Exported | Exact? |
|---|---|---|
| `shift_v`, `shift_s` | `tau_m`, `tau_syn = −1 / ln(1 − 2^−shift)` ms | per-tick decay exact; rounding not |
| voltage units, `threshold`, reset −256 | `V = E_L + s·v`: `V_th`, `V_reset` (default `E_L` −65 mV, `s` 15/1024 mV) | exact (a free scale) |
| weight `w` | `W = C_m·s·w·(1 − a)/(4a·τ_syn)` pA, `a = 2^−shift_s` | total charge matched; PSP shape approximate |
| delay `d` ticks | `d + 1` ms | the kernel's extra tick of latency included |
| `refractory` ticks | `t_ref` ms | close |
| Poisson and burster drivers | nodes with their rates as attributes | their spontaneous spikes are not generated elsewhere (reported) |
| integer rounding, minimum decrement, ±2048 clamp | — | not represented |

So spike times in another simulator are close to the toolbox's, not identical. The export report says this every
time.

## NIR — Neuromorphic Intermediate Representation (available)
```bash
python -m neurogenesis export network.json --format nir --out circuit.nir
python -m neurogenesis import circuit.nir --format nir --out back.json
```
```python
from neurogenesis.interop import export_network, import_network
report = export_network(net, "nir", "circuit.nir", drivers="keep")   # needs: pip install "neurogenesis-sim[nir]"
print(report)
net2 = import_network("nir", "circuit.nir")
```
`neurogenesis.interop.nir` maps integer LIF networks ($N \le 2{,}048$) into NIR `CubaLIF` nodes with dense `Linear`
recurrent weights (Pedersen et al. 2024). Driver neurons (`mode != 0`) can be kept (`drivers="keep"`), dropped
(`"drop"`), or converted into external input channels (`"input"`). Toolbox neuron and synapse fields are stored in
node metadata so `import_network("nir", ...)` reconstructs the `SNNNetwork` with identical neuron and synapse counts.

## Other targets
| Simulator / toolchain | Route | Status |
|---|---|---|
| NEST (Gewaltig & Diesmann 2007) | SONATA through BMTK PointNet, or PyNN | SONATA available; PyNN planned (J4) |
| NEURON (Hines & Carnevale 1997) | SONATA through BMTK; NeuroML 2 | NeuroML 2 planned (J5) |
| Brian 2 (Stimberg et al. 2019) | PyNN backend | planned (J4) |
| Arbor (Abi Akar et al. 2019) | NeuroML 2 / morphologies (phase N) | planned |
| SpiNNaker (sPyNNaker, Rhodes et al. 2018) | PyNN | planned (J4) |
| snnTorch, Norse, Lava-DL, SpiNNaker2 | NIR (Pedersen et al. 2024): `CubaLIF` + dense `Linear` ($N \le 2048$, no per-synapse delays) | available (J3) |

## Cross-simulator and continuous-ODE comparison
Every exporter reports exact, approximated, and dropped attributes in an `ExportReport`. For the 200-neuron column
(`1,149` synapses), `export_network(..., "nir", ...)` marks `neurons` and `synapses` as **exact**, `neuron dynamics`,
`delays`, and `refractory` as **approximated**, and `integer arithmetic` / `drivers` as **dropped**.

Using `neurogenesis.interop.dynamics.lif_params`, default integer parameters (`shift_v=5`, `shift_s=4`,
`threshold=1024`, `refractory=3`) translate to continuous-time exponential LIF parameters
`tau_m = 31.50 ms`, `tau_syn = 15.49 ms`, `C_m = 250 pF`, `E_L = -65.0 mV`, `V_reset = -68.75 mV`, `V_th = -50.0 mV`,
and `t_ref = 3.0 ms`. Driving a target neuron with an identical 80 Hz Poisson spike train (`delay = 1` tick $\to 2$ ms
latency, 5,000 ticks) gives close firing rates between the 1-ms integer kernel and a continuous Euler ODE integration
(`dt = 0.05 ms`), with the small offset coming from integer bit-shift rounding:

| Synaptic weight $w$ | Translated PSC jump $W$ (pA) | `lif_int` rate (Hz) | Continuous exp-LIF ODE rate (Hz) |
|---|---|---|---|
| 80 | 70.9 | 3.80 | 3.00 |
| 120 | 106.4 | 12.40 | 10.60 |
| 200 | 177.3 | 27.00 | 25.60 |
