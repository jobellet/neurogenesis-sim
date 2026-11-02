# Retina → thalamic relay: guidance, waves and their ablation

A toy two-region model loosely after the mouse retina → dLGN projection (E14–P14), grown by the stage pipeline and
compared across four conditions. Everything below holds **in this simulation** only; it is a demonstration of how to
set up and test a developmental hypothesis with the toolbox, not a biological finding.

    python examples/retinothalamic.py --cpu --seeds 10 --out out_dir      # about 1.5 min on 2 CPU threads
    python examples/retinothalamic.py --cpu --seeds 2 --small             # test configuration, about 10 s

The hypotheses, metrics and pass criteria were written before the runs: {doc}`../hypotheses/2026-11-02-retinothalamic`.

```{toctree}
:hidden:

../hypotheses/2026-11-02-retinothalamic
```

## Model
Two `Box` regions (a 100 × 100 retinal sheet, a 60 × 60 × 20 relay nucleus placed far away so that the retinal waves,
which spread through space, never reach it) and analytic x / y gradient fields. Stages (docs/STAGES.md):
`seed_cells`, `proliferate`, `express` (one fate gene with lateral inhibition through `neighbor_weights`, and two
graded genes read from the x / y gradient fields), `differentiate` (RGCs, other retinal cells, relay cells, relay
interneurons), `migrate`, `mosaic` (RGCs only), `grow_axons` (exuberant retina → relay projection, `sigma` 0.3, target
gain per axis `B = diag(2·EphA gain, 2·EphB gain, 0)`; interneuron → relay), `apoptosis` (relay cells with fewer than 3
inputs, through a per-cell `Field` for `min_inputs`), `set_transmitters` / `express_receptors` / `assign_receptors` /
`pharmacology` (context `immature`, depolarising GABA-A), four `refine_by_activity` calls with one propagating wave each
(random origin, speed 0.4 space units per tick, one 600-unit tick of drive per RGC) and STDP (`A_plus` 20,
`A_minus` 21), `pharmacology` (`mature`), `scale` (incoming sum 1500), `prune` (|w| < 150), `myelinate`
(retinal axons, factor 0.5), `freeze` (Dale check).

Conditions (genome values, `condition_genome`): **WT**; **b2KO**: no waves, RGCs fire as independent Poisson sources
at the same mean rate as one wave gives (one spike per RGC per 300-tick window); **TTX**: no refinement stages (no
spikes); **EphAKO**: x chemoaffinity gain 0.

## Results (10 development seeds per condition, seeds 0–9, mean ± SD)

| Condition | Mosaic NND/SD | r_x | r_y | Topographic error | Corner separation |
|---|---|---|---|---|---|
| WT     | 2.77 ± 0.53 | 0.910 ± 0.021 | 0.907 ± 0.031 | 0.232 ± 0.016 | 0.700 ± 0.078 |
| b2KO   | 2.77 ± 0.53 | 0.913 ± 0.018 | 0.912 ± 0.025 | 0.233 ± 0.014 | 0.687 ± 0.087 |
| TTX    | 2.77 ± 0.53 | 0.914 ± 0.021 | 0.911 ± 0.027 | 0.234 ± 0.015 | 0.684 ± 0.091 |
| EphAKO | 2.77 ± 0.53 | 0.021 ± 0.159 | 0.911 ± 0.025 | 0.396 ± 0.020 | 0.655 ± 0.097 |

Paired differences from WT (same seed), mean ± SD: TTX topographic error +0.0029 ± 0.0026 (higher in 9 of 10 seeds),
separation −0.017 ± 0.024 (lower in 6 of 10); b2KO error +0.0019 ± 0.0033 (7 of 10), separation −0.013 ± 0.020
(7 of 10); EphAKO error +0.164 ± 0.021 (10 of 10), r_x −0.889 ± 0.166. Per-seed values: `retinothalamic-results.json`
next to this page. About 66 RGCs, 145 relay cells and 710 retinal synapses per network.

## Which predictions held
- **H1 (mosaic unaffected): held, trivially.** The ablations act only on stages after `mosaic`, and every stage has its
  own random stream, so the mosaic is identical across conditions for a given seed. The mosaic is regular
  (NND/SD 2.8 against about 1.9 for random positions).
- **H2 (EphA-KO lowers r_x, not r_y): held.** r_x falls from 0.91 to 0.02 (|r_x| < 0.3), r_y changes by +0.004.
- **H3 (activity loss keeps the axes but blurs the map): orientation held; blurring weak.** TTX and b2KO keep
  r_x, r_y > 0.9. Their topographic error is higher and their corner separation lower than WT in the predicted
  direction, but every difference is far smaller than one pooled SD (the pre-registered criterion for "clear"), so the
  refinement effect is **weak** in this model. With a broad initial projection and only four waves, STDP followed by
  scaling and pruning changes the map little; most of the map's precision comes from the chemoaffinity term.

## Limits and toolbox findings
- `refine_by_activity` used to ignore its `waves` (and `twitches`) settings when run from a schedule (`run_schedule`
  wraps a dict param in `Const`). Found while writing this example and fixed in #81; the example now uses the stage
  directly. The results below were measured with an equivalent workaround, so they are unchanged.
- `grow_axons` resolves guidance values one level deep, so `B` cannot hold per-axis `Gene`s; the example builds `B`
  from the condition genome in Python. The graded genes produced by `express` are not read by the guidance rules (no
  expression-based target rule), so the EphA / EphB expression is illustrative and the gain in `B` carries the effect.
- Waves are applied to every cell in space; the relay is placed 1000 space units away so the wave never reaches it
  within a refinement window (`conduction_velocity` 200 keeps the delays short).
- `mosaic` with a `boundary` cancels every step of cells that start outside the geometry (here, cells displaced in z
  by `proliferate` jitter out of a thin retina box), so the example runs it without a boundary.
- Before the reported runs, the activity regime was set on pilot seeds 100–102 (not reported): wave drive of one
  600-unit tick (larger drive made RGCs and relay cells fire for tens of ticks), relay refractory period 5 ticks and a
  weak interneuron projection (otherwise the relay fired continuously under immature GABA), `scale` before `prune`, and
  the STDP amplitudes. These settings were chosen for a sensible firing regime, but they were tried with the outcome
  visible, so the weak H3 effect should not be read as a property of the mechanism in general.
