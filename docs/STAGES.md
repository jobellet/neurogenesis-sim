# Stage, geometry and field reference

What the registered stages (tasks C1–C12), geometries and fields (B2–B5) and sparse guidance (D2) do in the code on
`main` (2026-11-02, after the fix waves F1–F9). Roadmap items that are not implemented are marked **Not implemented**. Defaults are those of the code; a stage called without
a parameter uses them.

## Conventions
- A stage runs as `{"name": ..., "operator": ..., "params": {...}, "when": ..., "repeat": k}` in a Project's `schedule`
  (`neurogenesis.stages.run_schedule`). Each repeat gets its own random stream, seeded from (seed, stage name, repeat).
- Every parameter is a `Param` (`Const`, `Gene`, `Field`, `Fit`, `Expr`; see `neurogenesis/params.py`) or a plain value.
  A `Field` param gives per-cell values only where the stage passes cell positions to `resolve`; this is noted below as
  "per cell". Elsewhere a `Field` param resolves to the field object itself and the stage fails.
- `when` is an expression evaluated by the restricted evaluator `neurogenesis.expressions.eval_expr` (no `eval`), with
  `N`, `N_alive`, `E`, `rep`, `tissue`, `genome`, `np`.
- Units: one tick = 1 ms; positions and distances in space units (the Project's coordinates); weights and thresholds in
  integer kernel units. Delays are limited only by the storage bound of 255 ticks (multi-word spike history in all four kernels; stages accept a `max_delay` Param).
- `cost(N, E, params)` returns (bytes, ops); `neurogenesis.stages.base.schedule_cost` sums it over a schedule, and
  `neurogenesis.devcost.estimate_development` (command line: `python -m neurogenesis estimate --project p.json`)
  predicts N and E stage by stage, the peak memory and the time on this machine.
- **Neutral** means the stage leaves the tissue unchanged. Every toolbox stage called with empty params is a
  no-op (tested for every registered stage except `legacy_grow_stage`, which needs its `plan`).

## Population (C1–C3, C14, `neurogenesis/stages/population.py`)

**`seed_cells` (C1).** Adds cells: `N` sampled uniformly in a geometry or placed at one position, a `density`
in a geometry, or a point set.
| Param | Default | Meaning |
|---|---|---|
| `N` | 0 | number of cells; `N <= 0` is a no-op |
| `geometry` | none | name of a geometry in the Project (or a `Geometry` object); cells drawn with `sample_points` |
| `position` | none | (3,) position used for all cells when `geometry` is absent |
| `region`, `cell_type` | 0, 0 | integer labels of the new cells |
| `jitter` | 0.0 | standard deviation of a Gaussian offset added to each position (space units) |
| `density` | none | cells per unit volume in `geometry` (replaces `N`): a number gives round(density × volume) uniform cells; a `Field` param is sampled by thinning against `max_density` (Lewis & Shedler 1979) |
| `max_density` | none | upper bound of a density field (required with a field) |
| `max_cells` | none | upper bound on the cells added with `density` or `points` |
| `points` | none | a list of positions (2D points get z = 0), a pattern dict (`pattern`: `regular` / `jittered` / `poisson_disc`, `bounds`, `spacing` / `jitter` / `radius`), or a `PointSetField`; with a `geometry`, points outside it are dropped |

Limits: one of `geometry` / `position` / `points` is required (`ValueError` otherwise). The volume is measured by
Monte Carlo (65 536 points, about 1 % error) from the stage's random stream; flat geometries are measured by area. The
cost assumes `N = 100` (or `max_cells`) unless `N` is a constant.

**`proliferate` (C2).** Each cycling alive cell (`Tissue.cycling`) divides with probability `prob`; the daughter is appended, the mother stays.
| Param | Default | Meaning |
|---|---|---|
| `prob` | 0.0 | division probability per cell and call (per cell; an `Expr` sees `cell_type`, `generation`, `cycling`, `birth_stage`, `region`, `x`, `y`, `z` and the top-level genes); 0 is neutral |
| `jitter` | 0.1 | standard deviation of the daughter's Gaussian displacement from the mother (space units, per cell) |
| `new_type` | none | cell type of the daughters (per cell); if absent daughters copy the mother's type |
| `max_cells` | none | upper bound on alive cells; if divisions would exceed it, a random subset divides so the bound holds exactly |
| `asymmetric_prob` | 0.0 | probability that a division is asymmetric (needs `daughter_type`) |
| `daughter_type` | none | cell type of the new daughter in an asymmetric division; the mother keeps its type (Götz & Huttner 2005, Nat Rev Mol Cell Biol) |
| `expression_noise` | 0.0 | standard deviation of Gaussian noise added to both daughters' expression, clipped at 0 |
| `birth_stage` | none | birth stage given to new daughters; if absent, one more than the latest alive `birth_stage` |

Daughters copy the mother's region, expression, sign, `cycling` (`True` by default for cells from `seed_cells` and
`proliferate`) and neuron parameters and record `parent_id` and `clone_id`; both daughters get `generation = mother's + 1`
(`Tissue.generation`). Dead cells and postmitotic cells (`cycling == False`, e.g. from `place_by_hand` or
`cell_cycle_clock`) do not divide.

