# Jules Swarm Prompts: Parallel Implementation of neurogenesis-sim Roadmap

This document contains isolated, copy-paste prompts for autonomous Jules agents to implement tasks from `docs/ROADMAP.md` in parallel without git merge collisions.

### Key Strategy to Prevent Merge Conflicts
1. **Strict File Isolation**: Each agent only creates or modifies files within its dedicated domain.
2. **No Shared Index/Doc Edits**: Agents do **not** modify shared entry points (`neurogenesis/__init__.py`, `README.md`, `docs/ROADMAP.md`). These are updated in a single clean pass after PR merges.
3. **Execution Waves**: Wave 1 tasks have zero inter-dependencies and can be run simultaneously right now. Wave 2 tasks can run in parallel once Wave 1 is merged.

---

# Wave 1: Immediate Parallel Execution (Independent Foundations)

---

## Agent 1: Task A1 — Project Schema & I/O
**Branch:** `task/A1-project-schema`

```text
You are working on task A1 (Project schema and I/O) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/A1-project-schema`.

### Strict File Isolation (To Prevent PR Collisions)
- ONLY create/modify:
  - `neurogenesis/project/__init__.py`
  - `neurogenesis/project/schema.py`
  - `neurogenesis/project/io.py`
  - `docs/PROJECT_FORMAT.md`
  - `tests/test_project_schema.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, `docs/ROADMAP.md`, or any existing test files.

### Deliverables & Requirements
1. Implement `SCHEMA_VERSION = "1.0.0"` and validation logic in `neurogenesis/project/schema.py` (pure Python + NumPy, no new external dependencies) validating a Project dictionary containing:
   - `version` (str)
   - `geometry` (dict)
   - `fields` (dict)
   - `schedule` (list of stage config dicts)
   - `genome` (nested dict compatible with `neurogenesis.genome`)
   - `plan` (optional legacy BodyPlan dict)
   - `plugins` (list of module strings)
   - `neuron_model` (str, default `"lif_int"`)
   - `metadata` (dict)
2. Implement `Project` dataclass in `neurogenesis/project/io.py` with `Project.save(path)` and `Project.load(path)`:
   - Saves JSON to `<path>` and any large NumPy arrays (`ndarray`) to a sidecar `<stem>.npz` file referenced by key in the JSON.
   - Implement `migrate(data, from_version, to_version)` in `schema.py` with a registry of version migration functions (include a `"0.1.0" -> "1.0.0"` migration wrapping legacy dicts).
3. Document the format in `docs/PROJECT_FORMAT.md`.
4. In `tests/test_project_schema.py`, test:
   - JSON + `.npz` round-trip equality (including float32/int32 arrays);
   - Schema rejection of malformed files with clear `ValueError` messages;
   - Version migration from `"0.1.0"` to `"1.0.0"`.
5. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 2: Task A2 — Tissue State Struct-of-Arrays
**Branch:** `task/A2-tissue-state`

```text
You are working on task A2 (Tissue state) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/spiking/network.py` first. Work on branch `task/A2-tissue-state`.

### Strict File Isolation (To Prevent PR Collisions)
- ONLY create/modify:
  - `neurogenesis/tissue.py`
  - `tests/test_tissue.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, `docs/ROADMAP.md`, or any existing files.

### Deliverables & Requirements
1. Implement `Tissue` and `SparseConnectivity` as struct-of-arrays containers in `neurogenesis/tissue.py`:
   - Per-cell arrays (length `N`):
     - `positions`: `(N, 3)` `float32`
     - `directions`: `(N, 3)` `float32` (default `(0, 1, 0)`)
     - `lineage_id`: `(N,)` `int32` (unique cell id) and `parent_id`: `(N,)` `int32` (`-1` for founders)
     - `birth_stage`: `(N,)` `int32`
     - `cell_type`: `(N,)` `int32`
     - `region`: `(N,)` `int32`
     - `expression`: `(N, K)` `float32`
     - `sign`: `(N,)` `int8` (`+1` excitatory, `-1` inhibitory)
     - `alive`: `(N,)` `bool`
     - Neuron parameter arrays matching `NeuronData` in `neurogenesis/spiking/network.py`: `mode`, `shift_v`, `shift_s`, `base_weight`, `conn_radius`, `conn_prob`, `burst_period`, `burst_duty`, `poisson_hz`, `refractory`, `role`, `compartment`, `threshold`.
   - `connectivity`: `SparseConnectivity` holding 1D arrays `pre` (`int32`), `post` (`int32`), `weight` (`int32`), `delay` (`int32`).
