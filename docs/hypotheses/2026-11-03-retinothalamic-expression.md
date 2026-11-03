# Hypothesis note: retina → relay map read from expression (written 2026-11-03, before any run)

This note is written before the variant `python examples/retinothalamic.py --map-source expression` is run (no pilot
run either: the variant has only been built, not grown). Its predictions are hypotheses about **this simulation**, not
claims about biology. The outcome is appended below, dated, after the runs.

## Question
In runs 1–3 of {doc}`../use-cases/retinothalamic` the graded EphA-like (x) and EphB-like (y) genes are computed by
`express` but read by nothing: the retina → relay map comes from the gains on the diagonal of `B`, and EphA-KO sets the
x gain to 0. When the map is instead read from the expression by the `expression_gradient` target rule, and EphA-KO
removes the gene (expression 0 in every cell), does the model give the same conclusions?

## Variant (differences from run 2, everything else unchanged: seeds 0–9, genome, stages, metrics)
- `express_fate` names its three genes `fate`, `EphA`, `EphB`; the EphA morphogen gain is 1 in every condition.
- `grow_axons` retina → relay: `B = 0`, `rules_target = ["expression_gradient"]` with EphA on axis 0 and EphB on axis 1,
  gain 2, attraction, min-max normalisation over the projection's source cells. Target logit per axis
  4 · 2 · (e − 0.5), the same slope as `B = diag(2, 2, 0)` if e were the local position.
- EphAKO: `express(knockout=["EphA"])` sets the EphA column to 0 after each `express_fate` step. A constant gene
  normalises to 0.5, so the x target is the centre of the relay, as with a 0 gain in `B`.

The EphA level is sigmoid(−3 + 2 x) (x the local retinal position), so after min-max normalisation it is a convex,
not linear, function of x (0.32 at x = 0.5); the same for EphB on y. The expression-read target is therefore a
monotonic but distorted version of the `B` target, pushed towards the low end of each axis.

## Predictions (hypotheses, in this simulation)
- E1 (map orientation): in WT, b2KO and TTX the map keeps both axes: r_x, r_y > 0.5, positive.
- E2 (knockout): EphAKO gives |r_x| < 0.3, with r_y within 0.1 of WT of the same variant.
- E3 (distortion): the expression-read WT map has a higher topographic error than the `B` WT map of run 2 (error
  measured against the `B` target point), by more than one pooled SD; r_x and r_y stay within 0.1 of the `B` WT values.
- E4 (activity): as in runs 1–3, TTX and b2KO move topographic error up and corner separation down relative to WT of
  the same variant, by less than one pooled SD (weak).
- E5 (unchanged upstream): the RGC mosaic (NND/SD) is identical to run 2 for every seed and condition, since the
  changes act after `mosaic` and the fate gene does not read EphA or EphB.

## Seeds and reporting
Seeds 0–9 for every condition, `python examples/retinothalamic.py --cpu --seeds 10 --map-source expression`, compared
with run 2 (the `B` variant, rerun on the same commit). Mean ± SD per condition and paired differences per seed. Each
prediction is reported as held / not held / weak, whatever the outcome.

## Outcome (appended 2026-11-03, after the runs)
10 seeds (0–9) per condition, `python examples/retinothalamic.py --cpu --seeds 10 --map-source expression`, and the
`B` variant rerun on the same commit (identical to run 2); table in {doc}`../use-cases/retinothalamic`.
- E1: held: r_x, r_y between 0.889 and 0.896 in WT, b2KO and TTX.
- E2: held: EphAKO r_x 0.031 ± 0.074; r_y 0.890 ± 0.031 (WT 0.889 ± 0.033).
- E3: held: WT error 0.254 ± 0.013 against 0.230 ± 0.016 with `B` (paired +0.023 ± 0.010, pooled SD 0.014; 10 of 10
  seeds); r_x −0.015, r_y −0.022.
- E4: held as weak: TTX error +0.0034, separation −0.005; b2KO +0.0033, −0.003 (paired means), all below one SD.
- E5: held: the mosaic is identical to run 2 for every seed.
- Not predicted: the corner separation is higher than with `B` (0.763 ± 0.078 against 0.671 ± 0.088, higher in 10 of
  10 seeds).
- Deviations from the plan: none.