**`apoptosis` (C3).** Kills cells, then compacts the tissue (connectivity re-indexed).
| Param | Default | Meaning |
|---|---|---|
| `prob` | none | death probability per cell (per cell) |
| `density_radius` | none | radius (space units, per cell) for counting neighbours |
| `max_density` | 10 | cells with more than this many neighbours within `density_radius` die |
| `min_inputs`, `min_outputs` | none | neurotrophic death: cells with fewer incoming / outgoing synapses die |

All criteria are off when absent. Neighbour counts use a dense N × N distance matrix for `N <= 2048` and the cell list
(`CellList`, D1) above. Limits: synapse counts ignore weights and activity.

**`cell_cycle_clock` (C14).** Called once per cell cycle before `proliferate` (Takahashi, Nowakowski & Caviness 1995,
J Neurosci; 1996, J Neurosci; Caviness et al. 2000). Each cycling alive cell (`Tissue.cycling`) advances its cycle
counter (`Tissue.generation`) and leaves the cell cycle (`cycling = False`) with probability
`Q(generation) = min(1, k · generation^a)` or from a per-generation table `Q` (`q_table`).
| Param | Default | Meaning |
|---|---|---|
| `k`, `a` | 0.0, 1.97 | power-law parameters for `Q(generation) = min(1, k · generation^a)` (per cell; `Const`, `Gene`, `Field` or `Expr`); `k <= 0` without `Q` / `T_C` is a no-op |
| `Q` (or `q_table`) | none | per-generation exit probability table (1-indexed by cycle `generation`) or per-cell `Param`, overriding `k` and `a` |
| `T_C` (or `tc_table`, `tc`) | none | per-generation cycle length table or formula (`Param`); advances each cycling cell's cumulative `Tissue.birth_time` |

Leaving cells get `cycling = False` and their exit `generation` (birth cycle) and `birth_time` are frozen across later
cycles, while the immediately following `proliferate` completes the current cycle's division for all cells that entered
the cycle (producing two postmitotic daughters for leaving progenitors and two cycling progenitors for self-renewing
ones). Reference neocortical profile: `examples/profiles/cell_cycle_clock.json`.

## Migration and sorting (C4–C5, `neurogenesis/stages/migration.py`)

**`migrate` (C4).** Moves alive cells for `steps` sub-steps per call (Marín & Rubenstein 2003, Annu Rev Neurosci).
| Param | Default | Meaning |
|---|---|---|
| `steps` | 1 | sub-steps per call; `speed` and `chemotaxis` are distances per sub-step |
| `speed` | 0.0 | step length along `direction` (space units, per cell); 0 is neutral |
| `direction` | (1, 0, 0) | step direction (per cell, e.g. a vector field), normalised |
| `radial` | False | step away from `target` instead of along `direction` (per cell) |
| `target` | (0, 0, 0) | centre for radial steps |
| `chemotaxis_field`, `chemotaxis` | none, 0.0 | move along the unit gradient of a named scalar field (central differences, step `gradient_step`, default 1e-3); negative values move down the gradient |
| `layer_field`, `target_layer` | none, 0 | a cell stops once its layer label (first column of the field, e.g. `LayerStackField`) equals `target_layer` |
| `min_distance` | 0.0 | soft repulsion through the cell list: each cell of a pair closer than this moves half the overlap |
| `stop_field` | none | evaluated at the new position; True or a value > 0 cancels the step for that cell |
| `boundary` | none | geometry name; a step that would leave it is cancelled |
| `tangential` | False | (per cell) remove the component of `direction` along the radial vector from `target`, so cells move perpendicular to it (tangential migration) |

Limits: deterministic (no random motion). Tangential steps are straight, so they drift outwards by O(speed²/r) per
step. **Not implemented:** the inside-out layering test case as a test of `migrate` alone.

**`sort` (C5).** Two modes, run in this order when both are given; with neither, a no-op.
- **Ordering:** reassigns the cells' coordinates along `axis` so that their order along it follows `key`
  (`"birth_stage"`, `"expression"` (column 0) or a per-cell array), keeping the perpendicular coordinates.
- **Differential adhesion** (Steinberg 1963, Science): for `steps` iterations, neighbours within `radius` (cell list)
  attract or repel according to `adhesion[type_i, type_j]` (negative = repulsion), at rate `rate`; cells closer than
  `contact` (default `radius / 2`) push apart. The matrix must cover every living cell's type.

| Param | Default | Meaning |
|---|---|---|
| `axis`, `key` | (0, 0, 1), `"birth_stage"` | ordering mode (active when either is given) |
| `adhesion` | none | types × types matrix (adhesion mode) |
| `radius`, `contact`, `rate`, `steps` | 0.1, radius/2, 0.1, 1 | adhesion-mode interaction radius, contact distance, rate, iterations |

Limits: no random motility, so weak cross-type adhesion gives local clumps rather than full separation.

**`mosaic` (C5).** Homotypic exclusion zones: for `steps` iterations, living cells of the same type closer than
`radius` move apart by `rate` × half their overlap (cell list), plus optional Gaussian motility `jitter` from the stage
random stream; `types` restricts it to some cell types and `boundary` keeps cells in a geometry. This raises the
nearest-neighbour regularity index of each type (Galli-Resta et al. 1997, J Neurosci); other types are ignored.
| Param | Default | Meaning |
|---|---|---|
| `radius` | 0.0 | exclusion radius (space units); <= 0 is the no-op |
| `steps`, `rate`, `jitter` | 1, 1.0, 0.0 | iterations, fraction of the overlap removed, motility std |
| `types`, `boundary` | all, none | cell types that interact; geometry that cells may not leave (cells already outside it move freely) |