2. Implement O(N) / O(E) vectorised operations on `Tissue` (no Python loops over cells/synapses in array operations):
   - `add_cells(...)`: append new cells and assign unique `lineage_id`s;
   - `kill(mask)` and `compact()`: remove dead cells (`alive == False`), remap `connectivity.pre` and `connectivity.post` indices to the compacted indices (dropping synapses attached to dead cells), while preserving `lineage_id` and `parent_id` history;
   - `subset(indices)` and `Tissue.concatenate(tissues)`;
   - `to_network() -> SNNNetwork` and `Tissue.from_network(net: SNNNetwork) -> Tissue`;
   - `memory_bytes() -> int` documenting and computing exact array bytes per cell and synapse.
3. In `tests/test_tissue.py`, test:
   - Adding cells, killing a subset, and verifying `compact()` keeps lineage IDs intact and accurately remaps/prunes synapses;
   - `to_network()` and `from_network()` round-trip preservation;
   - Determinism and `memory_bytes()` accuracy.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 3: Task B1 — Geometry Primitives
**Branch:** `task/B1-geometry-primitives`

```text
You are working on task B1 (Geometry primitives) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/B1-geometry-primitives`.

### Strict File Isolation (To Prevent PR Collisions)
- ONLY create/modify:
  - `neurogenesis/geometry/__init__.py`
  - `neurogenesis/geometry/primitives.py`
  - `tests/test_geometry_primitives.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, `docs/ROADMAP.md`, or any existing files.

### Deliverables & Requirements
1. Implement 2D/3D geometry primitives in `neurogenesis/geometry/primitives.py`:
   - Shapes: `Box`, `Sphere`, `Ellipsoid`, `Cylinder`, `Sheet2D`, `CurvedSheet` (parametric surface with thickness `w`), and CSG boolean combinators `Union` and `Difference`.
   - Every geometry class must implement:
     - `contains(points: np.ndarray) -> np.ndarray` (bool mask for `(N, 3)` float32 points, fully vectorised);
     - `sample(n: int, rng: np.random.Generator) -> np.ndarray` (`(n, 3)` float32 uniform in volume or surface area, strictly using the passed `rng`);
     - `bounding_box() -> tuple[np.ndarray, np.ndarray]` (`(min_xyz, max_xyz)` in `float32`);
     - `local_coordinates(points: np.ndarray) -> np.ndarray` mapping global `(x, y, z)` to local `(u, v, w) in [0, 1]^3` (e.g. tangential `(u, v)` along a sheet and normalized depth `w` across it);
     - `to_dict()` and `geometry_from_dict(d)` for JSON serialization.
2. In `tests/test_geometry_primitives.py`, test:
   - Every sampled point from `sample(n, rng)` satisfies `contains(pts).all()`;
   - Statistical uniformity of `sample(n, rng)` (e.g. octant/quadrant chi-square test with fixed seed);
   - Determinism with same `rng` seed;
   - `to_dict` / `geometry_from_dict` JSON round-trip for all primitives and CSG trees.
3. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 4: Task D1 — Spatial Hash & Cell Lists
**Branch:** `task/D1-spatial-cell-list`

```text
You are working on task D1 (Cell lists / spatial hash) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/D1-spatial-cell-list`.

### Strict File Isolation (To Prevent PR Collisions)
- ONLY create/modify:
  - `neurogenesis/spatial.py`
  - `tests/test_spatial.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, `docs/ROADMAP.md`, or any existing files.

