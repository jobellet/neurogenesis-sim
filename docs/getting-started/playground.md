# Browser playground

The front page of this site runs a small evolution experiment in your browser: a cortex-like sheet is grown from a
genome, stage by stage, then simulated, and every generation the best of its offspring becomes the next parent. Two
slices are animated through the six stages of development: the founding genome on the left, the current champion on
the right (top and bottom on a narrow screen). Everything drawn comes from the grown individuals themselves (lineages,
migration paths, axon targets, synapses kept, spikes); nothing is scripted.

The code is a dependency-free JavaScript port of parts of the toolbox, `docs/_static/ngjs/ng-core.js`, plus the
page widget `docs/_static/ngjs/ng-hero.js`. It is a toy problem for the documentation, not a model of a particular
cortex.

## What you see
- **On load**, the page has already run 5 generations, so the right slice is the generation-5 champion (held-out
  fitness 0.19, against 0.02 for the founder), then evolution continues. The evolution's random stream is seeded, so
  every visitor sees the same first champions.
- **Colour key** (under the slices): pyramidal neurons pink, interneurons yellow, radial glia (progenitors) green;
  each thalamic axon has the colour of its position in the thalamus, so an ordered map looks like a rainbow; eliminated
  synapses turn grey; spikes flash white.
- **What selection changed**: for the current stage, the founder's and the champion's values, each the mean of three
  held-out development seeds. A value that selection has not changed is marked *same*.
- A new champion replaces the right slice at the next stage boundary, so that no slice changes in the middle of an
  animation; the slice title gives the generation shown.

## What you can do
- **Evolve / Pause / Step**: run the evolution, or one generation at a time with **Step**. Evolution pauses by itself
  every 40 generations.
- **Reset**: back to the founder (generation 0) and to stage 1 of the tour. The right slice then reads *champion so far
  = founder*, and evolution waits for **Evolve** or **Step**.
- **New seed**: grow the founder and the champion again from another development seed (the same genome gives a
  different, but similar, individual).
- **Stages**: click a stage to loop it; click it again to go back to the tour of all six stages.
- **λ, σ, keep parent, pause between generations**: number of offspring per generation, mutation size on the [0, 1]
  gene coding, elitism (the parent competes with its offspring, a (1 + λ) strategy, instead of the default (1, λ)), and
  a 0.9 s pause after each generation to follow the offspring.
