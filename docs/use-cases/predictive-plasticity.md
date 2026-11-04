# Representations learned from video by evolved plasticity (planned)

**Idea.** Evolve genes, not weights. A developmental program grows a retinotopic spiking network, and gene-coded local
plasticity rules (Hebbian, STDP, BCM, intrinsic plasticity, dendritic prediction) shape it during passive exposure to
video. No learning objective runs inside the network. The experimenter scores the frozen network with a masked
latent-prediction criterion modelled on V-JEPA 2.1 (Mur-Labadia et al. 2026, arXiv:2603.14482), rewritten as an amount
of information so that a constant code scores zero. Evolution keeps the genomes whose networks score best across
development seeds and visual worlds.

**Correspondence with the V-JEPA 2.1 objective.**

| V-JEPA 2.1 | Counterpart here |
|---|---|
| prediction of masked tokens in latent space | plasticity that strengthens inputs predicted by their context (dendritic prediction, predictive terms); masked predictive information as the fitness |
| context term (dense features) | retinotopy and local connections; negatives from the same clip in the fitness |
| deep self-supervision | local rules at every level; fitness summed over levels |
| moving-average target and stop-gradient | homeostasis: intrinsic plasticity, sliding thresholds, inhibitory plasticity, lateral decorrelation |
| warm-up of the context weight | developmental timing of lateral and feedback plasticity (critical periods) |

**Stages.** Development as in the other use cases (`seed_cells` → `proliferate` → `migrate` → `differentiate` →
`grow_axons` with topography) → `refine_by_activity` (spontaneous waves) → `expose` (E6, with the rules of E7) →
`critical_period_gate` → `freeze`; the frozen network is scored with the metrics of E8 and evolved as in E9. The
dendritic predictor needs synapses that target the soma or the dendrite (K7). Tasks: {doc}`../development/roadmap`.

```{toctree}
:hidden:

../hypotheses/2026-11-04-predictive-plasticity
```

The hypotheses, metrics, controls and pass criteria were written before any code: {doc}`../hypotheses/2026-11-04-predictive-plasticity`.

```{admonition} PLACEHOLDER
:class: placeholder
The worked example (`examples/predictive_plasticity.py`, task E9) on procedural worlds, with the step 1–3 results of
the hypothesis note, once E6–E9 are merged; then natural video and the dendritic predictor (K7).
```