### Deliverables & Requirements
1. Implement `CellList` in `neurogenesis/spatial.py` for fast O(N) 3D neighbour queries in `float32` using CSR-style cell-list binning (sort by 3D voxel hash / Morton or linear grid index + `np.searchsorted` / `bincount`, no `scipy` dependency):
   - `CellList(positions: np.ndarray, cutoff: float, box: tuple | None = None)`
   - `query_radius(query_points: np.ndarray, radius: float, return_distances: bool = False)` returning flat CSR arrays `(row_ptr, col_idx[, distances])` or pairs `(src_idx, dst_idx[, distances])` sorted deterministically by `(src_idx, dst_idx)`.
   - `query_knn(query_points: np.ndarray, k: int)` returning `(indices, distances)` of shape `(M, k)`.
   - `declared_cost(n_points: int, n_queries: int, mean_neighbours: float) -> tuple[int, int]` returning `(bytes, ops)`.
2. Never build a dense `N x N` distance matrix.
3. In `tests/test_spatial.py`, test:
   - Exact agreement with brute-force pairwise distances on `N = 300` random 3D points for both self-queries and cross-queries (`query_radius` and `query_knn`);
   - Linear O(N) scaling check up to `N = 50_000` points;
   - Cost declaration within a factor of 3 of measured memory bytes.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 5: Task E1 — Synaptic Plasticity Component
**Branch:** `task/E1-plasticity`

```text
You are working on task E1 (Plasticity component) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `docs/NEURON_MODELS.md` first. Work on branch `task/E1-plasticity`.

### Strict File Isolation (To Prevent PR Collisions)
- ONLY create/modify:
  - `neurogenesis/spiking/plasticity.py`
  - `tests/test_plasticity.py`
- DO NOT modify `neurogenesis/spiking/reference.py`, `neurogenesis/spiking/jax_backend.py`, `viz/src/sim/kernel.ts`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement reusable, deterministic, O(E) synaptic plasticity rules in `neurogenesis/spiking/plasticity.py` that operate on CSR or COO synapse arrays and spike histories without altering the core `lif_int` kernel:
   - **Pair-based STDP (`STDPRule`):** pre- and post-synaptic exponential traces (both float32 and bit-shift integer-friendly trace variants for `lif_int`), configurable `A_plus`, `A_minus`, `tau_plus`, `tau_minus`, hard/soft weight bounds `[w_min, w_max]`, and Dale's law sign preservation (excitatory weights stay `>= 0`, inhibitory stay `<= 0`).
   - **Hebbian with normalisation (`HebbianRule`):** correlation-based update with multiplicative or subtractive synaptic scaling (Oja / L1/L2 postsynaptic weight normalisation).
   - **Three-factor learning (`ThreeFactorRule`):** eligibility trace `e_ij(t)` updated by pre/post activity and gated by a scalar or per-region neuromodulator signal `M(t)`.
   - Include `declared_cost(num_neurons, num_synapses, ticks) -> tuple[int, int]` (`bytes, ops`).
2. In `tests/test_plasticity.py`, test:
   - Classic asymmetric STDP Δw vs. Δt curve (`t_post - t_pre` from `-50 ms` to `+50 ms`);
   - Weight bounds and Dale's law sign preservation;
   - Three-factor zero-change when modulator `M(t) == 0` and sign inversion when `M(t) < 0`;
   - Bit-for-bit determinism and neutral parameters (`A_plus = A_minus = 0`) producing a strict no-op.
3. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 6: Task F6 — Viewer Population Raster & Region Colouring
**Branch:** `task/F6-viewer-populations`

```text
You are working on task F6 (Network view enhancements) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and inspect `viz/src/` first. Work on branch `task/F6-viewer-populations`.

### Strict File Isolation (To Prevent PR Collisions)
- ONLY create/modify:
  - `viz/src/ui/PopulationFilter.ts`
  - `viz/src/ui/RasterCanvas.ts`
  - `viz/src/render/SceneManager.ts`
- DO NOT touch `viz/src/sim/kernel.ts` (browser kernel equivalence), Python files, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Add colour-mode switching in `viz/src/render/SceneManager.ts` and `viz/src/ui/PopulationFilter.ts`:
   - Allow colouring neurons by `role`/`sign` (default), `compartment` (region), or `mode` / cell-type metadata if present in the loaded network JSON.
