# Jules Swarm Prompts: Parallel Implementation of neurogenesis-sim Roadmap

This document contains isolated, copy-paste prompts for autonomous Jules agents to implement tasks from `docs/ROADMAP.md` in parallel without git merge collisions.

### Key Strategy to Prevent Merge Conflicts
1. **Strict File Isolation**: Each agent only creates or modifies files within its dedicated domain.
2. **No Shared Index/Doc Edits**: Agents do **not** modify shared entry points (`neurogenesis/__init__.py`, `README.md`, `docs/ROADMAP.md`).
3. **Execution Waves**:
   - **Wave 1 (Active)**: Independent foundations (A1, A2, B1, D1, E1, F6).
   - **Wave 1.5 (Contract & Core Scheduler)**: A3 + A4 (Param sources, stage registry with `pkgutil` auto-import, scheduler) followed by A5 (legacy compiler equivalence).
   - **Wave 2 (Minimal Roadmap Stages & Fields)**: Clean, generic implementations of B2–B4, C1–C7, C10–C12, D2 strictly adhering to the roadmap without speculative biological scope creep.
   - **Wave 3 (Closing the Loop & GUI Editor)**: C13 (freeze & compile), D3 (development cost model), E2–E4 (fitting & validation), F1–F5 (schedule & field editors), G1–G2 (module registry & examples).
4. **General Biological Conventions**:
   - Generic API names: no organ or species names in `neurogenesis/` (e.g. `stop_field`, `morphogen`, `adhesion_rule`). Biological names and mechanisms are cited in docstrings.
   - Self-contained tests: each stage test creates its own toy `Tissue` directly; tests never depend on an unmerged sister branch.

---

# Wave 1: Immediate Parallel Execution (Independent Foundations)

---

## Agent 1: Task A1 — Project Schema & I/O
**Branch:** `task/A1-project-schema`  
*Status: Completed & Merged into main*

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
   - Positions & spatial frame:
     - `positions`: `(N, 3)` `float64` in absolute space units (required for bit-for-bit backward compatibility with legacy grow float64 coordinates).
     - `directions`: `(N, 3)` `float32`, default `(1.0, 0.0, 0.0)` (matching `grow.py` default orientation).
   - Lineage and identity:
     - `cell_id`: `(N,)` `int32` (unique monotonic ID per cell).
     - `parent_id`: `(N,)` `int32` (`-1` for founders).
     - `clone_id`: `(N,)` `int32` (ID of the original founder ancestor).
     - `birth_stage`: `(N,)` `int32`.
     - `cell_type`: `(N,)` `int32`.
     - `region`: `(N,)` `int32`.
   - Gene expression:
     - `expression`: `(N, K)` `float32`.
     - `expression_names`: `list[str]` of length `K` (naming expression channels so stages can address genes by name).
   - Polarity & biophysics:
     - Single source of truth for polarity: `base_weight` carries the sign (positive for excitatory, negative for inhibitory).
     - `sign`: property returning `np.sign(self.base_weight).astype(np.int8)` (or `+1` if 0).
     - `alive`: `(N,)` `bool`.
     - Neuron parameter arrays matching `NeuronData`: `mode`, `shift_v`, `shift_s`, `base_weight`, `conn_radius`, `conn_prob`, `burst_period`, `burst_duty`, `poisson_hz`, `refractory`, `role`, `compartment`, `threshold`.
   - Connectivity: `SparseConnectivity` holding 1D arrays `pre` (`int32`), `post` (`int32`), `weight` (`int32`), `delay` (`int32`).
2. Implement O(N) / O(E) vectorised operations:
   - `add_cells(...)`: append cells, assign `cell_id`s, propagate `clone_id` from parent;
   - `kill(mask)` and `compact()`: remove dead cells (`alive == False`), remap synapse indices (pruning dangling synapses), keeping IDs consistent;
   - `subset(indices)` and `Tissue.concatenate(tissues)`;
   - `to_network() -> SNNNetwork` and `Tissue.from_network(net: SNNNetwork) -> Tissue`;
   - `memory_bytes() -> int` exact accounting of allocated array bytes.
