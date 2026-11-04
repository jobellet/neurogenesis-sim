# Hypothesis note: predictive representations from evolved local plasticity (written 2026-11-04, before any run)

This note is written before any of the code it needs exists (roadmap tasks E6–E9 and K7). Its predictions are
hypotheses about **this simulation**, not claims about biology or about the machine-learning model it borrows from.
The outcome of each step is appended below, dated, after the runs.

## Question
Can genes alone, that is a developmental program and local plasticity rules with no learning objective and no gradient
inside the network, produce spiking networks that, after passive exposure to video, represent it in a way that scores
well on a masked latent-prediction criterion modelled on the objective of V-JEPA 2.1 (Mur-Labadia et al. 2026,
arXiv:2603.14482)? Which parts of that objective must be in the fitness, and which can appear as mechanisms
(architecture, plasticity, homeostasis, developmental timing) that evolution selects?

## The objective borrowed from V-JEPA 2.1
- Two views of a clip: an encoder $E_\theta$ sees only the visible tokens of a masked clip $x$; a target encoder
  $E_{\bar\theta}$ (exponential moving average of $\theta$, momentum 0.99925, under stop-gradient) sees the full clip
  $y$. A predictor $P_\phi$ predicts the target features from the context features and positioned mask tokens.
- Masked term:
  $\mathcal{L}_\text{predict} = \frac{1}{|M|}\sum_{i\in M}\lVert P_\phi(E_\theta(x))_i - \mathrm{sg}(E_{\bar\theta}(y)_i)\rVert_1$.
- Context term (new in 2.1): the same error on the visible tokens, weighted by $\lambda_i = \lambda/\sqrt{d_\min(i, M)}$
  (distance to the nearest masked token); $\lambda$ is 0.5 for video and 0.7 for images, warmed up between epochs 50
  and 100.
- Deep self-supervision: four encoder levels (blocks 12, 24, 36 and 48 of the ViT-G) are fused for the predictor, which
  predicts the four target levels; both terms apply at each level.
- Masks: blocks of 15–70 % of the frame, as tubes over the whole clip. Tokens are 16 × 16 pixels × 2 frames.
- Ablation (their Table 1): the context term alone makes dense features (ADE20K 22.2 → 33.8 mIoU; NYU depth RMSE
  0.682 → 0.474) but lowers global ones (ImageNet −9.6, SSv2 −10.3 points); deep self-supervision restores most of the
  global score (SSv2 72.1, ImageNet 80.8) and improves the dense one further (ADE20K 38.6).
- Collapse is avoided only by the training dynamics (moving-average target, stop-gradient, predictor); the paper has
  no explicit information term.

Two consequences for an evolved network:
1. The L1 loss cannot be the fitness. On a frozen network a constant code has zero prediction error, and evolution would
   find it. The fitness must count information: how much of the representation of the hidden parts is predictable from
   the representation of the visible parts (predictive information: Bialek et al. 2001, Neural Comput; measured in a
   retina by Palmer et al. 2015, PNAS).
2. Only the experimenter computes the criterion, to select genomes. Nothing computes it during a lifetime.

## Model (two loops)
**A lifetime** (one development seed, one environment seed):
1. Development (stages of `docs/STAGES.md`): retinotopic levels grown from genes with `seed_cells`, `proliferate`,
   `migrate`, `differentiate` (excitatory and inhibitory types) and `grow_axons` with topography (feedforward spread per
   level, lateral range, optional feedback onto the dendrite with K7), then `myelinate`.
2. Spontaneous activity before exposure: `refine_by_activity` with waves whose parameters are genes (retinal waves
   carry optic-flow-like structure: Ge et al. 2021, Science).
3. Exposure (E6): a stream of frames from the individual's world, turned into input currents by ON/OFF centre-surround
   input cells with transient and sustained responses (in the example, not in the toolbox core), while the plasticity
   rules of E7 act online.
4. `critical_period_gate` closes plasticity; `freeze`.

**Evolution:** `evolution.islands.evolve` with fresh development and environment seeds every generation; fitness =
worst + 0.25 × mean − cost over the seeds (`evolution.robust.robust_value`), the cost being the metabolic term below;
one island per founder (below); `choose` on validation seeds and `audit` on held-out seeds.

## Genome
- **Architecture:** number of levels, cells per grid position, excitatory and inhibitory types, feedforward spread per
  level, lateral range and profile, feedback (present or not, target compartment), delays.