2. Enhance `viz/src/ui/RasterCanvas.ts` and `PopulationFilter.ts` so the user can filter the spike raster and 3D highlight by selected compartments/regions or cell types, and display synapse counts per projection/compartment pair.
3. Keep all state driven by the imported network JSON (no hidden state).
4. Verify with `cd viz && npm run build && cd .. && JAX_PLATFORMS=cpu pytest -q`.
```

---

# Wave 2: Subsequent Parallel Execution (Stages, Fields, Guidance)

*Prerequisite: Merge Wave 1 tasks, then add `neurogenesis/params.py` (A3) and `neurogenesis/stages/base.py` (A4).*

---

## Agent 7: Task B2 — Meshes & Voxel Masks
**Branch:** `task/B2-meshes-voxels`

```text
You are working on task B2 (Meshes and voxel masks) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/B2-meshes-voxels`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/geometry/mesh.py`
  - `neurogenesis/geometry/voxel.py`
  - `tests/test_geometry_mesh.py`
- DO NOT modify `primitives.py`, `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement `MeshGeometry` in `neurogenesis/geometry/mesh.py`:
   - Parse OBJ / STL ASCII files (vertices, triangle faces) using pure NumPy/Python.
   - Point-in-mesh containment test using ray-casting parity intersection.
   - Bounding box calculation and voxel caching of occupancy for fast query lookups.
   - Uniform point sampling within closed triangular meshes.
2. Implement `VoxelMaskGeometry` in `neurogenesis/geometry/voxel.py`:
   - Binary 3D boolean occupancy array with voxel pitch `(dx, dy, dz)` and origin.
   - Vectorized `contains(points)` via trilinear/nearest grid index lookup.
   - Rejection-sampled or stratified `sample(n, rng)`.
3. In `tests/test_geometry_mesh.py`, test:
   - Containment tests for standard closed shapes (cube, sphere);
   - Point sampling within 2% volume accuracy compared to analytical volumes.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 8: Task B3 — Scalar, Vector, & Label Fields
**Branch:** `task/B3-fields-core`

```text
You are working on task B3 (Scalar, vector and label fields) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/B3-fields-core`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/fields/__init__.py`
  - `neurogenesis/fields/core.py`
  - `tests/test_fields_core.py`
- DO NOT modify `geometry/`, `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement field representations in `neurogenesis/fields/core.py`:
   - `GridField`: 2D / 3D regular grids for scalar, vector, or integer label data with trilinear/nearest-neighbour sampling at arbitrary `(N, 3)` coordinates.
   - `AnalyticField`: Parametric scalar/vector functions (linear gradients, radial Gaussians, exponential decays).
   - `LayerStackField`: Cortical-style layering assigning discrete integer labels and continuous laminar depths based on boundary thresholds along a geometric coordinate axis or depth coordinate.
2. Provide `sample(points: np.ndarray) -> np.ndarray` across all field types.
3. In `tests/test_fields_core.py`, test:
   - Sampling accuracy against analytical expressions;
   - Correct layer label assignment matching defined thickness boundaries.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 9: Task B4 — Point Patterns & Pinwheel Maps
**Branch:** `task/B4-point-patterns-maps`

```text
You are working on task B4 (Point patterns and maps) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/B4-point-patterns-maps`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/fields/maps.py`
  - `tests/test_fields_maps.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement point pattern generation and 2D cortical map models in `neurogenesis/fields/maps.py`:
   - Point pattern generators: regular lattice, jittered grid, and Poisson-disc sampling (Bridson's algorithm) enforcing minimum separation distance.
   - Orientation preference maps: pinwheel maps constructed from placed topological singularities with half-integer charges ($q = \pm 1/2$), and bandpass-filtered noise methods producing realistic pinwheel densities.
2. In `tests/test_fields_maps.py`, test:
   - Poisson-disc samples strictly respect minimum distance parameter;
   - Topological charge contour integral around placed pinwheels recovers $\pm 1/2$;
   - Determinism given fixed seed.
3. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 10: Task D2 — Sparse Axon Guidance
**Branch:** `task/D2-sparse-guidance`

```text
You are working on task D2 (Sparse guidance) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/D2-sparse-guidance`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/development/sparse_guidance.py`
  - `tests/test_sparse_guidance.py`
