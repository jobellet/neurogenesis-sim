# Hypothesis note: retina → thalamic relay development (written 2026-11-02, before any run)

This note is written before the example `examples/retinothalamic.py` is run. Its predictions are hypotheses about
**this simulation**, not claims about biology. The outcome is appended below, dated, after the runs.

## Question
In a toy two-region model (a retinal sheet projecting to a thalamic relay nucleus, loosely after the mouse retina →
dLGN projection between embryonic day 14 and postnatal day 14), which parts of the final map depend on molecular
guidance and which on patterned spontaneous activity? Specifically: does removing the x-axis chemoaffinity gradient,
removing correlated waves, or removing all activity change (a) the retinal ganglion cell (RGC) mosaic, (b) the
orientation of the map along each axis, and (c) its precision?

## Model (toolbox stages, see docs/STAGES.md)
Two `Box` regions (retina, relay), analytic gradient `AnalyticField`s along x and y.
1. `seed_cells` retinal progenitors, `proliferate`.
2. `express` one fate gene with lateral inhibition (neighbour weights < 0), `differentiate` high expressers into RGCs
   (the other retinal cells get another region and do not project); relay cells: relay (excitatory) and local
   interneurons (inhibitory).
3. `migrate` (small soft repulsion), then `mosaic` (homotypic exclusion of RGCs).
4. `grow_axons` retina → relay with an exuberant, broad projection (large `sigma`): target map
   `sigmoid(4·(u − 0.5)·B + c)` where the diagonal of `B` is the chemoaffinity gain per axis (x: EphA/ephrin-A-like,
   y: EphB/ephrin-B-like counter-gradients, set from genes); relay interneuron → relay local projection.
5. `apoptosis` neurotrophic (`min_inputs` on relay cells, `min_outputs` on RGCs).
6. Pharmacology profile (glutamate/AMPA-like, GABA-A-like with an `immature` depolarising context):
   `set_transmitters`, `express_receptors`, `assign_receptors`, `pharmacology` in context `immature`.
   (`transporter_switch` is not on `main`, so the chloride switch is the P3 immature → mature context.)
7. `refine_by_activity` with spontaneous propagating waves (`waves`: sources, speed, interval, duration, amplitude)
   and STDP, repeated with several wave origins.
8. `pharmacology` context `mature`, `prune` (weight threshold), `scale`, `myelinate`, `freeze`.

## Conditions
- **WT**: both gradients, propagating waves.
- **β2-KO** (stand-in for β2-nAChR knockout): no propagating waves; RGCs fire as independent Poisson sources at a low
  rate during the same refinement window (uncorrelated activity).
- **TTX**: no spiking during refinement (the activity-dependent stages see no spikes; pruning is still applied by
  weight).
- **EphA-KO**: x-axis chemoaffinity gain set to 0 (no x gradient read-out); y unchanged; waves as WT.

## Metrics (per development seed)
1. Mosaic regularity of RGCs: nearest-neighbour regularity index NND mean / SD
   (`neurogenesis.analysis.nearest_neighbour_regularity`, on x, y).
2. Per-RGC weighted target centroid: the |weight|-weighted mean local (x, y) position of its relay targets
   (vectorised with `np.bincount`). Pearson r_x (RGC local x vs centroid x) and r_y; mean topographic error: mean
   Euclidean distance between the centroid and the WT chemoaffinity target point of that RGC (local units).
3. Evoked functional separation: drive the RGCs of two opposite retinal corners (local x, y < 0.25 vs > 0.75) with
   `spiking.batch.simulate_counts`; separation = 1 − cosine similarity of the two relay response vectors.

## Predictions (hypotheses, in this simulation)
- H1: mosaic regularity is unaffected by the three ablations (they act after the mosaic stage): each ablation's mean
  within 10 % of WT.
- H2: EphA-KO lowers r_x strongly (|r_x| < 0.3) while r_y stays within 0.1 of WT.
- H3: TTX and β2-KO keep the axis orientation (r_x, r_y > 0.5 and same sign as WT) but raise the topographic error
  and lower the corner separation relative to WT (difference in means in the predicted direction, larger than one
  pooled SD for "clear", otherwise "weak").

## Seeds and reporting
At least 10 development seeds per condition (seeds 0–9, the same seeds for every condition). The table reports
mean ± SD per condition. Each prediction is reported as held / not held / weak by the criteria above, whatever the
outcome.

## Outcome (appended 2026-11-02, after the runs)
10 seeds (0–9) per condition, `python examples/retinothalamic.py --cpu --seeds 10`; table in
{doc}`../use-cases/retinothalamic`.
- H1: held (trivially: the mosaic is identical across conditions because the ablations act after it).
- H2: held: EphA-KO r_x 0.021 ± 0.159 (WT 0.910 ± 0.021); r_y 0.911 ± 0.025 (WT 0.907 ± 0.031).
- H3: orientation held (r_x, r_y > 0.9 in TTX and β2-KO). Error and separation moved in the predicted direction
  (TTX error +0.003, separation −0.017; β2-KO +0.002, −0.013, paired means) but by much less than one pooled SD:
  **weak**, not clear.