- **Plasticity**, per synapse class (feedforward, lateral excitatory, inhibitory onto excitatory, feedback): the
  coefficients of the E7 template

  $$\Delta w_{ij} = \eta\,\bar x_j\left[a_0 y_i + a_1 y_i(y_i-\theta_i) + a_2\frac{y_i-\bar y_i}{\sigma_i^2} - a_3\,\Delta\bar y_i + a_4(y_i-\hat y_i) + a_5\,m\,y_i\right] - a_6\,y_i^2\,w_{ij}$$

  where $\bar x_j$ is the presynaptic trace, $y_i$ the postsynaptic trace, $\theta_i$ a sliding threshold, $\bar y_i$
  and $\sigma_i^2$ the running mean and variance of $y_i$, $\Delta\bar y_i$ the change of $y_i$ over one frame,
  $\hat y_i$ the dendritic prediction of somatic activity and $m$ a neuromodulatory surprise signal; plus the STDP
  window, the time constants and the learning rates. Hebb ($a_0$), Oja ($a_0$, $a_6$), BCM ($a_1$; Bienenstock et al.
  1982, J Neurosci), latent predictive learning ($a_2$, $a_3$; Halvagal & Zenke 2023, Nat Neurosci), dendritic
  prediction ($a_4$; Urbanczik & Senn 2014, Neuron) and a three-factor rule ($a_5$) are points of this space.
- **Homeostasis:** target rate per cell type, gain and time constant of intrinsic plasticity (Triesch 2007, Neural
  Comput), synaptic scaling.
- **Timing:** onset and end of plasticity per synapse class and level (later lateral and feedback plasticity is the
  counterpart of the warm-up of $\lambda$), closure of the critical period.
- **Spontaneous waves:** speed, size, interval, duration.
- **Internal masking (optional):** random patchy inhibition of the feedforward input during exposure (probability, patch
  size); off in the founders.

Founders, one island each: latent predictive learning; BCM + intrinsic plasticity + anti-Hebbian lateral inhibition
(Földiák 1990, Biol Cybern) + inhibitory STDP (Vogels et al. 2011, Science); dendritic prediction (after K7); a
three-factor rule gated by a surprise signal (after Illing et al. 2021, NeurIPS); random.

## Worlds
Steps 1–3 use procedural worlds that carry ground truth: textured sprites moving over textured backgrounds, with
occlusions, at 16 × 16 to 32 × 32 pixels and 30 frames/s, generated from the environment seed. A world fixes the
texture family, the motion statistics (speed and direction distributions, egomotion), the dominant orientations and the
luminance polarity; one lifetime is spent in one world. Natural video comes in step 4.

## Fitness (E8)
- **Tokens:** at each level ℓ, the spike-count vector of the cells at each grid position, per frame window.
- **Masks:** spatial tubes over the whole evaluation clip (so that nothing can be copied from neighbouring frames),
  sized to each level's receptive fields. The way of masking is varied: mean luminance, input cells silenced, noise, a
  moving occluder.
- **Views and predictor:** for a held-out clip, targets $z = R_\ell(\text{full clip})$ and context
  $\hat z = R_\ell(\text{masked clip})$. The predictor $g$ is (B) a closed-form ridge regression from the context tokens
  around a masked token, fitted on half of the evaluation clips and scored on the other half, or (A), after K7, the
  network's own response at the masked position (filling-in).
- **Terms:** $I^M_\ell$ is the InfoNCE score of $g(\hat z)_i$ against $z_i$ over the masked tokens, with negatives from
  the other positions of the same clip and from the same position in other clips (van den Oord et al. 2018,
  arXiv:1807.03748); $I^C_\ell$ is the same over the visible tokens, weighted by $\lambda/\sqrt{d(i, M)}$.
- **Fitness:** $F = \sum_\ell (I^M_\ell + \lambda I^C_\ell) - \beta\,(\text{spikes} + \text{synapses})$; $\lambda$ and
  $\beta$ are fixed before step 2 and recorded here.

Same-clip negatives are the counterpart of the context term: a code that is the same at every position cannot tell
which position it predicts. Other-clip negatives make the code depend on content. The sum over levels is the deep
self-supervision, and the cost acts as an information bottleneck. A Gaussian estimate from the canonical correlations
$\rho_k$ between $g(\hat z)$ and $z$, $I \approx -\tfrac12\sum_k \log(1-\rho_k^2)$, is reported next to InfoNCE.

## Conditions and controls
- **Exposed:** the lifetime above.
- **Unexposed:** no stream (dark: the input cells receive no current; TTX: no spikes during the exposure window).
- **Shuffled:** the same frames in a random order (temporal structure destroyed, frame statistics kept).
- **Cross-reared:** reared in world A, evaluated in world B.
- **Random:** the same architecture with plasticity off.
- **Fitness variants** for H2–H5: L1 latent prediction without negatives; negatives from other clips only; last level
  only; one world for every generation.