3. In `tests/test_tissue.py`, test:
   - Compaction keeps lineage and synapse mapping intact;
   - `to_network()` round-trip preserves float64 positions and all parameters;
   - Determinism and `memory_bytes()` accuracy.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 3: Task B1 — Geometry Primitives & Registry
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
1. Implement a registry pattern in `neurogenesis/geometry/__init__.py`:
   - `@register_geometry(type_name)` decorator.
   - `geometry_from_dict(d: dict) -> Geometry`: looks up `d["type"]` in registry and calls `cls.from_dict(d)`. This ensures task B2 (meshes) can register `"mesh"` without editing `__init__.py`.
2. Implement 2D/3D geometry primitives in `neurogenesis/geometry/primitives.py`:
   - Shapes: `Box`, `Sphere`, `Ellipsoid`, `Cylinder`, `Sheet2D`, `CurvedSheet`, CSG `Union`, `Difference`.
   - Every geometry class implements:
     - `contains(points: np.ndarray) -> np.ndarray` (bool mask for `(N, 3)` points);
     - `sample(n: int, rng: np.random.Generator) -> np.ndarray` (`(n, 3)` uniform in volume/area using passed `rng`);
     - `bounding_box() -> tuple[np.ndarray, np.ndarray]` (`(min_xyz, max_xyz)`);
     - `local_coordinates(points: np.ndarray) -> np.ndarray` mapping `(x, y, z)` to `(u, v, w) in [0, 1]^3`:
       - Box: normalized Cartesian offset in `[0, 1]^3`;
       - Cylinder: `u = (theta + pi)/(2*pi)`, `v = r / R`, `w = (z - z_min)/(z_max - z_min)`;
       - Sphere: `u = (phi + pi)/(2*pi)`, `v = theta/pi`, `w = r / R`;
       - Sheet2D / CurvedSheet: tangential `(u, v)` along surface and depth `w` across thickness.
     - `to_dict()` and `from_dict(d)`.
3. In `tests/test_geometry_primitives.py`, test:
   - Sample containment (`contains(sample(n, rng)).all()`);
   - Sampling uniformity (chi-square test with fixed seed);
   - Local coordinate bounds inside `[0, 1]^3`;
   - JSON serialization round-trip via `geometry_from_dict`.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
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
1. Implement `CellList` in `neurogenesis/spatial.py` for fast O(N) 3D neighbour queries in `float64` / `float32`:
   - Pure Python + NumPy (no `scipy` dependency).
   - `CellList(positions: np.ndarray, cutoff: float, box: tuple | None = None)`
   - `query_radius(query_points: np.ndarray, radius: float, return_distances: bool = False)` returning CSR arrays `(row_ptr, col_idx[, distances])` sorted deterministically by `(src_idx, dst_idx)`.
   - `query_knn(query_points: np.ndarray, k: int)` returning `(indices, distances)` of shape `(M, k)`:
     - If fewer than `k` neighbors exist within cutoff, pad missing entries with index `-1` and distance `np.inf`.
     - In case of equidistant ties, break ties by ascending cell index.
   - `declared_cost(n_points: int, n_queries: int, mean_neighbours: float) -> tuple[int, int]` (`bytes, ops`).
2. Never build a dense `N x N` distance matrix.
3. In `tests/test_spatial.py`:
   - Exact agreement with brute-force pairwise distances on `N = 300` points;
   - Behavior tests for `query_knn` padding with `-1` and tie-breaking;
   - O(N) scaling test (count operations / cell-bin accesses, mark any heavy timing test with `@pytest.mark.slow`);
   - Cost declaration within factor of 3 of measured bytes.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q -m "not slow"` and ensure all tests pass.
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
1. Implement reusable, deterministic, O(E) synaptic plasticity rules in `neurogenesis/spiking/plasticity.py`:
   - **Pair-based STDP (`STDPRule`):** exponential traces (float32 and integer bit-shift variants for `lif_int`), configurable `A_plus`, `A_minus`, `tau_plus`, `tau_minus`, hard/soft bounds `[w_min, w_max]`, Dale's law sign preservation.
   - **Hebbian with normalisation (`HebbianRule`):** correlation update with multiplicative / subtractive weight scaling (Oja / L1/L2 normalization).
   - **Three-factor learning (`ThreeFactorRule`):** eligibility trace `e_ij(t)` gated by neuromodulator `M(t)`.
   - `declared_cost(num_neurons, num_synapses, ticks) -> tuple[int, int]`.
2. In `tests/test_plasticity.py`, test:
   - Classic STDP Δw curve (`-50 ms` to `+50 ms`);
   - Dale's law sign preservation;
   - Three-factor zero-change when `M(t) == 0`;
   - Bit-for-bit determinism and neutral parameter no-op (`A_plus = A_minus = 0`).
3. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 6: Task F6 — Viewer Region/Type Colouring & Population Raster
**Branch:** `task/F6-viewer-populations`

```text
You are working on task F6 (Network view enhancements) from `docs/ROADMAP.md` in `neurogenesis-sim`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and inspect `viz/src/` first. Work on branch `task/F6-viewer-populations`.