- **Genome**: drag a gene to edit the champion by hand. Its slice and its fitness are recomputed at once; **Evolve
  from this genome** continues the evolution from there. The small curves show each gene over the generations (dashed:
  the founder's value).
- In the browser console, `window.NGJS` holds every function (see [JavaScript API](#javascript-api)).

## The stages and their genes
The slice is 2D: x along the sheet, z the depth from the ventricle (0) to the pia (1). Twelve genes, each acting on one
stage, are coded in [0, 1] between the bounds below (as `neurogenesis.genome.from_unit`).

| Stage | Toolbox stage it follows | What happens | Genes (founder → bounds) |
|---|---|---|---|
| 1. Neurogenesis | `seed_cells`, `cell_cycle_clock` (C14), `proliferate` (C2) | 12 radial glial progenitors divide for 6 cycles; at each cycle a cell leaves the cycle with probability Q = min(1, k · generation^1.97) and its two daughters become neurons (Takahashi, Nowakowski & Caviness 1996, J Neurosci). Progenitors stay tethered to the ventricular surface by an apical process while their nuclei move asynchronously across G1/S/G2/M (interkinetic nuclear migration; Sauer 1935, J Comp Neurol; Kosodo et al. 2011, EMBO J), divide at the ventricle, and newborn neurons delaminate into the SVZ/IZ multipolar zone (Miyata et al. 2001, Neuron; Noctor et al. 2001, Nature). | cycle exit k (0.1; 0.005–0.4) |
| 2. Fate | `proliferate` (C2) | Pyramidal neurons come from the cortical ventricular zone. Most cortical interneurons come from the medial ganglionic eminence (MGE), others from the caudal ganglionic eminence; the model has one source, 4 MGE progenitors that divide 4 times (Anderson et al. 1997, Science; Wonders & Anderson 2006, Nat Rev Neurosci). | MGE division probability (0.3; 0–1) |
| 3. Migration | `migrate` (C4), `mosaic` (C5) | After a multipolar pause in the SVZ/IZ, pyramidal neurons climb radially along radial glial fibers with a leading centrosomal swelling and saltatory nuclear jumps (Noctor et al. 2004, Nat Neurosci; Tsai et al. 2007, Cell) for 20 sub-steps at speed s0 + s1 (birth cycle − 3.5), stopped by the marginal zone (Rakic 1972, J Comp Neurol; inside-out: Angevine & Sidman 1961, Nature). Interneurons move tangentially, each leaving the stream at its own point, disperse (homotypic repulsion with motility), then enter the cortical plate at the depth of nearby pyramidal cells (Marín & Rubenstein 2001, Nat Rev Neurosci; Lodato et al. 2011, Neuron). | radial speed s0 (0.022; 0–0.05), birth-date gain s1 (0.006; −0.012–0.012), tangential speed (0.025; 0–0.06) |
| 4. Axon guidance | `secrete_cue`, `grow_arbors` (C27 options), `arbor_synapses` (N3); `grow_axons` (C8) for the local circuit | Pyramidal cells release a cue in proportion to their layer-4 identity, exp(−(z − 0.66)²/2·0.12²) (cells above 0.05 secrete), with decay length 0.05 (`CueField`; target-derived cues: Tessier-Lavigne & Goodman 1996, Science). 32 thalamic relay cells (a fixed scaffold) each grow one axon from depth −0.55, heading for x = sigmoid(4 B (x_thalamus − ½)) in layer 4 (chemoaffinity: Sperry 1963, PNAS), with angle noise 0.015 and steps of 0.06; the growth cone turns up the cue's gradient with its receptor gain (the receptor sets attraction or repulsion: Hong et al. 1999, Cell). Where the cue reaches the arrival threshold, the shaft becomes an arbor (steps 0.02, angle noise 0.7, branching probability per step), confined to where the cue stays above the threshold (target-derived branching: Cohen-Cory & Fraser 1995, Nature); 30 steps in all. Arbor nodes within 0.035 of a cortical cell body make a synapse with probability 0.8 (one per axon and cell, the closest; delay = path length / 0.12). Interneurons contact nearby pyramidal cells densely (p0 0.8, σ 0.12; Packer & Yuste 2011, J Neurosci) and receive input from them. | gradient gain B (0; −1–3), receptor gain (0.3; −1–2), arrival threshold (1.0; 0.05–3), arbor branching (0.12; 0–0.3) |
| 5. Refinement | `competitive_elimination` (C22) after spontaneous activity | Two waves sweep the thalamus (160 ms; before eye opening, retinal waves drive the visual thalamus: Katz & Shatz 1996, Science). On every cortical cell that fired, a thalamic input whose coactivity (pre spike, after the delay, then a post spike within 5 ms) is below a fraction of the best input onto that cell is removed (Willshaw 1981, Proc R Soc Lond B; Balice-Gordon & Lichtman 1994, Nature). | competition fraction (0; 0–1) |
| 6. Activity | `lif_int` kernel | Seven flashes on the thalamus, one every 40 ms in one continuous simulation; each is read from the pyramidal spikes of a 20 ms window starting 10 ms after onset. Interneurons give feedforward inhibition (Gabernet et al. 2005, Neuron). | excitatory weight (140; 20–500), inhibitory weight (100; 0–1500) |

The founder grows a viable but untuned cortex: no map (B = 0, every thalamic axon heads for the centre of the sheet),
most neurons settle below layer 4, so the cue is weak and half of the thalamic axons never reach the arrival threshold
(they make no arbor and no synapse), interneurons cover half of the sheet, and synapses are weak.

## The task and the fitness
After each flash, the decoded position is the spike-weighted mean x of the pyramidal cells (a population vector; ½ when
they are silent). With the root-mean-square error between decoded and true positions over the seven flashes:

```text
accuracy   = exp(-RMSE / 0.08)
response   = mean over flashes of (1 - exp(-spikes / 5))         reliable, not silent
efficiency = exp(-(neurons / 1000 + thalamocortical synapses / 2500 + spikes per flash / 400))
fitness    = accuracy × response × efficiency
```

Spikes and synaptic transmission dominate the energy used for signalling (Attwell & Laughlin 2001, J Cereb Blood Flow
Metab), so a network that floods its whole sheet with spikes, or grows many useless cells and synapses, pays for it. The
product makes every stage matter: a perfect map (stage 4) is useless if the neurons are not in layer 4 where the axons
end (stages 1 and 3), and a strong response is costly unless inhibition (stages 2, 3 and 6) and competition (stage 5)
keep it focused.

## Evolution
`NGJS.Evolution` is a (1, λ) evolution strategy on the [0, 1] coding, the one-parent case of
`neurogenesis.evolution.islands.evolve`: the parent makes λ mutated offspring (u + σ N(0, 1), clipped); all are
grown on the same fresh development seeds of the generation (`seeds_of`, two seeds by default) and the best becomes the
next parent, even when it is worse than its parent. The champion of each generation is also assessed on three fixed
held-out seeds (1, 2, 3), the audit of `neurogenesis.evolution.robust`; the green curve of the chart is this held-out
fitness.

In 8 runs of 30 generations with the default settings (λ = 10, σ = 0.1, islands 0–7), the held-out fitness of the
founder is 0.02; the champion passed 0.2 after 1 to 6 generations and reached 0.25 on average (0.14–0.39) at generation
10 and 0.34 (0.20–0.47) at generation 30. It fluctuates on the way: comma selection on noisy evaluations loses the
parent every generation. What selection changed, from the founder to the generation-30 champions (mean, range over the
8 runs):

| Stage | Founder | Champions |
|---|---|---|
| Neurogenesis: cycle exit k; neurons; mean birth cycle | 0.1; 93; 2.9 | 0.13 (0.005–0.40); 90 (48–134); 3.3 (1.8–5.3) |
| Fate: MGE divisions; interneurons in the cortex | 0.30; 10 | 0.24 (0.01–0.48); 8 (3–20) |
| Migration: radial speed; pyramidal cells in L4; interneuron coverage | 0.022; 0%; 47% | 0.032 (0.013–0.047); 54% (0–100%); 48% (10–83%) |
| Axons: gradient gain B; receptor gain; arrival threshold; arbor branching | 0; 0.30; 1.0; 0.12 | 1.35 (0.93–1.61); 1.03 (−0.29–2.0); 0.92 (0.05–1.92); 0.16 (0–0.30) |
| Axons: map slope; axons that arborise | −0.03; 49% | 0.99 (0.82–1.06); 97% (78–100%) |
| Refinement: competition; thalamocortical synapses grown → kept | 0; 84 → 84 | 0.37 (0.02–0.71); 252 → 193 |
| Activity: excitatory, inhibitory weight; decoding error | 140, 100; 0.27 | 326, 411; 0.071 (0.03–0.12) |

The map gain B rises in every run, and in every run nearly all axons end up arborising; how they get there differs
(receptor gain from −0.29 to 2, arrival threshold from 0.05 to 1.9, depending on where the neurons settled), and other
genes drift more (the inhibitory weight ends anywhere from 200 to 860), which is expected when several combinations of
genes give similar fitness. Use **keep parent** for a (1 + λ) strategy that does
not lose its parent.

## How close the port is to the toolbox
**Identical** (checked against Python in `tests/test_docs_playground.py`):
- the `lif_int` kernel: `NGJS.Simulator` / `NGJS.simulate` give the same spikes, tick by tick, as
  `neurogenesis.spiking.reference.IntegerSNNSimulator` (integer leak and synaptic decay, xorshift32 Poisson drivers,
  bursters, refractory period, multi-word spike history for delays above 31 ticks);
- the gene coding (`fromUnit`, `toUnit`, `getGene`, `setGene` as `neurogenesis.genome`), `seedsOf`, `coactivity`
  (as `neurogenesis.stages.refinement.coactivity`) and `competitiveLosers` (the losers of `competitive_elimination`
  with `remove: true`);
- `CueField` values (as `neurogenesis.fields.maps.CueField`), and `growArbors` with cue guidance, a target threshold
  and confinement: without angle noise or branching (so without random draws) it grows the same nodes as
  `grow_arbors`.

**Simplified**:
- the stages work in 2D on a small struct-of-arrays tissue and follow the formulas of the Python stages, but their
  random numbers come from JavaScript streams (one per stage, seeded from the development seed and the stage name), not
  NumPy's PCG64: the same genome and seed do not give the same network in Python and in the browser;
- `growArbors` grows one neurite per cell in 2D; its random draws come in the same order as in Python (stop, angle
  noise, branch, branch direction) but from a JavaScript stream. Only arbor nodes make synapses (the Python
  `arbor_synapses` lets every axonal node make contacts, so the shaft's contacts on its way are not modelled), each
  candidate (node, cell) pair gets one draw, and the closest pair per (axon, cell) is kept;
- the cells that release the cue are chosen by a laminar expression profile computed from their depth, which stands for
  the layer-identity genes a Python schedule would express;
- each interneuron's tangential speed is scaled by a random factor (where it leaves the stream), and its depth is
  taken from the nearest pyramidal cell; the toolbox's `migrate` has no random motion;
- the thalamus is drawn below the slice for clarity: real thalamocortical axons reach the cortex through the internal
  capsule, not across the ventricular zone;
- the Python `grow_arbors`, `grow_axons`, `proliferate` and `migrate` take many more options (fields, expressions, cell lists, sparse
  guidance) than the port.

## JavaScript API
In a page that loads `ng-core.js`, the functions are in `window.NGJS`; in Node, `require("docs/_static/ngjs/ng-core.js")`.

```javascript
const NG = require("./docs/_static/ngjs/ng-core.js");
const D = NG.CortexMapDemo;

// grow and evaluate a genome on three development seeds
const founder = D.assess(D.FOUNDER, [1, 2, 3]);
console.log(founder.fitness, founder.phenotype.slope);        // 0.01 and 0: no map yet

// edit a gene by hand: a matched receptor gradient
const g = NG.deepClone(D.FOUNDER);
g.axon.B = 1.2;
console.log(D.assess(g, [1, 2, 3]).phenotype.slope);

// evolve: 20 generations of the best of 10 offspring
const evo = NG.Evolution({ lambda: 10, sigma: 0.1 });
for (let k = 0; k < 20; k++) evo.step();
console.log(evo.history.map((h) => h.validation.toFixed(2)).join(" "));
```

| Function | What it does |
|---|---|
| `Simulator(cells, csr, seed)`, `simulate(cells, csr, ticks, seed, drive)`, `buildCSR(N, pre, post, weight, delay)` | the `lif_int` kernel; `drive(t, sim)` may set `sim.poissonThresh` before each tick |
| `fromUnit`, `toUnit`, `getGene`, `setGene`, `seedsOf` | gene coding and development seeds |
| `coactivity`, `competitiveLosers` | activity measures of the refinement stages |
| `seedCells`, `cellCycleClock`, `proliferate`, `migrate`, `mosaic`, `growAxons` | the 2D stages |
| `Stream(seed, name)` | the random stream of a stage |
| `CortexMapDemo.develop(genome, seed)` | grow one individual: `{net, record, tissue}` |
| `CortexMapDemo.evaluate(dev, seed, keepRasters)` | fitness and its factors, decoded positions, spike rasters |
| `CortexMapDemo.assess(genome, seeds)`, `phenotype(dev, ev)` | mean over seeds; per-stage summary |
| `Evolution(opts)` | `step()`, `work(budgetMs)` (one generation spread over animation frames), `history`, `setParent(genome)` |