- DO NOT modify `neurogenesis/development/grow.py`, `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement sparse axon guidance in `neurogenesis/development/sparse_guidance.py` using `CellList` from `neurogenesis.spatial`:
   - Replace dense `N_src x N_dst` connection probability matrices with candidate queries restricted to radius $c \cdot \sigma$ around the target point.
   - Support `exact=True` mode which reproduces the dense connection probability matrix exactly when the cutoff radius encloses all candidate cells.
   - Support systems-matching / dynamic capacity scaling: allow target capacity constraints or terminal density penalties (Gierer/Prestige-Willshaw type dynamic occupancy) so projections scale smoothly across tissue size disparities without hardcoded rigid coordinates.
   - Support cell-type-specific bouton multiplicity & arbor distribution:
     - Allow configurable bouton count distributions per projection pair (e.g. sparse 1–2 contacts for pyramidal–pyramidal, clustered 10–30 contacts for basket cell somatic inhibition, dense multi-active-zone cartridges for chandelier cells).
     - Support two-stage synaptogenesis: Peters' rule proximity filtering via `CellList` followed by molecular matching criteria (subcellular compartment targeting e.g. soma vs. axon initial segment vs. dendrites).
   - Support multi-step guidance trajectories / waypoints: allow paths to specify intermediate choice points or guidepost regions before final terminal arborization (e.g. midline crossing, turning onto tract).
   - Support dynamic rule / sensitivity resets: allow projection rules to invert or switch attractant/repellent weights upon crossing an intermediate geometric boundary or landmark plane.
   - Support memory-bounded sparse generation achieving $O(E)$ memory scaling for $10^5$ cells.
2. In `tests/test_sparse_guidance.py`, test:
   - Bit-for-bit or numerical equivalence to dense guidance when `exact=True`;
   - Memory and runtime scaling on large synthetic tissues ($10^5$ cells).
3. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 11: Tasks C1–C3 — Progenitor Seeding, Proliferation, Apoptosis
**Branch:** `task/C1-C3-population-stages`

```text
You are working on tasks C1, C2, and C3 (seed_cells, proliferate, apoptosis stages) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/tissue.py` first. Work on branch `task/C1-C3-population-stages`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/population.py`
  - `tests/test_stages_population.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/population.py`:
   - `@register_stage("seed_cells")`: initializes tissue progenitors from explicit positions or geometry sampling.
   - `@register_stage("proliferate")`:
     - Models symmetric vs. asymmetric cell division modes.
     - Mode choice controlled via `division_mode` Param (can be constant, read from an extrinsic mitogen field like FGF/EGF concentration, or read from intrinsic cell cycle / expression state).
     - **Symmetric proliferative mode:** cleavage plane vertical, dividing parent equally; both daughters remain adjacent at the apical boundary in progenitor state.
     - **Asymmetric neurogenic mode:** cleavage plane horizontal/oblique; cytokinesis places sibling cells immediately adjacent at the apical margin, after which the apical daughter retains apical attachment/progenitor status, and the basal daughter detaches, inherits asymmetrical Notch/Numb factor levels, and is flagged for cell-cycle exit and outward migration.
     - Daughter cell displacement: minimal steric offset immediately post-mitosis (adjacent cell radius), with outward trajectory determined by subsequent migration stage or interkinetic movement.
     - Division probability parameter, expression inheritance with mutation/noise, lineage tracking, and max-cell safety bounds.
   - `@register_stage("apoptosis")`:
     - Cell culling via probability parameter, neurotrophic connectivity deficit, or local crowding density (modeling selective apoptosis of crowded homotypic neighbours to elevate mosaic regularity).
2. Each stage must declare its cost function `cost(N, E, params) -> (bytes, ops)` and accept an isolated `rng`.
3. In `tests/test_stages_population.py`, test:
   - Determinism per seed and stage salt;
   - Neutral parameters act as strict no-ops;
   - Correct lineage tree and parent-child tracking;
   - Declared cost matches measured cost within a factor of 3.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 12: Tasks C4–C5 — Migration & Cell Sorting
**Branch:** `task/C4-C5-migration-sorting`