### Allowed Files (Scattered viz updates required for compartment import)
- ONLY create/modify:
  - `viz/src/ui/PopulationFilter.ts`
  - `viz/src/ui/RasterCanvas.ts`
  - `viz/src/render/SceneManager.ts`
  - `viz/src/sim/spatialHash.ts` (to preserve `compartment` and metadata on import)
  - `viz/src/sim/memory.ts` (to store per-neuron compartment buffer)
- DO NOT touch `viz/src/sim/kernel.ts` (browser kernel equivalence), Python files, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Import `compartment` from network JSON in `spatialHash.ts` and `memory.ts`.
2. Implement colour-mode switching in `SceneManager.ts` and `PopulationFilter.ts`:
   - Colour by `role`/`sign` (default), `compartment` (region ID), or `mode`.
3. Filter spike raster and 3D highlights by selected compartments or cell types in `RasterCanvas.ts`.
4. Keep all state driven by the imported network JSON.
5. Verify with `cd viz && npm run build && cd .. && JAX_PLATFORMS=cpu pytest -q`.
```

---

# Wave 1.5: Core Contracts & Scheduler (Sequential Pre-Requisite for Wave 2)

---

## Agent 7: Tasks A3 + A4 — Param Sources & Stage Scheduler
**Branch:** `task/A3-A4-param-scheduler`

```text
You are working on shared contracts A3 (Param sources) and A4 (Stage interface and scheduler) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/tissue.py` first. Work on branch `task/A3-A4-param-scheduler`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/params.py`
  - `neurogenesis/stages/__init__.py`
  - `neurogenesis/stages/base.py`
  - `tests/test_params.py`
  - `tests/test_stages_base.py`
- DO NOT modify `tissue.py`, `project/`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement `neurogenesis/params.py`:
   - `Param = Const(value) | Gene(path, lo, hi, integer) | Field(name, transform) | Fit(target, init, lo, hi) | Expr(formula)`.
   - `resolve(param, genome, fields, positions, cell_indices=None) -> float | np.ndarray`.
   - `collect_genes(stage_configs) -> list[str]`.
2. Implement stage registry with auto-discovery in `neurogenesis/stages/__init__.py`:
   - Use `pkgutil.iter_modules(__path__)` and `importlib.import_module` to dynamically load all submodules in `neurogenesis/stages/` upon import.
   - This guarantees any stage added by future Wave 2 agents (`population.py`, `migration.py`, etc.) is automatically registered without modifying `__init__.py`.
3. Implement `neurogenesis/stages/base.py`:
   - `@register_stage(name)` decorator.
   - `Stage(name, operator, params: dict[str, Param], when=None, repeat=1)`.
   - `run_schedule(project, genome, seed, checkpoints=False) -> Tissue | list[Tissue]`:
     - Isolated RNG per stage: `np.random.default_rng([seed, stage_idx, stage_salt])`.
   - Cost summing: collect `stage.cost(N, E, params)` across schedule.
4. In `tests/test_params.py` and `tests/test_stages_base.py`, test:
   - Resolution of each Param source;
   - Dynamic stage auto-discovery via `pkgutil`;
   - RNG isolation (adding a stage does not change random sequence of subsequent stages);
   - Checkpoint reloading.
5. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 8: Task A5 — Legacy Growth Compiler (Backward Compatibility)
**Branch:** `task/A5-legacy-compiler`

```text
You are working on task A5 (Legacy compiler) from `docs/ROADMAP.md`.
Read `AGENTS.md` and `tests/test_development.py` first. Work on branch `task/A5-legacy-compiler`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/development/legacy_compiler.py`
  - `tests/test_legacy_compiler.py`