## Expression and differentiation (C6–C7, C15, `neurogenesis/stages/differentiation.py`)

**`express` (C6).** One gene-regulatory step on the expression matrix (N, K):
`E ← E·(1 − decay·dt) + sigmoid(W·E + Σ_m f_m·w_m + W_n·Σ_neighbours E)·dt`.
| Param | Default | Meaning |
|---|---|---|
| `K` | 0 | number of genes; `K <= 0` (or no params) is a no-op; expression is padded or cut to K columns |
| `weights` | zeros | K × K regulatory weights `W` (or K² values) |
| `morphogens` | [] | list of `{"field": Param, "weights": [K]}`; the field is evaluated at the cell positions; each weight may be a `Param` (e.g. a `Gene`) |
| `radius` | 0.0 | contact radius (space units) for neighbour input through the cell list; 0 disables it |
| `neighbor_weights` | zeros | K × K weights `W_n` applied to the **sum** of neighbours' expression |
| `dt`, `decay` | 1.0, 0.0 | step size and linear decay rate |
| `activation` | `"sigmoid"` | `"sigmoid"`, or `"hill"`: x⁺ⁿ / (kⁿ + x⁺ⁿ) of the positive part x⁺ of the input |
| `hill_n`, `hill_k` | 2.0, 1.0 | Hill coefficient and half-activation input |
| `names` | unset | K distinct gene names stored in `Tissue.expression_names` (read by the `expression_gradient` rule); unset leaves the names as they are |
| `knockout` | [] | genes (names or column indices) set to 0 in every cell after the step (a null allele) |

Dead cells are kept (only the runner compacts). Limits: with `K > 0` the step is not a no-op even with zero weights (sigmoid(0) = 0.5 is
added); weight matrices of the wrong shape are silently replaced by zeros (the Hill activation is 0 for zero input). The
cost is O(N K²) (plus the cell-list query when `radius > 0`) and uses a `Gene`'s upper bound for `K`.

