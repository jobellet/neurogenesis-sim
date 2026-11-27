# Teaching

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/use-cases/teaching.ipynb)

- **Spiking dynamics:** the viewer simulates in the browser; students change thresholds, leaks, weights and delays and
  see the raster change immediately.
- **Neuron models:** the same network with integer LIF, two-compartment and Hodgkin–Huxley neurons
  ({doc}`../tutorials/neuron-models-cost`); f–I curves in one call.
- **Cost of detail:** `python -m neurogenesis estimate` shows why a Hodgkin–Huxley model of a whole cortical area is
  out of reach on one machine.
- **Development and evolution:** grow the same genome with different seeds; evolve a projection and see robustness
  across seeds matter.

- **Puzzles:** the viewer hides chosen neuron parameters (`?hide=shift_v,refractory,threshold`); students find them by
  experiment and check their guess, then see how `python -m neurogenesis fit` recovers a parameter from data.
- **Textbook phenomena:** strength–duration curve, type I / II onset, accommodation, rebound, summation, lateral
  inhibition, coincidence detection, persistent activity, as small tested experiments
  ({doc}`../reference/neuron-models` scoreboard; `tests/test_textbook_phenomena.py`).

## Zero-install 2-hour practical (no local setup required)
Students can complete the full practical in a browser using the front-page playground, the embedded 3D viewer, or the
**Open In Colab** badge at the top of this page.

### Part 1 (30 min) — Spiking dynamics and biophysical cost
1. Open the [live 3D viewer](../_static/viewer/index.html?preset=column&no-modal) (500/1,000-neuron column running
   `lif_int` live in WebAssembly/TypeScript).
2. Pause, select an excitatory neuron in the inspector, increase its `threshold` from `1024` to `1500` or lower
   `shift_v` (faster leak), and resume to observe the raster rate drop.
3. In Colab or a local shell, compare the resource cost of simulating `lif_int`, `two_compartment`, and `hh` on
   increasing network sizes:
   ```bash
   python -m neurogenesis estimate --neurons 1e4 --synapses-per-neuron 100 --seconds 1
   python -m neurogenesis estimate --neurons 3e8 --synapses-per-neuron 5000 --model hh
   ```

<details>
<summary>Solution / expected observation</summary>

At $3 \times 10^8$ neurons and $5{,}000$ synapses/neuron ($1.5 \times 10^{12}$ synapses), synapse arrays alone require
tens of terabytes ($25\text{ B} \times 1.5 \times 10^{12} \approx 37.5\text{ TB}$), so `neurogenesis.cost` prints
`DOES NOT FIT` before allocating any memory. Increasing neuron `threshold` or reducing `shift_v` raises the rheobase,
reducing population rate in the browser raster immediately.

</details>

### Part 2 (30 min) — Chemoaffinity and topographic maps
1. Run `examples/topographic_map.py` (or open Tutorial 2 in Colab) and inspect `r_x` and `r_y` on seed 0.
2. Double `sigma` from `0.12` to `0.30` and negate `B[0, 0]` from `2.0` to `-2.0`.

<details>
<summary>Solution / expected observation</summary>

Widening `sigma` increases each sensor's arbor overlap across the map, increasing per-synapse dispersion. Flipping
`B[0, 0]` to `-2.0` reverses the sign of `r_x` (mirror-flipping the horizontal map) so stimulating corner `(0, 0)` drives
the right edge ($u \approx 1$) of the map instead of the left edge.

</details>

### Part 3 (30 min) — Developmental knockouts vs. seed variability
1. Grow `examples/topographic_map.py` across seeds `0..9`, then apply `knockout(genome, projections=[("sensor", "map")])`
   and separately set `B[0, 0] = 0.0`.
2. Compare the between-seed standard deviation of `r_x` in WT against the knockout effect.

<details>
<summary>Solution / expected observation</summary>

Across WT seeds, `r_x` fluctuates by less than `0.01`, whereas `B[0, 0] = 0.0` collapses `r_x` near `0` while sparing
`r_y` (axis-specific cue knockout), and `knockout(genome, projections=[("sensor", "map")])` yields 0 synapses across
every seed.

</details>

### Part 3b (optional, 20 min) — Puzzle: find a hidden parameter
1. Open the viewer with a network and hidden values, for example
   [`?preset=column&no-modal&hide=shift_v,threshold`](../_static/viewer/index.html?preset=column&no-modal&hide=shift_v,threshold);
   any network JSON can be opened from a link with `?network=<url>`.
2. Select a neuron (or press `]`), stimulate it, watch the voltage trace and the raster, and enter a guess in the
   puzzle box. Keyboard: Space runs or pauses, `S` steps, `[` / `]` select neurons, Escape deselects.

<details>
<summary>Solution / expected observation</summary>

A faster leak (smaller `shift_v`) makes the voltage fall back sooner between inputs; a higher threshold needs more
summed input before a spike. Different values can give the same activity (Prinz, Bucher & Marder 2004), so more than
one guess may be consistent with what you see: a good reason to fit parameters to several kinds of data.

</details>

### Part 4 (30 min) — Evolving a genome across fresh developmental seeds
1. Open the {doc}`../getting-started/playground` on the front page (`docs/index.html`) or run its Python equivalent.
2. Click **Step** and **Evolve** to watch the generation-by-generation champion, then toggle **New seed** and drag the
   `B` slider manually to test sensitivity.

<details>
<summary>Solution / expected observation</summary>

Because every generation draws fresh development seeds (`seeds_of`), selection cannot overfit to one lucky wiring;
gradient gain `B` rises consistently across runs, lifting held-out fitness from ~0.01 (founder) past 0.25 within 10
generations.

</details>

## A caution for every simulation
Simulations always "work" and give clean results; real experiments do not. And a model that reproduces a recording
does not prove that the real system uses the model's mechanism: Hodgkin and Huxley (1952) wrote that the success of
their equations was no evidence for the mechanism they had in mind (quoted in this context by Heitler 2022). Virtual
labs teach concepts about as well as physical labs, but not experimental skills (de Jong, Linn & Zacharia 2013).