- DO NOT modify `grow.py`, `neurogenesis/__init__.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement `compile_plan_to_schedule(plan: BodyPlan, genome: dict) -> list[Stage]` in `neurogenesis/development/legacy_compiler.py`:
   - Converts legacy `BodyPlan` into a stage schedule that reproduces `development.grow` bit-for-bit when run with `legacy_stream=True` (single shared RNG stream).
2. In `tests/test_legacy_compiler.py`, test:
   - Bit-for-bit fingerprint equality with `tests/test_development.py` outputs.
3. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

# Wave 2: Roadmap Developmental Stages & Fields (Parallel)

*All Wave 2 stage tests must be 100% self-contained: create toy `Tissue` fixtures directly (with hand-set `birth_stage`, `expression`, etc.) without depending on sister stage branches.*

---

## Agent 9: Task B2 — Meshes & Voxel Masks
**Branch:** `task/B2-meshes-voxels`

```text
You are working on task B2 (Meshes and voxel masks) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/geometry/__init__.py` first. Work on branch `task/B2-meshes-voxels`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/geometry/mesh.py`
  - `neurogenesis/geometry/voxel.py`
  - `tests/test_geometry_mesh.py`
- DO NOT modify `geometry/__init__.py`, `primitives.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement `MeshGeometry` in `neurogenesis/geometry/mesh.py` using `@register_geometry("mesh")`:
   - Parse OBJ / STL (vertices, triangle faces) using pure NumPy.
   - Point-in-mesh containment via ray-casting parity intersection.
   - Bounding box and occupancy voxel cache.
   - `local_coordinates(points)`: bounding-box normalized `[0, 1]^3`.
2. Implement `VoxelMaskGeometry` in `neurogenesis/geometry/voxel.py` using `@register_geometry("voxel_mask")`:
   - 3D boolean occupancy array with origin and pitch `(dx, dy, dz)`.
   - Vectorized `contains(points)` and rejection-sampled `sample(n, rng)`.
3. In `tests/test_geometry_mesh.py`, test:
   - Ray-parity containment on cube/sphere meshes;
   - Voxelisation volume within 2% of analytic geometry;
   - JSON round-trip via `geometry_from_dict({"type": "mesh", ...})`.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 10: Tasks B3 + B4 + B5 — Fields, Maps, and Field Operations
**Branch:** `task/B3-B5-fields`

```text
You are working on tasks B3, B4, and B5 (Fields, maps, and field operations) from `docs/ROADMAP.md`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/B3-B5-fields`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/fields/__init__.py`
  - `neurogenesis/fields/core.py`
  - `neurogenesis/fields/maps.py`
  - `neurogenesis/fields/ops.py`
  - `tests/test_fields.py`
- DO NOT modify `geometry/`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement fields in `neurogenesis/fields/core.py`:
   - `GridField`: 2D / 3D regular grids (scalar, vector, label) with trilinear / nearest sampling.
   - `AnalyticField`: linear gradients, Gaussians, exponential decay.
   - `LayerStackField`: discrete integer labels and depth `w in [0, 1]` based on boundary thresholds.
2. Implement maps in `neurogenesis/fields/maps.py`:
   - Point patterns: regular, jittered, Poisson-disc sampling.
   - Orientation maps: pinwheel maps from singularities with charges ($q = \pm 1/2$) and bandpass-filtered noise.
3. Implement field arithmetic and transforms in `neurogenesis/fields/ops.py`:
   - Field operations: addition, thresholding, Gaussian smoothing, Euclidean distance transform to boundaries.
4. In `tests/test_fields.py`, test:
   - Sampling accuracy against analytic formulas;
   - Layer labels match boundary definitions;
   - Pinwheel topological charges recovered via contour integrals;
   - Determinism.
5. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 11: Task D2 — Sparse Axon Guidance
**Branch:** `task/D2-sparse-guidance`

```text
You are working on task D2 (Sparse guidance) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, `neurogenesis/spatial.py`, and `neurogenesis/development/rules.py` first. Work on branch `task/D2-sparse-guidance`.

### Allowed Files
- ONLY create/modify:
  - `neurogenesis/development/sparse_guidance.py`
  - `neurogenesis/development/rules.py` (extend rule API to accept candidate pairs in addition to dense matrices)
  - `tests/test_sparse_guidance.py`
- DO NOT modify `grow.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Extend `neurogenesis/development/rules.py`:
   - Update rule contexts so probability/weight rules support both dense matrices and sparse candidate lists `(src_indices, dst_indices)`.