**`differentiate` (C7).** Applies a rule table `types`: for each entry, in order, cells matching `condition` get the
listed properties (later entries override earlier ones).
| Entry key | Meaning |
|---|---|
| `type_id` | cell type set on matching cells (default 0) |
| `condition` | expression over `expr` (K × N, so `expr[k]`), `N`, `lineage` (cell ids), `parent`, `clone`, `cell_type`, `generation`, `cycling`, `birth_stage` (birth order), `birth_time`, `region`, positions `x`, `y`, `z`, `field_<name>` (each Project field at the cell positions; geometries give 0/1) and `geom_<name>`; absent = all cells |
| `sign`, `base_weight` | sign and weight magnitude; `base_weight` keeps the sign (Dale's principle) |
| `mode`, `shift_v`, `shift_s`, `conn_radius`, `conn_prob`, `burst_period`, `burst_duty`, `poisson_hz`, `refractory`, `role`, `compartment`, `threshold`, `region`  | neuron parameters set on the matching cells |

Every value in an entry (`sign`, `base_weight` and the neuron parameters) may be a `Param`; a `Field` value
is applied per cell. An empty or absent `types` is a no-op. Limits: `type_id` and `condition` are plain values; a
condition must give one value per cell.

**`temporal_competence` (C15).** Progressive, irreversible progenitor competence cascade (McConnell & Kaznowski 1991,
Science; McConnell 1995, Neuron; Isshiki et al. 2001, Cell). Updates competence channels in `Tissue.expression` for
cycling alive cells (`alive & cycling`, plus cells exiting in the current cycle's `cell_cycle_clock`); postmitotic cells
from earlier cycles keep their competence frozen.
| Param | Default | Meaning |
|---|---|---|
| `channels` | none (no-op) | list of cascade specs `{"channel": c, "until": Param}` (starts at `1.0`, switches irreversibly off to `0.0` when the effective driver exceeds `until`) or integer channel indices (advances monotonically via `maximum(expr[c], driver)`) |
| `thresholds` | none | optional list of `until` thresholds paired with integer `channels` |
| `driver` (or `mapping`, `target`) | `Tissue.generation` | intrinsic competence driver (`Const`, `Gene`, `Field`, `Expr` or per-generation table) |
| `environment` (or `field`) | none | optional environmental `Field` / `Param`; effective driver is `max(driver, environment)`, so an older environment advances young cycling progenitors without reversing older ones |

`differentiate` conditions read `expr[c]` (or `generation`), so one rule table assigns birth-order-dependent fates.
Reference neocortical birth-order windows: `examples/profiles/temporal_competence.json`.

## Connectivity (C8–C9, `neurogenesis/stages/connectivity.py`)

**`cluster_boutons` (C19).** Cell-type specific connection multiplicity.
| Param | Default | Meaning |
|---|---|---|
| `contacts` | none | a dict of `(pre_type, post_type)` keys to distributions (fixed int, truncated poisson dict, or prob list) |

**`grow_axons` (C8).** The guidance rules of `neurogenesis.development.rules` as a stage, per projection
(source region → target region). Target point `sigmoid(4·(x_src − 0.5)·Bᵀ + c)` in local [0, 1]³ coordinates, then
`p = p0·exp(−d²/2σ²)` over target cells, one Bernoulli draw per pair.
| Param | Default | Meaning |
|---|---|---|
| `projections` | the `guidance` keys | list of `"src->dst"` strings or pairs; regions are matched by id or through `region_map`; `[]` is the no-op |
| `guidance` | none | per projection (`"src->dst"` keys, or a list of dicts with `src`, `dst`): `B` (identity), `c` (0), `sigma` (0.1), `p0` (0.0), `w` (1.0), `wc`, `inh`, per-projection rule lists, rule genes |
| `rules_shift`, `rules_target`, `rules_probability`, `rules_weight` | [] | rule names applied in order; unknown names raise |
| `conduction_velocity` | 1.0 | space units per tick; delay = round(distance / velocity) clipped to [1, `max_delay`], with a warning when clipped |
| `max_delay` | unlimited (255, the storage bound) | ticks; also a Param of `myelinate` |
| `w_clip`, `inh_weight_factor` | 512, 1.0 | weight clip and inhibitory factor (overridden per projection by `wc`, `inh`) |
| `exact` | unset | unset: dense Ns × Nd when max(Ns, Nd) <= 2048, else sparse guidance (D2, cell list); `True`: always dense, error above 2²⁴ pairs; `False`: sparse when `sigma <= 1` |
| `region_map`, `bounds_min`, `bounds_size`, `identities` | {} | region names → ids; region boxes for local coordinates (default: the bounding box of the region's cells); per-region identities |

Guidance values are resolved at any depth, so a `Gene` may be one entry of `B`. Weights are `w · (1 or −inh) · U(0.9, 1.1)`, rounded and clipped. The stage does not read
`genome["guidance"]` (use `Gene` values inside `guidance`), and raises `ValueError` when neither `projections` nor
`guidance` is given, when a listed projection has no guidance entry, or when a region name is not in `region_map`; a
region without alive cells is a no-op for that projection. Target rules (e.g. `topographic`, `lamina`,
`expression_gradient`, which reads the source cells' named expression columns) run before the dense or sparse path,
so both paths support them. Limits: the dense path uses O(Ns·Nd) memory (only up to 2048 cells per side by default); no probability rule (not even `no_autapse`) applies unless listed; the sparse path supports only the
`identity_expression`, `no_autapse` and `source_sign` probability rules and uses a fixed cutoff of 5σ.

**`place_by_hand` (C9).** Appends cells at explicit `positions` (M, 3), with `region` (0), `cycling` (`False` by
default) and optional `cell_type`, `birth_stage`, `sign`, `mode`, `shift_v`, `shift_s`, `base_weight`, `threshold`,
`directions` (scalars or one value per cell). No positions = no-op.

**`connect_by_hand` (C9).** Appends synapses `pre[i] → post[i]` (current cell indices, not cell ids) with `weight`
(1.0, truncated to an integer) and `delay` (1 tick). Indices outside [0, N) and delays outside [1, 255] raise
`ValueError`. Empty lists = no-op. Two more supervised inputs (run before the index lists):
- `matrix`: a dense N × N weight matrix (row = pre, column = post, 0 = no synapse), allowed up to N = 2048 cells,
  with `delay_matrix` (N × N) or a scalar `delay`.
- `rules`: a list of connection rules, each `{pre, post, prob, weight, delay | velocity, max_distance, sigma, dale,
  allow_autapse}`. `pre` / `post` select living cells by a dict of `region` / `cell_type` values or a boolean
  expression over `cell_type`, `region`, `birth_stage`, `generation`, `sign`, `x`, `y`, `z`. Without `max_distance`
  the number of synapses is drawn from Binomial(N_pre · N_post, prob) and distinct pairs are drawn without building
  an N_pre × N_post array (O(E)); with `max_distance` candidates come from the cell list, each kept with `prob`
  (times exp(−d²/2σ²) with `sigma`). `velocity` sets delay = round(distance / velocity) clipped to [1, 255] with a
  warning; `dale` gives each synapse the presynaptic sign; autapses are dropped unless `allow_autapse`. Values may be
  `Param`s.

## Maturation (C10–C12, `neurogenesis/stages/refinement.py`)

**Plasticity mask (K6).** `tissue.connectivity.plastic` is an optional per-synapse bool array; absent (None, the
default) means every synapse is plastic and the stages below behave exactly as without it. Synapses with
`plastic == False` keep their weight in `refine_by_activity`, `scale` and `neuromodulate` and are never removed by
`prune` (`scale` still counts them in each cell's incoming sum). The mask follows `take` / `concat` / `append`,
`compact`, `subset`, `concatenate`; new synapses are plastic. `to_network` / `from_network` carry it only as the
in-memory attribute `_plastic` of the network (network files do not store it).

**`prune` (C10).** Removes synapses with `|w| < threshold` (default 0, neutral). With `min_coactivity`, it also
removes synapses whose presynaptic spikes, arriving after the synapse delay, were followed by a postsynaptic spike
within `window` ticks (default 5) fewer than `min_coactivity` times ("use it or lose it", Katz & Shatz 1996, Science).
Activity comes from `spikes` (a (T, N) raster) or a `lif_int` simulation of `ticks` (100) with optional
`ext_current`; dead cells are compacted first. Cost O(T · E).

**`scale` (C10).** Multiplies each cell's incoming weights so that their absolute sum equals `target`, then rounds to
integers. Without `target` it is a no-op. `rate` (default 1) moves only that fraction of the way per call
(1 + rate · (factor − 1)), a discrete time constant (Turrigiano et al. 1998, Nature). Limits: small weights can round
to 0.

**`refine_by_activity` (C11).** Simulates the tissue with the JAX `lif_int` kernel for `ticks`, then applies a plasticity
rule of `neurogenesis.spiking.plasticity` once to the weights. Dead cells are compacted first.
| Param | Default | Meaning |
|---|---|---|
| `ticks` | 100 | simulated ticks (ms) |
| `rule` | none (no-op) | `"three_factor"` (`eta` 0.01, `tau_e` 20 ticks; `modulator`: constant, (ticks,) or (ticks, N), or `modulator_cells` whose spike count per tick × `modulator_gain` is the modulator) or `"stdp"` (`A_plus` 1.0, `A_minus` 1.0, `tau_plus` 20, `tau_minus` 20 ticks, `w_min` 0, `w_max` 1000) or `"hebbian"` (`eta` 0.01, `norm_target` 1000, `norm_type` `"l1_subtractive"`) |
| `sources` (or `driver_cells`) | none | cell ids (or indices) made Poisson drivers (`mode = 1`) at `poisson_hz` (1000 Hz); this change stays in the tissue unless `restore_modes` |
| `restore_modes` | False | restore every cell's `mode` and `poisson_hz` after the stage, so drivers act only during it |
| `ext_current` | none | external current per cell (array, or `{cell id: current}`) |
| `spikes` | none | a (ticks, N) spike raster used instead of simulating |
| `waves` | none | spontaneous waves: `sources` (cell ids or points), `speed` (space units per tick), `interval`, `duration` (ticks), `amplitude` (current), `cells` (`{region, cell_type}`: the cells the waves reach; default all) |
| `twitches` | none | motor twitches with sensory feedback: `motor_cells`, `sensory_cells`, `interval`, `duration`, `amplitude`, feedback `delay` and `gain` |
| `record` | false | keep the (ticks, N) spike raster on the tissue (`_activity_spikes`, in memory only) for `competitive_elimination` |

Without `rule` the stage is a no-op . Limits: plasticity acts on magnitudes and keeps synapse signs; weights
are cast to integers. The three-factor eligibility counts arrivals that coincide with a postsynaptic spike in the same tick. **Not implemented:** pruning inside the stage (follow with `prune`), other neuron models.

**`competitive_elimination` (C22, `neurogenesis/stages/competition.py`).** Competitive synapse elimination (Willshaw
1981, Proc R Soc Lond B; Gouzé, Lasry & Changeux 1983, Biol Cybern; Balice-Gordon & Lichtman 1994, Nature). Each
input's score is its coactivity with its target (presynaptic spikes, after the delay, followed by a target spike within
`window` ticks, default 5). On every target that spiked at least `min_target_spikes` times (default 1), inputs scoring
below `fraction` (default 0 = no-op) of the best input onto that target lose `delta` (default 0) of their magnitude
(sign kept, floored at 0) or, with `remove` (default false), are removed. Silent targets change nothing; synchronous
inputs score alike and are all kept; non-plastic synapses (K6) compete but are never changed. Activity: `spikes` (a
(T, N) raster) or the raster recorded by `refine_by_activity` with `record: true`; without either it is a no-op
(`ticks`, default 100, only sizes the cost). Grouping by target: one sort and `np.maximum.reduceat`; cost O(T · E).
Differs from `prune` (absolute weight or coactivity thresholds).

**`partner_select` (C18, `neurogenesis/stages/partner.py`).** Keeps a candidate synapse with probability
`compat[i][j]` (a `Param` matrix, pre channel i × post channel j, clipped to [0, 1]). A cell's channel is its
`cell_type` (default), the argmax of its expression (`channels: "expression"`) or an explicit per-cell list; channels
outside the matrix are kept. Filters synapses from `grow_axons`, `arbor_synapses` or `connect_by_hand`; an identity
matrix reproduces the `identity_expression` rule. Neutral: no `compat` = no-op. Cost O(E). Transmitter–receptor
matching (P2) is not implemented.

**`tissue_expand` (C24, `neurogenesis/stages/expansion.py`).** Dilates the positions of living cells about a centre
(default: their centroid) by `1 + kappa * N_new / N_total` along the chosen `axes`, where `N_new` counts the cells
added since the previous call. Proliferation then pushes existing cells outward, so density stays bounded while the
count grows (in this simulation, with kappa 0.668 and growth x1.5 per cycle: about x5 per tangential axis over 8 cycles).
The first call only records the count (or give `n_prev`); call it once before the first `proliferate`. Synapses keep
their delays unless `recompute_delays` (with `conduction_velocity`, `max_delay`). Neutral `kappa` 0 = no-op. Cost O(N).

**`critical_period_gate` (C23, `neurogenesis/stages/critical_period.py`).** Opens and closes a critical period of
plasticity by setting the K6 `plastic` mask of the gated synapses (those onto `target_type` cells, all by default):
`False` before opening, `True` while open, `False` after closing. Opening when the maturity of inhibition from
`source_type` cells reaches `open_threshold`, closing after `close_after` gate calls or when maturity reaches
`close_threshold`, as maturing parvalbumin-cell inhibition opens and perineuronal nets close the ocular-dominance
critical period (Hensch 2005, Nat Rev Neurosci; Hubel & Wiesel 1970, J Physiol); `reopen` restores plasticity, as
removing the nets with chondroitinase ABC does (Pizzorusso et al. 2002, Science). Call it before each plasticity stage;
its state (phase, gate calls since opening) is kept on the tissue as `_critical_period` (not carried by `subset` /
`concatenate`). Synapses added later are plastic until the next call.
| Param | Default | Meaning |
|---|---|---|
| `source_type` | none | cell type id(s) whose inhibitory (w < 0) synapses measure maturity |
| `target_type` | all cells | cell type id(s) whose incoming synapses are measured and gated |
| `measure` | `"mean"` | `"mean"`: mean \|w\| of those synapses; `"sum"`: mean over target cells of the summed \|w\| |
| `maturity` | none | a maturity value (`Param`: gene, field, `Expr`) used instead of the inhibitory measure |
| `open_threshold` | none | opens when maturity >= this |
| `open` / `close` | false | open / close now (place the entry at the wanted stage index of the schedule) |
| `close_after` | none | closes this many gate calls after opening |
| `close_threshold` | none | closes when maturity >= this (ignored after a reopening) |
| `reopen` | false | reopens: plastic again, `close_after` counts from here |

Neutral: without `open_threshold`, `open`, `close` and `reopen` the stage is a no-op (any of them activates the gate,
so before opening the gated synapses are not plastic). Cost O(N + E). Mouse and cat ages: `examples/profiles/critical_period_gate.json`.

**`myelinate` (C12).** Multiplies delays by `factor` (alias `delay_factor`; absent = no-op; 1.0 is neutral), rounds
and clips to [1, `max_delay`] ticks (default 255) with a warning when clipped. By default every synapse is scaled; given criteria select
synapses passing all of them: `min_delay` (long projections, ticks), `pre_region` / `post_region` (lists of region
ids), `min_rate` (presynaptic rate in Hz, from `spikes` or a simulation of `ticks`; activity-dependent myelination,
Gibson et al. 2014, Science; needs a compacted tissue).

**`freeze` (C13, `neurogenesis/stages/freeze.py`).** Validates the tissue (finite positions, synapse indices in
range, delays in [1, 255], |weight| <= 32767 and, with `dale`, outgoing signs equal to the presynaptic sign) and raises
`FreezeError` listing every problem; the tissue is unchanged. With `path` it writes the compiled network (NGB1 for a
`.ngb` suffix, else JSON). The functions `freeze(tissue)` → `SNNNetwork` and `develop(project, genome, seed)` (run the
schedule, then freeze) do the same from Python.

## Arbors (N1–N3, `neurogenesis/arbors.py`, `neurogenesis/stages/arbors.py`)
`ArborStore` holds the trees of all cells as struct of arrays: `xyz`, `radius`, `parent` (−1 = root, always
`parent[i] < i`), `compartment` (0 undefined, 1 soma, 2 axon, 3 dendrite, 5 neurite, other integers are user labels)
and `cell` (index into the tissue). It lives in `Tissue.morphology` and follows `compact`, `subset` and `concatenate`.
`path_length_to_root`, `depth` (pointer jumping, O(M log depth)), `take` (drop nodes, children re-attached to the nearest
kept ancestor), `downsample(step)` and `to_budget(max_nodes_per_cell)` (keep roots, branch points, terminals and
compartment changes); `read_swc` / `write_swc` for SWC files (`scale` converts units).

**`grow_arbors` (N2).** Grows neurites from each selected cell's soma for `steps` steps (absent or <= 0 = no-op).
| Param | Default | Meaning |
|---|---|---|
| `compartment` | `"dendrite"` | label of the new nodes (`axon`, `dendrite`, `neurite` or an integer) |
| `n_neurites` | 1 | tips started per cell (per cell, read at the soma) |
| `step_length`, `angle_noise` | 1.0, 0.2 | elongation per step (space units); Gaussian turning (radians) |
| `branch_prob`, `branch_angle` | 0.0, 0.5 | branching probability per tip and step; angle of the new branch |
| `stop_prob`, `retraction_prob` | 0.0, 0.0 | stop probability per tip and step; removal probability of each new terminal at the end |
| `direction` | random | initial direction (vector, or per cell) |
| `attractor_field`, `attraction` | none, 0.0 | tips turn up the gradient of this scalar field (negative: down) |
| `stop_field`, `boundary` | none | a step into `stop_field` > 0 or out of the geometry stops the tip |
| `cells`, `soma_radius`, `max_nodes` | all, 0, 10⁶ | `{region, cell_type}` selector; radius of new nodes; bound on new nodes |

**`arbor_synapses` (N3).** Synapses from geometric proximity (Peters' rule): axonal nodes (`pre_compartments`,
default axon and neurite) within `contact_distance` of dendritic nodes (`post_compartments`, default dendrite, neurite,
soma) of another cell, found through the cell list over nodes. Each contact is kept with `p_contact` (1.0), at most
`max_per_pair` (1) per cell pair, closest first. Delay = round(axonal path length / `axon_velocity` (1.0) +
dendritic path length / `dendrite_velocity` (ignored if absent)), clipped to [1, 255] ticks with a counted warning.
Weight `weight` (1) with the presynaptic sign (`dale`, True). Each synapse records `pre_node`, `post_node`,
`path_length` and `dendritic_distance`. No arbors or no `contact_distance` is the no-op. The cost assumes 50 nodes per
cell unless `expected_nodes` is given.

## Pharmacology (P1–P3, `neurogenesis/pharmacology.py`, `neurogenesis/stages/pharmacology.py`)
A **profile** (JSON: `id`, `transmitters` (at most 7, bit k of `Tissue.transmitter`), `receptors`) maps each receptor
class (the value of a synapse's `receptor_class`) to a `transmitter`, a `sign` (+1, −1 or `"pre"`: the weight keeps
its sign), a `gain` (number or `Param`), optional `reversal_mV`, `tau_ms` (recorded for conductance models) and
`contexts` (`{context: {sign, gain}}`, e.g. depolarising GABA-A in immature neurons, Ben-Ari 2002, Nat Rev Neurosci).
`load_profile` takes a dict, a path, or an id searched in `$NEUROGENESIS_PROFILES` and `./profiles/`. The default
profile (one classic receptor, sign `"pre"`) changes no weight, so existing networks keep their fingerprints. An
example profile with cited entries is in `examples/profiles/example_receptors.json`.
- **`set_transmitters`**: `rules` = [{`condition`, `transmitters`: [names], `add`}] set each cell's transmitter bitmask
  (co-transmission: several names; Dale's principle is not enforced).
- **`express_receptors`**: `rules` = [{`condition`, `receptor`, `level` (a `Field` is read per cell)}] set
  `Tissue.receptor_expression` (one column per receptor of the `profile`).
- **`assign_receptors`**: each synapse's receptor class among the receptors whose transmitter the presynaptic cell
  releases, in proportion to their postsynaptic expression (`mode` `"sample"` from the stage stream, or `"max"`);
  synapses without an expressed candidate keep their class. O(E R).
- **`pharmacology`**: compiles weights in a `context`: sign from the receptor, magnitude × gain, and synapses whose
  presynaptic cell lacks the receptor's transmitter set to 0 (`require_transmitter`). Run it in context `"immature"`
  before `refine_by_activity` and `"mature"` after it for a sign switch during development; gains multiply at every
  call, so give gains other than 1 in one compilation only.
- **`transporter_switch`** (C21): per-cell chloride reversal potential from maturation, the NKCC1 → KCC2 switch
  (Rivera et al. 1999, Nature; Ben-Ari 2002, Nat Rev Neurosci). E_Cl = `e_immature` + (`e_mature` − `e_immature`) ·
  sigmoid((age − `midpoint` + `activity_gain` · `activity`) / `width`). Age is `age` (a `Param`) or `now` minus the
  cell's `clock` (`"birth_time"`, default, in the unit of `cell_cycle_clock`'s T_C; `"birth_stage"`, stage index;
  `"generation"`, cycles); `now` defaults to the largest clock value (youngest cell: age 0); `midpoint` (0) and `width`
  (1) are in the age's unit. `activity` (per cell, default 0: `refine_by_activity` does not record it yet) advances the
  switch by `activity_gain` (0 = purely programmed). Synapses whose `receptor_class` is in `receptors` (names in
  `profile`, or indices) get `e_rev` = E_Cl of their postsynaptic cell, used by the conductance models
  (`two_compartment`, `hh`); `lif_int` ignores `e_rev`, so with `v_rest` (mV) their weights also take the sign of
  E_Cl − `v_rest`. Run it after `pharmacology` (which rewrites `e_rev` from the profile). Without `receptors`,
  `e_immature` or `e_mature`: no-op. O(N + E). Rodent defaults (E_Cl −45 → −75 mV, switch P5–P10) with citations:
  `examples/profiles/transporter_switch.json`.
Conditions use the variables of `differentiate` conditions. Each stage without its params (`rules` / `profile`) is a
no-op. Conductance-based synapses (P4) are in the spiking models (`docs/NEURON_MODELS.md`) and neuromodulation (P5) is
the `neuromodulate` stage below. **Not implemented:** the legacy `receptor_sign` rule is not re-expressed as a profile.

## Neuromodulation and dendrites (P5, N5, `neurogenesis/neuromodulation.py`, `neurogenesis/dendritic.py`)

**`neuromodulate` (P5).** Three-factor plasticity (`spiking.plasticity.ThreeFactorRule`) over a recorded spike raster
`spikes` (T × N array, a plain value), gated by a modulator released by `modulator_cells` (volume transmission). The
level at a cell is the sum over modulator cells of their spike trains filtered with `tau_ms`, weighted by
exp(−distance / `space_constant`); dw = `eta` × eligibility × level, the eligibility summing pre-synaptic arrivals
(after the synaptic delay) that coincide with post-synaptic spikes, filtered with `tau_e`. Weights keep their sign and
their magnitude is clipped to [`w_min`, `w_max`]; synapses with `plastic == False` (K6) keep their weight. Every
parameter but `spikes` is a `Param` (a Gene-controlled `eta` is tested); a `Field` resolves to the field object, so use
scalar sources.
| Param | Default | Meaning |
|---|---|---|
| `modulator_cells` | none | cell indices releasing the modulator (none or empty = no-op) |
| `space_constant`, `tau_ms` | 50.0, 50.0 | spatial decay (space units) and time constant (ticks) of the modulator |
| `eta`, `tau_e` | 0.05, 50.0 | learning rate; eligibility time constant (ticks) |
| `tau_plus`, `tau_minus` | 20.0, 20.0 | accepted for a timing-dependent eligibility; the current rule does not use them |
| `w_min`, `w_max` | 0.0, 1000.0 | bounds of the weight magnitude |
| `ticks` | all rows | rows of `spikes` used; the cost assumes 1000 when absent |
No `spikes` or no modulator cells is the no-op. The source × target distance kernel is evaluated only at cells that
receive synapses, in blocks of at most 2²⁰ pairs; memory is O(T N) (the per-cell modulator level) and time
O(T S P + T E) for S modulator cells and P postsynaptic cells. The spike raster must be supplied (the stage does
not simulate).

**`dendritic_attenuate` (N5).** Passive dendritic filtering: each synaptic weight is multiplied by
`exp(−d / length_constant)`, where `d` is the synapse's dendritic distance (computed from `post_node` and the
morphology's path length to the soma when missing); a non-zero weight keeps a magnitude of at least 1. With
`dendrite_velocity`, `round(d / velocity)` ticks are added to the delay; with `distal_compartment_threshold`, the target
cells of synapses at or beyond that distance are marked compartment 1 (distal).
| Param | Default | Meaning |
|---|---|---|
| `length_constant` | 100.0 | dendritic length constant (space units); a `Param` |
| `dendrite_velocity` | none | space units per tick for the added dendritic delay; a `Param` |
| `distal_compartment_threshold` | none | distance (space units) beyond which targets are marked distal; a `Param` |

Empty params = no-op. Limits: synapses without a dendritic distance are left unattenuated; the added delays are still
clipped to `max_delay` (default 255 ticks), with a warning when clipped.

## Geometry (B2, `neurogenesis/geometry/mesh.py`, `voxel.py`)
- **`mesh`** (`MeshGeometry(vertices, faces, resolution=32)`, `from_obj`, `from_stl` for ASCII and binary STL).
  `contains` by ray parity, vectorised over points and faces in blocks of at most 2²⁰ pairs; `sample_points` draws
  uniformly in a `resolution`³ voxel cache (inside and surface voxels) and keeps points that pass the exact test.
  JSON stores vertices, faces and resolution as lists.
- **`voxel_mask`** (`VoxelMaskGeometry(mask, origin, pitch)`): a boolean (X, Y, Z) occupancy array; `contains` by
  lookup, `sample_points` uniform over occupied voxels. `from_npz` / `save_npz` read and write `mask` with an
  axis-aligned 4 × 4 `affine` or `origin` + `voxel_size` (a rotated affine raises); a file-backed mask serialises as
  `{"type": "voxel_mask", "npz": path}`.

## Fields (B3–B5, `neurogenesis/fields/`)
Fields are evaluated with `values(points)` and registered by type name in the Project's `fields`. `run_schedule` binds
each field to the run's genome (`Field.bind`), so `Param` values inside a field are resolved.
- **`GridField(data, origin, spacing, method="nearest")`** (B3): 2D or 3D grids, scalar or with trailing vector
  components; `nearest` or `linear` (`bilinear`, `trilinear`) sampling, clamped at the edges.
- **`AnalyticField(expr)`** (B3): an expression in `x`, `y`, `z`, `exp`, `sin`, `cos`, `pi` and whitelisted NumPy
  functions, evaluated by the restricted evaluator.
- **`VectorField`** (stacked scalar fields) and **`LabelField`** (integer labels on a grid, nearest lookup, a background
  value outside, optional names) (B3).
- **`LayerStackField(base_field, thicknesses, labels=None)`** (B3): the base field is a depth; returns `(label, w)` per
  point, `w` in [0, 1] the relative depth inside the layer. Thicknesses are numbers or `Param`s.
- **Point patterns and maps** (B4, `maps.py`): `regular_points`, `jittered_points`, `poisson_disc_points` (minimum
  distance `radius`) return point arrays; **`PointSetField`** registers a point set as a field (given `points`, or a
  `pattern` with `bounds`, `spacing` / `jitter` / `radius` and its own `seed`, regenerated identically on load); its
  values are the distance to the nearest point (cell list), and `seed_cells` accepts it as `points`.
  **`PinwheelField`** gives an orientation angle in [0, π) from singularities with charges (`pinwheel_map` returns it
  sampled on a grid); `pinwheel_charges` measures the charge around given centres; `find_pinwheels(angles, origin,
  spacing)` locates the pinwheels of any 2D angle grid (winding of 2θ around each grid square, charge ±1/2);
  `bandpass_pinwheels(..., return_pinwheels=True)` also returns the positions and charges of its pinwheels.
- **Operations** (B5, `ops.py`, NumPy only): `Add(a, b)`, `Subtract(a, b)`, `Multiply(a, b)` (fields or constants),
  `Threshold(field, threshold, below, above)`, `GaussianSmooth(grid_field, sigma)`, `DistanceTransform(bounds, spacing,
  target_points)` (distance to a point set on a grid), `Gradient` (of a grid field, or central differences for any
  field), `DistanceToBoundary` (distance to a geometry's or a label region's boundary, optionally signed, grid-based
  with error under one spacing). Composite fields pass `bind(genome)` to their sub-fields, and
  `collect_project_genes` finds `Gene`s inside field definitions. Large operations work in blocks of at most 2²⁰ pairs.

## Sparse guidance (D2, `neurogenesis/development/sparse_guidance.py`)
`sparse_guidance(ctx, plan, rng, c=5.0, exact=False)` returns `(pre, post, p)` for one projection. With `exact=True` it
computes the dense probabilities and draws exactly as the dense code. With `exact=False` it queries target cells within
`c·σ` of each target point through `CellList` (memory O(candidates)) and supports only the `identity_expression`,
`no_autapse` and `source_sign` probability rules (others raise `NotImplementedError`). Limits: the sparse mode draws
different random numbers from the dense mode, so it does not reproduce dense networks for the same seed; the legacy
`grow()` does not use it, and it is not the default for large tissues (`grow_axons` uses it only with `exact=False`).
