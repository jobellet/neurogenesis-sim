# Functional Connectomics & Metrics

`neurogenesis.metrics` measures functional pair interactions, stimulus tuning, and connectivity multiplicity rules.

## Scientific Grounding

- **MICrONS wiring rule ("like-to-like")**: In the mouse visual cortex millimetre cube, connection probability and
  synaptic contact count per pair increase linearly with the neurons' residual signal correlation (correlation
  adjusted for somatic distance and retinotopy; reported $P = 0.009$; Nature 640:8058, 2025; PMC11981947).
- **Developmental sequence**: Layer 2/3 orientation selectivity is established before eye opening (pre-P14 mouse)
  by feedforward thalamic and layer 4 inputs, while recurrent intralaminar connections remain random and uncorrelated
  with functional preference. Only after eye opening does activity-dependent rearrangement strengthen concordant pairs
  and prune divergent ones (Ko, Ho, Mrsic-Flogel et al., 2013, Nature / PubMed 23552948).

## Functional Pair Metrics

Module `neurogenesis.metrics.function`:
- `pair_correlations(spikes_or_rates, pre, post)`: Pearson correlation of response series across time or trials
  for given (pre, post) cell pairs. Vectorised and chunked for linear memory bounds.
- `residual_correlations(pairs_corr, soma_distance, rf_distance=None)`: per-pair residual signal correlation
  after regressing out somatic distance (and RF coordinate distance).
- `multiplicity_regression(residual_corr, contacts, pre=None, post=None, bins=5)`: OLS regression of synaptic
  multiplicity on residual correlation. Returns slope, standard error, analytic two-tailed $t$-test $p$-value
  (no external dependencies), $R^2$, and binned reciprocity.
- `tuning_metrics(responses, angles, annulus_responses=None)`: global orientation selectivity index
  $$gOSI = \frac{|\sum_\theta R(\theta) e^{2 i \theta}|}{\sum_\theta R(\theta)}$$
  and surround suppression index (SSI).

```python
from neurogenesis.metrics.function import multiplicity_regression, pair_correlations, residual_correlations, tuning_metrics

corrs = pair_correlations(raster, pre, post)
res_corr = residual_correlations(corrs, distances)
reg = multiplicity_regression(res_corr, contacts, pre=pre, post=post)
print(f"Multiplicity slope: {reg['slope']:.3f}, p = {reg['p_value']:.4e}")
```

Registered fitting metrics:
- `multiplicity_slope`: regression slope of contact multiplicity on residual correlation.
- `mean_gOSI`: population mean orientation selectivity index.

## In-Silico Stimulus Bank

Module `neurogenesis.metrics.stimuli`:
- `generate_natural_movie(n_frames, height=32, width=32, seed=0)`: deterministic spatio-temporally correlated
  random movie bank in $[0, 1]$ (AR(1) temporal dynamics and spatial Gaussian convolution).
- `movie_input_currents(movie, cell_positions, rf_sigma=0.08, gain=300.0)`: projects movie frames onto cell
  receptive fields via 2D Gaussian integration. Same movie + same seed produces identical currents. No network downloads.

## Example: Two-Phase Cortical Microcircuit

`examples/cortical_microcircuit.py` demonstrates the emergence of the like-to-like wiring rule:
1. **Phase 1 (pre-eye-opening)**: Feedforward inputs drive layer 2/3 selectivity ($gOSI > 0.25$), but recurrent
   multiplicity is uncorrelated with residual correlation ($P > 0.05$).
2. **Phase 2 (post-eye-opening)**: Natural movie stimulation + STDP refinement + pruning + scaling produce significant
   like-to-like multiplicity scaling ($P < 0.01$) while preserving orientation tuning and surround suppression.