2. Implement sparse axon guidance in `neurogenesis/development/sparse_guidance.py`:
   - Candidate queries restricted to radius $c \cdot \sigma$ using `CellList`.
   - RNG determinism: use coordinate-based or pair-hash random generator (or per-source counter) so sparse search reproduces dense connection choices for candidates covered by the cutoff.
   - Memory bounded: strictly $O(E)$ working memory for $N = 10^5$ cells.
3. In `tests/test_sparse_guidance.py`, test:
   - Equivalence to dense probability for all candidates within cutoff;
   - Existing rule compatibility in `rules.py` (dense rules still pass existing tests);
   - Scaling benchmark (marked `@pytest.mark.slow`).
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q -m "not slow"` and ensure all tests pass.
```

---

## Agent 12: Tasks C1–C3 — Population Stages (Seed, Proliferate, Apoptosis)
**Branch:** `task/C1-C3-population-stages`

```text
You are working on tasks C1, C2, and C3 (seed_cells, proliferate, apoptosis) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, `neurogenesis/tissue.py`, and `neurogenesis/stages/base.py` first. Work on branch `task/C1-C3-population-stages`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/population.py`
  - `tests/test_stages_population.py`
- DO NOT modify `stages/__init__.py`, `tissue.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/population.py`:
   - `@register_stage("seed_cells")`: initializes tissue progenitors from explicit positions or geometry sampling.
   - `@register_stage("proliferate")`:
     - Division probability `Param`.
     - Supports symmetric vs. asymmetric division:
       - Symmetric: two progenitor daughters with identical expression and lineage.
       - Asymmetric: one progenitor daughter, one differentiated daughter with shifted expression or cell type flag.
     - Daughter displacement offset parameter.
     - Tracks `cell_id`, `parent_id`, and `clone_id`.
     - Safety bound: `max_cells` parameter refuses unbounded proliferation.
   - `@register_stage("apoptosis")`:
     - Culling via death probability `Param` or trophic connectivity threshold (kills cells with in-degree below threshold).
2. Each stage declares `cost(N, E, params) -> (bytes, ops)` and consumes isolated `rng`.
3. In `tests/test_stages_population.py`:
   - Create self-contained toy `Tissue` fixtures directly;
   - Determinism with fixed seed and stage salt;
   - Neutral parameters (p=0) are strict no-ops;
   - Max-cells safety bound enforced;
   - Declared cost matches measured within factor of 3.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 13: Tasks C4–C5 — Migration & Sorting Stages
**Branch:** `task/C4-C5-migration-sorting`

```text
You are working on tasks C4 and C5 (migrate, sort/mosaic) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, `neurogenesis/tissue.py`, and `neurogenesis/spatial.py` first. Work on branch `task/C4-C5-migration-sorting`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/migration.py`
  - `tests/test_stages_migration.py`
- DO NOT modify `stages/__init__.py`, `tissue.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/migration.py`:
   - `@register_stage("migrate")`:
     - Step movement along vector fields or up/down scalar fields with speed `Param`.
     - Target layer / boundary arrest: stops migration when crossing a boundary defined by a scalar or label field (`stop_field`).
     - Collision handling via `CellList` to prevent somal overlap.
   - `@register_stage("sort")` / `@register_stage("mosaic")`:
     - Homotypic repulsion and differential adhesion using `CellList` within radius $r$.
2. Each stage declares `cost(N, E, params) -> (bytes, ops)`.
3. In `tests/test_stages_migration.py`:
   - Build toy `Tissue` fixtures directly (set `birth_stage` and initial positions manually in test fixture);
   - Test inside-out layering: verify early-born cells arrest at lower boundary and late-born cells pass them to arrest at superficial boundary;
   - Test mosaic spatial regularity improvement (regularity index increases);
   - Determinism and neutral parameter no-op.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 14: Tasks C6–C7 — GRN Expression & Differentiation
**Branch:** `task/C6-C7-expression-diff`

```text
You are working on tasks C6 and C7 (express, differentiate) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, `neurogenesis/tissue.py`, and `neurogenesis/spatial.py` first. Work on branch `task/C6-C7-expression-diff`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/expression.py`
  - `tests/test_stages_expression.py`