```text
You are working on tasks C4 and C5 (migrate, sort/mosaic stages) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/tissue.py` first. Work on branch `task/C4-C5-migration-sorting`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/migration.py`
  - `tests/test_stages_migration.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/migration.py`:
   - `@register_stage("migrate")`:
     - Moves cell positions along vector fields (e.g. radial glia fibers), up/down scalar gradients (chemotaxis/trophic fields), or toward designated target laminar depths.
     - **Radial glial scaffold & inside-out layering model**:
       - Cells migrate along radial direction vectors.
       - Support a superficial detachment/stop signal (e.g. marginal zone **Reelin** signal field). When active cells enter the stop zone (or surpass settled deep-layer cells), they detach from the radial guide and arrest forward motion.
       - Collision / crowding handling using `CellList`: migrating cells can bypass settled cells unless un-detached cells produce a physical blockade (the biological "log-jam" / *reeler* failure mode).
     - **Tangential-to-radial stream switching (interneuron migration)**:
       - Support tangential vector fields (e.g. orthogonal to cortical depth $w$, deep in VZ/IZ or superficial in MZ).
       - Allow switching to radial vectors upon entering target coordinate intervals (modeling turning onto corticofugal axonal tracks).
       - Optional paracrine deceleration brake: local cell density or ambient paracrine field (e.g. GABA accumulation) slowing step velocity.
   - `@register_stage("sort")` / `@register_stage("mosaic")`:
     - Homotypic repulsion and differential cell adhesion dynamics using `CellList`.
     - Models minimal exclusion zone dynamics: applies repulsive displacement vectors to homotypic pairs closer than exclusion distance $d_{\text{min}}$ (drawn from a configurable Gaussian distribution).
     - Allows cell-type specific rules: forward-pathway sensory neurons (e.g. RGCs, bipolars) enforce exclusion/tiling, whereas lateral interneuron types allow overlap.
2. Each stage must declare its cost function `cost(N, E, params) -> (bytes, ops)`.
3. In `tests/test_stages_migration.py`, test:
   - Inside-out cortical layering verification: successive cohorts (e.g. Layer VI then Layer II/III) crawl past predecessors and arrest beneath the marginal stop zone;
   - Stop-signal knockout test (*reeler* analogue): in the absence of the superficial stop signal, cells fail to detach, producing a pile-up / inverted layering;
   - Verification that postmitotic neurons maintain their committed laminar subtype identity regardless of migration position or time;
   - Mosaic spatial regularity improvement (Voronoi / regularity index increases after mosaic stage);
   - Determinism and neutral parameter no-op.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 13: Tasks C6–C7 — Gene Expression & Differentiation
**Branch:** `task/C6-C7-expression-diff`

```text
You are working on tasks C6 and C7 (express, differentiate stages) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/tissue.py` first. Work on branch `task/C6-C7-expression-diff`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/expression.py`
  - `tests/test_stages_expression.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/expression.py`:
   - `@register_stage("express")`:
     - Updates continuous regulatory state `tissue.expression (N, K)` via coupled dynamical ODE/difference updates:
       - **Juxtacrine Notch–Delta dynamics**: for contact neighbors identified via `CellList` (contact radius or Voronoi adjacency), compute average neighbor Delta $\bar{D}_i = \frac{1}{|K_i|} \sum_{j \in K_i} D_j$, activating Notch via saturating Hill kinetics $f(\bar{D}_i) = \frac{\bar{D}_i^k}{A + \bar{D}_i^k}$, which represses Delta synthesis via $g(\bar{N}_i) = \frac{1}{1 + B \bar{N}_i^k}$.
       - **Morphogen gradient coupling**: read continuous concentration inputs from scalar fields (e.g. SHH, BMP, Wnt) to define competence domains and modulate basal proneural / Notch expression.
       - **Autonomous temporal cascade**: unidirectional activation of successive transcription factor states (downstream factors repressing upstream factors).
       - **Extrinsic/kinetic modulation**: rate modulation by cell cycle kinetics ($T_{G1}$ lengthening) and paracrine feedback fields.
   - `@register_stage("differentiate")`:
     - Maps continuous expression profiles, lineage, or spatial coordinates into discrete cell types, assigning excitatory/inhibitory sign and biophysical neuron parameters.
     - Postmitotic neurons lock in their temporal subtype and laminar fate permanently upon cell-cycle exit.
     - Support postsynaptic polarity rules and developmental transporter switches:
       - Presynaptic Dale's law sign (`+1` exc, `-1` inh) as default base sign.
       - Support projection-specific receptor inversion (e.g. mGluR6-like sign inversion for ON-bipolar pathways).
       - Support maturation-dependent polarity switches (e.g. developmental NKCC1 $\to$ KCC2 chloride transporter transition where early immature GABAergic transmission delivers depolarizing excitation before shifting to hyperpolarizing inhibition).
