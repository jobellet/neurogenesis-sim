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
  integer kernel units. Delays are clipped to the kernel limit of 31 ticks.
- `cost(N, E, params)` returns (bytes, ops); `neurogenesis.stages.base.schedule_cost` sums it over a schedule.
- **Neutral** means the stage leaves the tissue unchanged. Every toolbox stage called with empty params is a
  no-op (tested for every registered stage except `legacy_grow_stage`, which needs its `plan`).

## Population (C1–C3, `neurogenesis/stages/population.py`)

**`seed_cells` (C1).** Adds `N` cells, sampled uniformly in a geometry or placed at one position.
| Param | Default | Meaning |
|---|---|---|
| `N` | 0 | number of cells; `N <= 0` is a no-op |
| `geometry` | none | name of a geometry in the Project (or a `Geometry` object); cells drawn with `sample_points` |
| `position` | none | (3,) position used for all cells when `geometry` is absent |
| `region`, `cell_type` | 0, 0 | integer labels of the new cells |
| `jitter` | 0.0 | standard deviation of a Gaussian offset added to each position (space units) |

Limits: one of `geometry` / `position` is required (`ValueError` otherwise). **Not implemented:** a density `Param` or a
density field, a list of hand positions (use `place_by_hand`), point sets from B4. The cost assumes `N = 100` unless `N`
is a constant.

**`proliferate` (C2).** Each alive cell divides with probability `prob`; the daughter is appended, the mother stays.
| Param | Default | Meaning |
|---|---|---|
| `prob` | 0.0 | division probability per cell and call (per cell); 0 is neutral |
| `jitter` | 0.1 | standard deviation of the daughter's Gaussian displacement from the mother (space units, per cell) |
| `new_type` | none | cell type of the daughters (per cell); if absent daughters copy the mother's type |
| `max_cells` | none | upper bound on alive cells; if divisions would exceed it, a random subset divides so the bound holds exactly |
| `asymmetric_prob` | 0.0 | probability that a division is asymmetric (needs `daughter_type`) |
| `daughter_type` | none | cell type of the new daughter in an asymmetric division; the mother keeps its type (Götz & Huttner 2005, Nat Rev Mol Cell Biol) |
| `expression_noise` | 0.0 | standard deviation of Gaussian noise added to both daughters' expression, clipped at 0 |
| `birth_stage` | none | birth stage given to new daughters; if absent, one more than the latest alive `birth_stage` |

Daughters copy the mother's region, expression, sign and neuron parameters and record `parent_id` and `clone_id`; both
daughters get `generation = mother's + 1` (`Tissue.generation`). Dead cells do not divide.

**`apoptosis` (C3).** Kills cells, then compacts the tissue (connectivity re-indexed).
| Param | Default | Meaning |
|---|---|---|
| `prob` | none | death probability per cell (per cell) |
| `density_radius` | none | radius (space units, per cell) for counting neighbours |
| `max_density` | 10 | cells with more than this many neighbours within `density_radius` die |
| `min_inputs`, `min_outputs` | none | neurotrophic death: cells with fewer incoming / outgoing synapses die |

All criteria are off when absent. Neighbour counts use a dense N × N distance matrix for `N <= 2048` and the cell list
(`CellList`, D1) above. Limits: synapse counts ignore weights and activity.

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

Limits: deterministic (no random motion). **Not implemented:** tangential migration, the inside-out layering test
case as a test of `migrate` alone.

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
**Not implemented:** the `mosaic` stage (the legacy `mosaic` placement rule of `neurogenesis.development.rules` exists).

## Expression and differentiation (C6–C7, `neurogenesis/stages/differentiation.py`)

**`express` (C6).** One gene-regulatory step on the expression matrix (N, K):
`E ← E·(1 − decay·dt) + sigmoid(W·E + Σ_m f_m·w_m + W_n·Σ_neighbours E)·dt`.
| Param | Default | Meaning |
|---|---|---|
| `K` | 0 | number of genes; `K <= 0` (or no params) is a no-op; expression is padded or cut to K columns |
| `weights` | zeros | K × K regulatory weights `W` (or K² values) |
| `morphogens` | [] | list of `{"field": Param, "weights": [K]}`; the field is evaluated at the cell positions |
| `radius` | 0.0 | contact radius (space units) for neighbour input through the cell list; 0 disables it |
| `neighbor_weights` | zeros | K × K weights `W_n` applied to the **sum** of neighbours' expression |
| `dt`, `decay` | 1.0, 0.0 | step size and linear decay rate |