- DO NOT modify `stages/__init__.py`, `tissue.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/expression.py`:
   - `@register_stage("express")`:
     - Updates `tissue.expression (N, K)` via discrete Hill/sigmoid regulatory steps:
       - Inputs from scalar morphogen fields;
       - Juxtacrine neighbour signaling: average neighbour expression within contact radius using `CellList` (contact radius, no Voronoi/scipy dependency);
       - $O(N \cdot K^2)$ complexity.
   - `@register_stage("differentiate")`:
     - Maps continuous expression thresholds, lineage, or spatial coordinates into discrete `cell_type` integers.
     - Assigns biophysical neuron parameters (`shift_v`, `shift_s`, `base_weight`, `threshold`) per cell type from a configuration table.
2. Each stage declares `cost(N, E, params) -> (bytes, ops)`.
3. In `tests/test_stages_expression.py`:
   - Create self-contained toy `Tissue` fixtures directly;
   - Contact-mediated lateral inhibition produces salt-and-pepper pattern on toy tissue;
   - Differentiation assigns correct biophysical parameters according to threshold table;
   - Determinism and neutral parameter no-op.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 15: Tasks C8–C9 — Axon Growth & Supervised Hand Placement
**Branch:** `task/C8-C9-axon-placement`

```text
You are working on tasks C8 and C9 (grow_axons, place_by_hand, connect_by_hand) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/development/sparse_guidance.py` first. Work on branch `task/C8-C9-axon-placement`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/axon_growth.py`
  - `neurogenesis/stages/hand_craft.py`
  - `tests/test_stages_axons_hand.py`
- DO NOT modify `stages/__init__.py`, `tissue.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement `@register_stage("grow_axons")` in `neurogenesis/stages/axon_growth.py`:
   - Packages sparse guidance (D2) into a standard developmental stage consuming `Tissue`.
2. Implement supervised entry points in `neurogenesis/stages/hand_craft.py`:
   - `@register_stage("place_by_hand")`: inserts explicit neuron coordinates and types.
   - `@register_stage("connect_by_hand")`: adds explicit pre-post synapse pairs or connection matrices.
3. In `tests/test_stages_axons_hand.py`, test:
   - Hand-placed cells and connections are accurately appended to `Tissue`;
   - Stage cost declarations and determinism.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 16: Tasks C10–C12 — Pruning, Activity Refinement, Myelination
**Branch:** `task/C10-C12-maturation`

```text
You are working on tasks C10, C11, and C12 (prune, scale, refine_by_activity, myelinate) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and `neurogenesis/spiking/plasticity.py` first. Work on branch `task/C10-C12-maturation`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/maturation.py`
  - `tests/test_stages_maturation.py`
- DO NOT modify `stages/__init__.py`, `tissue.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement registered stages in `neurogenesis/stages/maturation.py`:
   - `@register_stage("prune")`: removes synapses with absolute weight below threshold `w_cut`, compacting `connectivity`.
   - `@register_stage("scale")`: homeostatic multiplicative scaling of synaptic weights to target total input sum $W_{\text{target}}$: $w_i \leftarrow w_i \cdot (W_{\text{target}} / \sum |w_j|)$.
   - `@register_stage("refine_by_activity")`: runs a developmental simulation phase with spontaneous wave drivers or input currents, applying STDP/Hebbian plasticity from `neurogenesis.spiking.plasticity` to adjust synaptic weights.
   - `@register_stage("myelinate")`: reduces conduction delays (`delay`) by factor `delay_factor in (0, 1]` for long-distance or active projections (clamped to minimum 1 tick).
2. Each stage declares `cost(N, E, params) -> (bytes, ops)`.
3. In `tests/test_stages_maturation.py`:
   - Create self-contained toy `Tissue` with synthetic connectivity;
   - Pruning removes sub-threshold synapses and compacts CSR/COO arrays;
   - Scaling preserves relative weight ratios while achieving target sum;
   - Myelination reduces delays with 1-tick floor;
   - Determinism and neutral parameter no-op.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

# Wave 3: Closing the Loop & Pipeline Integrations

---

## Agent 17: Tasks C13 + D3 — Tissue Freeze & Development Cost Model
**Branch:** `task/C13-D3-freeze-cost`

```text
You are working on task C13 (freeze stage) and D3 (development cost model) from `docs/ROADMAP.md`.
Read `AGENTS.md`, `docs/ROADMAP.md`, `neurogenesis/cost.py`, and `neurogenesis/tissue.py` first. Work on branch `task/C13-D3-freeze-cost`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/stages/freeze.py`
  - `neurogenesis/dev_cost.py`
  - `tests/test_freeze_and_dev_cost.py`
- DO NOT modify `stages/__init__.py`, `cost.py`, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement `@register_stage("freeze")` in `neurogenesis/stages/freeze.py`:
   - Validates final tissue state and compiles `Tissue` into a ready-to-simulate `SNNNetwork` (`tissue.to_network()`).
2. Implement development cost aggregation in `neurogenesis/dev_cost.py`:
   - `estimate_schedule_cost(project, genome)`: sums memory bytes and FLOPs declared across all schedule stages before running development.
   - Expose CLI command `python -m neurogenesis estimate --project project.json`.
3. In `tests/test_freeze_and_dev_cost.py`, test:
   - Freeze produces valid `SNNNetwork` that runs in `simulate_counts`;
   - Cost estimation accurately sums declared stage costs.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 18: Tasks E2–E4 — Supervised Fitting, Workflows & Validation
**Branch:** `task/E2-E4-fitting-validation`

```text
You are working on tasks E2 (Supervised fitting of Fit params), E3 (Semi-supervised workflows), and E4 (Validation harness) from `docs/ROADMAP.md`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/E2-E4-fitting-validation`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/fitting.py`
  - `neurogenesis/validation.py`
  - `tests/test_fitting_validation.py`
