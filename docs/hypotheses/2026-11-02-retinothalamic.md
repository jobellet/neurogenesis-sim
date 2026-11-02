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