- Deviations from the plan: the β2-KO Poisson rate was set equal to the WT mean RGC rate; `scale` runs before `prune`;
  the activity regime was set on pilot seeds 100–102 before the reported runs; `refine_by_activity` needed a
  workaround for its `waves` param (see the use case).

## Run 2 (appended 2026-11-02, after the toolbox fixes #81 and #82)
Not part of the pre-registered plan: the model layout was changed after run 1 was seen (waves restricted to the
retina, relay moved next to it, β2-KO drivers turned off after refinement). Same seeds and metrics. H2 held
(EphA-KO r_x 0.033 ± 0.157, r_y 0.911 ± 0.026); H3 orientation held, blurring still weak (TTX error +0.004,
separation −0.015; β2-KO +0.003, −0.006, paired means). Details in {doc}`../use-cases/retinothalamic`.

## Larger-seed rerun (appended 2026-11-04, after the runs; not part of the pre-registered plan)
The criteria above were not changed. The statistics below (paired tests, bootstrap intervals, power) were chosen after
the 10-seed results were known, so they are exploratory.
- **Seeds.** Run-2 settings: 100 seeds (0–99) per condition. Separation is undefined for seed 87 (all four conditions:
  every response vector of one corner stimulus was zero), so separation uses n = 99; every other metric uses n = 100.
  Seeds 0–9 reproduce the committed per-seed values (largest difference 2.8e-17). The run used a driver outside the
  repository that calls the same `build_project`, `run_schedule` and `measure`; its per-seed CSVs are not committed
  here.
- **Verdicts unchanged.** H1 held, H2 held (EphA-KO r_x 0.000 ± 0.131, r_y within 0.009 of WT), H3 orientation held
  (r_x, r_y 0.924 in TTX and β2-KO), H3 blurring **weak** by the one-pooled-SD rule: topographic error +0.0029 (TTX) and
  +0.0031 (β2-KO), ratio to the pooled SD 0.16 and 0.18; separation −0.0096 and −0.0049, ratio −0.09 and −0.05.
- **What 100 seeds add.** The topographic-error shift is small against the across-seed SD (0.018) but consistent within a
  seed: paired dz +1.06 (TTX, 95% CI 0.85 to 1.35) and +1.19 (β2-KO, 0.96 to 1.48), Wilcoxon p below 1e-13, error higher
  than WT in 86–87 of 100 seeds. "Weak" is therefore not a small-sample artefact, and it is not zero. The corner-separation
  drop is detectable for TTX (dz −0.37, p 0.002) and not for β2-KO (dz −0.17, interval includes 0). p-values are
  uncorrected.
- **Seeds needed.** For 80% power with a paired comparison: about 8–10 seeds for the topographic-error shift, about 60
  (TTX) to 280 (β2-KO, very uncertain) for separation. An unpaired comparison of the topographic-error shift would need
  about 510–590 seeds per group. Future runs should compare conditions seed by seed.
- **Means moved a little.** 100-seed WT separation is 0.621 against 0.671 at 10 seeds (seeds 0–9 happen to be high, about
  0.5 SD); r_x 0.921 against 0.911.

## 1000-seed rerun (appended 2026-11-04, after the runs; not part of the pre-registered plan)
The run-2 settings were extended to seeds 0–999 to settle the corner-separation endpoint, which the 100-seed power analysis
said needed hundreds of paired seeds. The sample size was chosen after seeing the 100-seed results and the statistics are
exploratory (uncorrected p-values). Seeds 100–999 ran on the cluster as 180 array tasks of 5 seeds (3.6 core-hours), at
commit dc2186b like seeds 0–99; seed 0 reproduces the earlier run exactly (largest difference 0). Separation is undefined
for 8 seeds (87, 127, 240, 289, 369, 401, 523, 811: no responding relay cell at a corner), so it uses n = 992; every other
metric n = 1000. The driver and per-seed files are not committed here.
- **Verdicts unchanged:** H1, H2 held (EphA-KO r_x 0.001, |Δr_y| 0.013), H3 orientation held (r_x, r_y 0.924 in TTX and
  β2-KO), H3 blurring **weak** by the one-pooled-SD rule: error +0.0032 (TTX) and +0.0034 (β2-KO), ratio 0.19 and 0.20;
  separation −0.0072 and −0.0037, ratio −0.06 and −0.03.
- **Topographic error:** paired dz +1.15 (95% CI 1.07 to 1.23) for TTX and +1.10 (1.02 to 1.19) for β2-KO, higher than WT in
  899 and 876 of 1000 seeds.
- **Corner separation, settled:** the drop is detectable for both conditions, and tiny. TTX −0.0072 (dz −0.28, CI −0.35 to
  −0.22, p 5e-17), β2-KO −0.0037 (dz −0.13, CI −0.20 to −0.07, p 1e-5); 0.06 and 0.03 pooled SD, so far below the
  one-SD criterion for "clear". The 100-seed estimates (−0.0096 and −0.0049) were slightly larger, within sampling noise.
- **Seeds for 80% power, paired:** about 9 for the topographic-error shift, about 99 (TTX) and 437 (β2-KO) for separation.