- DO NOT modify `README.md` or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement parameter fitting in `neurogenesis/fitting.py`:
   - Optimize `Fit` params against quantitative targets (cell density per layer, connection probability vs distance, firing rate distributions) using gradient-free methods across multiple development seeds.
2. Implement validation harness in `neurogenesis/validation.py`:
   - Declarative assay runner (stimuli, readouts, pass/fail gating metrics, knockout assays).
3. In `tests/test_fitting_validation.py`, test:
   - Parameter fitting converges on a synthetic toy target;
   - Validation harness passes valid modules and fails knockouts.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```

---

## Agent 19: Tasks F1–F5 — GUI Schedule & Field Editors (viz/)
**Branch:** `task/F1-F5-gui-editors`

```text
You are working on tasks F1–F5 (Project, geometry, field, and schedule editors) in `viz/`.
Read `AGENTS.md`, `docs/ROADMAP.md`, and inspect `viz/src/` first. Work on branch `task/F1-F5-gui-editors`.

### Strict File Isolation
- ONLY create/modify files within `viz/src/ui/editors/` and `viz/src/ui/ScheduleEditor.ts`
- DO NOT modify `viz/src/sim/kernel.ts` (browser kernel equivalence), Python files, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement Project load/save and undo/redo panel matching the `1.0.0` Project JSON schema.
2. Implement schedule editor UI: an ordered list of stages with parameter switches (`const`, `gene`, `field`, `fit`, `expr`).
3. Implement step-by-step development preview stepping through stage checkpoints.
4. Verify with `cd viz && npm run build && cd .. && JAX_PLATFORMS=cpu pytest -q`.
```

---

## Agent 20: Tasks G1–G3 — Module Registry, Worked Examples & Docs
**Branch:** `task/G1-G3-modules-examples`

```text
You are working on tasks G1, G2, and G3 (Module registry, worked examples, docs) from `docs/ROADMAP.md`.
Read `AGENTS.md` and `docs/ROADMAP.md` first. Work on branch `task/G1-G3-modules-examples`.

### Strict File Isolation
- ONLY create/modify:
  - `neurogenesis/registry.py`
  - `examples/example_cortical_column.py`
  - `examples/example_pinwheel_sheet.py`
  - `examples/example_genetic_growth.py`
  - `tests/test_worked_examples.py`
- DO NOT modify existing examples, `README.md`, or `docs/ROADMAP.md`.

### Deliverables & Requirements
1. Implement module registry and version compatibility checking in `neurogenesis/registry.py`.
2. Implement the worked examples specified in roadmap section G2:
   - `example_cortical_column.py`: semi-supervised layered column;
   - `example_pinwheel_sheet.py`: sheet with orientation pinwheels;
   - `example_genetic_growth.py`: unsupervised genetic growth.
   - Each example must run in under 2 minutes on CPU.
3. In `tests/test_worked_examples.py`, test that all three examples run to completion and produce valid SNNNetworks.
4. Run `cd viz && npm run build:kernel && cd .. && JAX_PLATFORMS=cpu pytest -q` and ensure all tests pass.
```