2. Each stage must declare its cost function `cost(N, E, params) -> (bytes, ops)`.
3. In `tests/test_stages_expression.py`, test:
   - Lateral inhibition produces salt-and-pepper cell fate differentiation;
   - Neutral parameters produce no change;
   - Determinism and cost declaration tests.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 14: Tasks C10–C12 — Pruning, Activity Refinement, Myelination
**Branch:** `task/C10-C12-maturation`

```text
You are working on tasks C10, C11, and C12 (prune, refine_by_activity, myelinate stages) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/spiking/plasticity.py` first. Work on branch `task/C10-C12-maturation`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/maturation.py`
  - `tests/test_stages_maturation.py`
- DO NOT modify `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/maturation.py`:
   - `@register_stage("prune")`:
     - Removes weak synapses below threshold and applies homeostatic synaptic scaling.
     - **Multiplicative homeostatic scaling**: scales total incoming synaptic weights toward a target setpoint $W_{\text{target}}$ or target firing rate via multiplicative scaling factor $\gamma$ ($w_i \leftarrow \gamma \cdot w_i$), preserving relative Hebbian synaptic weight ratios $w_i / w_j$.
     - **Multi-timescale integration**: computes homeostatic setpoint error over slow time-averaged activity windows, preventing transient bursting patterns from causing spurious weight resets.
     - Supports competitive punishment pruning: inactive synapses are only eliminated when target cells receive active, competing inputs (acausal depression below pruning threshold), matching the biological failure of passive disuse alone to eliminate uncompetitive connections.
   - `@register_stage("refine_by_activity")`:
     - Runs a developmental simulation phase with spontaneous waves (retinal/cochlear wave patterns) or sensory inputs.
     - **Wave generator models**:
       - Support propagating spontaneous bursts generated either by intrinsic bursting drivers or by spatio-temporal wave fields (e.g. moving Gaussian pulse of depolarization, velocity $v$, with prolonged seconds-scale relative refractory trailing zones preventing backwards reflection and producing mutual annihilation upon collision).
     - Implements the two-stage hierarchical refinement: coarse molecular projections refined by correlated activity.
     - Applies STDP / Hebbian plasticity rules from `neurogenesis.spiking.plasticity`:
       - Synchronous neighbor firing strengthens/stabilizes connections (tLTP).
       - Asynchronous / uncorrelated inputs undergo depression (tLTD) and pruning.
       - Mexican-hat lateral interactions or competitive sum-rule normalization to prune exuberant branches into localized receptive fields.
   - `@register_stage("myelinate")`:
     - Models axonal delay reductions (conduction speedups):
       - Caliber threshold: only myelinate axons exceeding a caliber/distance threshold (unmyelinated axons $\le 1\ \mu\text{m}$ remain at base unmyelinated conduction speed $\propto \sqrt{d}$, while myelinated axons achieve linear scaling $\text{speed} \propto d$).
       - Activity & length-dependent delay tuning: selectively reduces integer tick delays ($1\text{ to }31\text{ ticks}$) for active or long-range projections, enabling compensatory delay synchronization across unequal physical lengths (modeling auditory coincidence lines and transcallosal synchronization).
2. Each stage must declare its cost function `cost(N, E, params) -> (bytes, ops)`.
3. In `tests/test_stages_maturation.py`, test:
   - Pruning eliminates sub-threshold connections and compacts sparse connectivity;
   - Activity-dependent refinement increases weights of correlated cell pairs;
   - Determinism and cost verification.
4. Run `JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