## Metrics (per development seed and environment seed)
1. $F$ and its terms; the learning gain $\Delta F = F_\text{exposed} - F_\text{unexposed}$.
2. Effective dimension of each level's tokens: the participation ratio $(\sum_k\mu_k)^2/\sum_k\mu_k^2$ of the
   eigenvalues $\mu_k$ of their covariance.
3. Probes never used for selection: ridge decoding of local orientation, motion direction, speed and depth order at each
   token (ground truth of the procedural worlds); decoding of the world's parameters from the top level; object tracking
   by cosine label propagation between frame windows (as in the paper's DAVIS protocol).
4. The evolved coefficients, and the effect of knocking each one out (set to 0, same seeds).

## Predictions (hypotheses, in this simulation)
- **H1 (the fitness detects learning; step 1, hand-set rules, no evolution).** For latent predictive learning and for
  BCM + intrinsic plasticity + anti-Hebbian inhibition, $F_\text{exposed} > F_\text{unexposed}$ and
  $F_\text{exposed} > F_\text{shuffled}$ in at least 9 of 10 paired seeds. If H1 does not hold, the fitness is revised
  before any evolution run, and the revision is recorded here.
- **H2 (an L1 fitness collapses).** Evolved with the L1 fitness, the effective dimension of the top level falls below 2
  within 50 generations in at least 4 of 5 islands; evolved with $F$, it stays at 5 or more in the best genome of every
  island.
- **H3 (same-clip negatives make features dense).** Compared with negatives from other clips only, same-clip negatives
  raise the local probe scores by more than one pooled SD, while the global probe changes by less than one pooled SD.
- **H4 (levels).** Summing $F$ over levels, rather than taking the last level only, raises the probe scores of the
  intermediate levels by more than one pooled SD and keeps the top level within one pooled SD.
- **H5 (variable worlds select learning).** With one world for every generation, the learning gain of the best genome
  falls across generations (Spearman correlation between generation and $\Delta F$ below 0) while the unexposed score
  rises: genetic assimilation (Hinton & Nowlan 1987, Complex Systems). With one world per individual, $\Delta F$ stays
  above 0 in every audit, and cross-reared networks score higher in their rearing world than in the other in at least 8
  of 10 paired seeds (Stephens 1991, Behav Ecol).
- **H6 (evolved rules keep a predictive and a homeostatic term).** In the best genome of at least 3 of 5 islands, a
  predictive coefficient ($a_3$ or $a_4$) is non-zero and its knockout lowers $F$ by more than one SD over seeds; a
  homeostatic term (intrinsic plasticity or $a_1$) is kept too, and its knockout lowers $F$ or the effective dimension.
- **H7 (filling-in; after K7, predictor A).** With the internal predictor, $I^M$ is above its value for shuffled
  (mismatched) pairs in at least 9 of 10 seeds, and knocking out the lateral and feedback projections removes this
  excess while the probes of the visible tokens stay within one SD.

Absolute probe scores are expected to be far below those of V-JEPA 2.1; only comparisons within this simulation are
made.

## Seeds and reporting
Evolution uses 4 development seeds and 4 environment seeds per individual and generation, fresh every generation
(`seeds_of`); `choose` uses validation seeds 2000–2019 and `audit` held-out seeds 1000–1019 (`evolution.robust`). Every
prediction uses at least 10 seeds per condition, compared seed by seed: the 100-seed rerun of the retina → relay note
showed that unpaired comparisons waste most of the seeds. Each prediction is reported as held, not held or weak (right
direction, less than one pooled SD), whatever the outcome; deviations from this plan are listed with the outcome.

## Steps
1. H1: hand-set rules on one level (needs E6, E7 without the dendritic rule, and E8).
2. H2 and H6: rules evolved on a fixed two-level architecture with 16 × 16 inputs (needs E9).
3. H3–H5: architecture and rules evolved together, three levels, worlds varied.
4. H7 with K7, larger inputs and natural video; a small V-JEPA trained by backpropagation at the same resolution gives
   a ceiling.

Compute (an estimate, to be replaced by `python -m neurogenesis estimate`): 5,000 neurons, 500,000 synapses and 60 s of
stream at 30 frames/s (60,000 ticks) with plasticity take about 6 × 10¹¹ operations per individual, about a minute on a
CPU; a generation of 64 individuals × 4 seeds then takes hours on a laptop and minutes on a GPU with batched runs.
Short exposures screen every individual and long ones only the best.

## Outcome
To be appended, dated, after each step.
