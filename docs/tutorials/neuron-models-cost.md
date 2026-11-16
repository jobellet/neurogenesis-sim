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

## Slow intrinsic currents (`neurogenesis.spiking.currents`)
Any model can also receive slow intrinsic currents without Hodgkin–Huxley gates as an external current (`ext`), leaving
the integer `lif_int` kernel unchanged:
- `t_current`: low-threshold T-type burst current (integrate-and-fire-or-burst form; Smith et al. 2000).
- `recovery_current`: linear recovery variable for sag, resonance, or spike-frequency adaptation (4 bytes state and ~6
  FLOPs per neuron and tick).

## Reference hardware cost and throughput
Every neuron allocates `40 B` of shared parameters (`PARAM_BYTES`) plus model state (`20 B` for `lif_int`, `32 B` for
`two_compartment`, `36 B` for `hh`), and every synapse allocates `25 B` (`17 B` connectivity + `8 B` per-tick arrival
buffers). Measured 1,000-tick CPU times on a 1,000-neuron, 28,670-synapse column:

| Model / backend | Substeps / tick | State / neuron | FLOPs / substep | CPU time (1,000 ticks) |
|---|---|---|---|---|
| `lif_int` (`numba_backend`) | 1 | 20 B | 12 | 0.062 s |
| `lif_int` (JAX CPU) | 1 | 20 B | 12 | 0.178 s |
| `two_compartment` (JAX CPU) | 4 | 32 B | 22 | 0.280 s |
| `hh` (JAX CPU) | 40 | 36 B | 90 | 1.199 s |

## Interactive calculator: which model can I afford?
Adjust network size and machine memory below using the exact formulas of `neurogenesis.cost.memory_bytes` (refused above
80% of available RAM) and linear throughput extrapolation from the calibrated CPU constants above:

```{raw} html
<div id="ng-cost-calc" style="border:1px solid #d0d7de;border-radius:8px;padding:16px 18px;background:#fafbfc;margin:14px 0 22px 0;">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px 18px;margin-bottom:14px;">
    <label style="font-size:0.88rem;">Neurons ($\log_{10} N$): <strong id="ngc-n-val">100,000</strong><br/>
      <input id="ngc-n" type="range" min="2" max="8" step="0.1" value="5" style="width:100%;" /></label>
    <label style="font-size:0.88rem;">Synapses / neuron: <strong id="ngc-spn-val">1,000</strong><br/>
      <input id="ngc-spn" type="range" min="10" max="5000" step="10" value="1000" style="width:100%;" /></label>
    <label style="font-size:0.88rem;">Simulated seconds: <strong id="ngc-sec-val">1.0 s</strong><br/>
      <input id="ngc-sec" type="range" min="0.5" max="60" step="0.5" value="1" style="width:100%;" /></label>
    <label style="font-size:0.88rem;">Available RAM (GB): <strong id="ngc-ram-val">32 GB</strong><br/>
      <input id="ngc-ram" type="range" min="4" max="256" step="4" value="32" style="width:100%;" /></label>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:0.88rem;background:#fff;">
    <thead><tr style="background:#f0f4f8;text-align:left;"><th style="padding:7px 10px;">Model</th><th style="padding:7px 10px;">Memory</th><th style="padding:7px 10px;">Fits (&le;80% RAM)?</th><th style="padding:7px 10px;">Est. CPU time</th></tr></thead>
    <tbody id="ngc-rows"></tbody>
  </table>
</div>
<script>
(function(){
  const MODELS = [
    { name: "lif_int", state: 20, sub: 1, a: 0.0, b: 1.02e-7, c: 2.1e-8 },
    { name: "two_compartment", state: 32, sub: 4, a: 4.97e-5, b: 1.9e-8, c: 2.6e-8 },
    { name: "hh", state: 36, sub: 40, a: 1.39e-4, b: 2.4e-8, c: 6.5e-8 }
  ];
  const fmtBytes = (b) => b >= 1e12 ? (b/1e12).toFixed(2)+" TB" : b >= 1e9 ? (b/1e9).toFixed(2)+" GB" : b >= 1e6 ? (b/1e6).toFixed(1)+" MB" : (b/1e3).toFixed(1)+" KB";
  const fmtTime = (s) => s >= 86400 ? (s/86400).toFixed(1)+" d" : s >= 3600 ? (s/3600).toFixed(1)+" h" : s >= 60 ? (s/60).toFixed(1)+" min" : s.toFixed(2)+" s";
  const els = { n: document.getElementById("ngc-n"), spn: document.getElementById("ngc-spn"), sec: document.getElementById("ngc-sec"), ram: document.getElementById("ngc-ram") };
  function update(){
    const N = Math.round(Math.pow(10, parseFloat(els.n.value)));
    const spn = parseInt(els.spn.value, 10), sec = parseFloat(els.sec.value), ramGB = parseFloat(els.ram.value);
    const E = N * spn, ticks = sec * 1000, limit = 0.8 * ramGB * 1e9;
    document.getElementById("ngc-n-val").textContent = N.toLocaleString();
    document.getElementById("ngc-spn-val").textContent = spn.toLocaleString();
    document.getElementById("ngc-sec-val").textContent = sec.toFixed(1) + " s";
    document.getElementById("ngc-ram-val").textContent = ramGB + " GB";
    document.getElementById("ngc-rows").innerHTML = MODELS.map((m) => {
      const mem = N * (40 + m.state + 4) + E * 25;
      const fits = mem <= limit;
      const t = (m.a + N * m.sub * m.b + E * m.c) * ticks;
      return `<tr style="border-top:1px solid #e5e7eb;"><td style="padding:7px 10px;"><code>${m.name}</code></td>` +
             `<td style="padding:7px 10px;">${fmtBytes(mem)}</td>` +
             `<td style="padding:7px 10px;font-weight:600;color:${fits ? "#166534" : "#b91c1c"};">${fits ? "fits" : "DOES NOT FIT"}</td>` +
             `<td style="padding:7px 10px;">${fmtTime(t)}</td></tr>`;
    }).join("");
  }
  Object.values(els).forEach((el) => el.addEventListener("input", update));
  update();
})();
</script>
```