Dead cells are kept (only the runner compacts). Limits: with `K > 0` the step is not a no-op even with zero weights (sigmoid(0) = 0.5 is
added); weight matrices of the wrong shape are silently replaced by zeros; the sigmoid has no Hill coefficient. The
cost is O(N K²) (plus the cell-list query when `radius > 0`) and uses a `Gene`'s upper bound for `K`.

**`differentiate` (C7).** Applies a rule table `types`: for each entry, in order, cells matching `condition` get the
listed properties (later entries override earlier ones).
| Entry key | Meaning |
|---|---|
| `type_id` | cell type set on matching cells (default 0) |
| `condition` | expression over `expr` (K × N, so `expr[k]`), `N`, `lineage` (cell ids), `parent`, `clone`, `field_<name>` (each Project field at the cell positions; geometries give 0/1) and `geom_<name>`; absent = all cells |
| `sign`, `base_weight` | sign and weight magnitude; `base_weight` keeps the sign (Dale's principle) |
| `mode`, `shift_v`, `shift_s`, `conn_radius`, `conn_prob`, `burst_period`, `burst_duty`, `poisson_hz`, `refractory`, `role`, `compartment`, `threshold`, `region`  | neuron parameters set on the matching cells |

Every value in an entry (`sign`, `base_weight` and the neuron parameters) may be a `Param`; a `Field` value
is applied per cell. An empty or absent `types` is a no-op. Limits: `type_id` and `condition` are plain values;
`birth_stage` and positions are not available in conditions (use a field); a condition must give one value per cell;
`collect_genes` does not find `Gene`s nested inside `types`.

## Connectivity (C8–C9, `neurogenesis/stages/connectivity.py`)

**`grow_axons` (C8).** The guidance rules of `neurogenesis.development.rules` as a stage, per projection
(source region → target region). Target point `sigmoid(4·(x_src − 0.5)·Bᵀ + c)` in local [0, 1]³ coordinates, then
`p = p0·exp(−d²/2σ²)` over target cells, one Bernoulli draw per pair.
| Param | Default | Meaning |
|---|---|---|
| `projections` | the `guidance` keys | list of `"src->dst"` strings or pairs; regions are matched by id or through `region_map`; `[]` is the no-op |
| `guidance` | none | per projection (`"src->dst"` keys, or a list of dicts with `src`, `dst`): `B` (identity), `c` (0), `sigma` (0.1), `p0` (0.0), `w` (1.0), `wc`, `inh`, per-projection rule lists, rule genes |
| `rules_shift`, `rules_target`, `rules_probability`, `rules_weight` | [] | rule names applied in order; unknown names raise |
| `conduction_velocity` | 1.0 | space units per tick; delay = round(distance / velocity) clipped to [1, min(`max_delay`, 31)], with a warning when clipped |
| `max_delay` | 31 | ticks |
| `w_clip`, `inh_weight_factor` | 512, 1.0 | weight clip and inhibitory factor (overridden per projection by `wc`, `inh`) |
| `exact` | unset | unset: dense Ns × Nd when max(Ns, Nd) <= 2048, else sparse guidance (D2, cell list); `True`: always dense, error above 2²⁴ pairs; `False`: sparse when `sigma <= 1` |
| `region_map`, `bounds_min`, `bounds_size`, `identities` | {} | region names → ids; region boxes for local coordinates (default: the bounding box of the region's cells); per-region identities |

Weights are `w · (1 or −inh) · U(0.9, 1.1)`, rounded and clipped. The stage does not read
`genome["guidance"]` (use `Gene` values inside `guidance`), and raises `ValueError` when neither `projections` nor
`guidance` is given, when a listed projection has no guidance entry, or when a region name is not in `region_map`; a
region without alive cells is a no-op for that projection. Limits: the dense path uses O(Ns·Nd) memory (only up to 2048 cells per side by default); no probability rule (not even `no_autapse`) applies unless listed; the sparse path supports only the
`identity_expression`, `no_autapse` and `source_sign` probability rules and uses a fixed cutoff of 5σ.

**`place_by_hand` (C9).** Appends cells at explicit `positions` (M, 3), with `region` (0) and optional `cell_type`,
`birth_stage`, `sign`, `mode`, `shift_v`, `shift_s`, `base_weight`, `threshold`, `directions` (scalars or one value per
cell). No positions = no-op.

**`connect_by_hand` (C9).** Appends synapses `pre[i] → post[i]` (current cell indices, not cell ids) with `weight`
(1.0, truncated to an integer) and `delay` (1 tick). Indices outside [0, N) and delays outside [1, 31] raise
`ValueError`. Empty lists = no-op. **Not implemented:** connection matrices and connection rules from the GUI.

## Maturation (C10–C12, `neurogenesis/stages/refinement.py`)

**`prune` (C10).** Removes synapses with `|w| < threshold` (default 0, neutral). **Not implemented:** the activity
criterion.

**`scale` (C10).** Multiplies each cell's incoming weights so that their absolute sum equals `target`, then rounds to
integers. Without `target` it is a no-op. Limits: small weights can round to 0; all inputs are scaled, without a time
constant.

**`refine_by_activity` (C11).** Simulates the tissue with the JAX `lif_int` kernel for `ticks`, then applies a plasticity
rule of `neurogenesis.spiking.plasticity` once to the weights. Dead cells are compacted first.
| Param | Default | Meaning |
|---|---|---|
| `ticks` | 100 | simulated ticks (ms) |
| `rule` | none (no-op) | `"stdp"` (`A_plus` 1.0, `A_minus` 1.0, `tau_plus` 20, `tau_minus` 20 ticks, `w_min` 0, `w_max` 1000) or `"hebbian"` (`eta` 0.01, `norm_target` 1000, `norm_type` `"l1_subtractive"`) |
| `sources` (or `driver_cells`) | none | cell ids (or indices) made Poisson drivers (`mode = 1`) at `poisson_hz` (1000 Hz); this change stays in the tissue |
| `ext_current` | none | external current per cell (array, or `{cell id: current}`) |
| `spikes` | none | a (ticks, N) spike raster used instead of simulating |

Without `rule` the stage is a no-op . Limits: plasticity acts on magnitudes and keeps synapse signs; weights
are cast to integers. **Not implemented:** spontaneous waves (sources and speed), motor twitches with sensory
feedback, the three-factor rule, pruning inside the stage (follow with `prune`), other neuron models.

**`myelinate` (C12).** Multiplies every delay by `factor` (alias `delay_factor`; absent = no-op; 1.0 is neutral), rounds and clips to [1, 31] ticks with a warning when clipped. **Not implemented:** selecting active or long
projections (all synapses are scaled).

**`freeze` (C13).** **Not implemented** as a stage; `Tissue.to_network()` compiles a tissue to an `SNNNetwork`.

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
  distance `radius`) return point arrays; **`PinwheelField`** gives an orientation angle in [0, π) from singularities
  with charges (`pinwheel_map` returns it sampled on a grid); `pinwheel_charges` measures the charge around given
  centres; `bandpass_pinwheels` returns an angle grid from band-pass filtered noise. **Not implemented:** registered
  field types for point sets, and locating the pinwheels of a band-pass map.
- **Operations** (B5, `ops.py`, NumPy only): `Add(a, b)` (fields or constants), `Threshold(field, threshold, below,
  above)`, `GaussianSmooth(grid_field, sigma)`, `DistanceTransform(bounds, spacing, target_points)` (distance to a
  point set on a grid), `Gradient` (of a grid field, or central differences for any field), `DistanceToBoundary`
  (distance to a geometry's or a label region's boundary, optionally signed, grid-based with error under one spacing).
  Large operations work in blocks of at most 2²⁰ pairs. **Not implemented:** subtraction and multiplication fields;
  `Add` and `Threshold` do not pass `bind` on to their children; `collect_genes` does not find `Gene`s inside fields.

## Sparse guidance (D2, `neurogenesis/development/sparse_guidance.py`)
`sparse_guidance(ctx, plan, rng, c=5.0, exact=False)` returns `(pre, post, p)` for one projection. With `exact=True` it
computes the dense probabilities and draws exactly as the dense code. With `exact=False` it queries target cells within
`c·σ` of each target point through `CellList` (memory O(candidates)) and supports only the `identity_expression`,
`no_autapse` and `source_sign` probability rules (others raise `NotImplementedError`). Limits: the sparse mode draws
different random numbers from the dense mode, so it does not reproduce dense networks for the same seed; the legacy
`grow()` does not use it, and it is not the default for large tissues (`grow_axons` uses it only with `exact=False`).
