# neurogenesis-sim roadmap

This roadmap turns the current toolbox (body plan → one fixed growth procedure → spiking network) into a **versatile
developmental engine**. A user must be able to:
- **build everything by hand** (supervised: shapes, layers, cell positions, connections all specified);
- **let genes do everything** (unsupervised: a genome, development and evolution);
- **or anything in between** (semi-supervised): for example a hand-drawn cortex with its layers and cytochrome-oxidase
  blobs or orientation pinwheels, on which genes control proliferation, migration, differentiation and wiring.

Development is an **arbitrary, ordered list of stages** (for example: 1 proliferation, 2 migration, 3 differentiation,
4 proliferation of differentiated cells, 5 axon growth, 6 activity-dependent pruning ...). Each stage, and each
parameter of each stage, can be set by hand, controlled by genes, read from a hand-drawn field, or fitted to data.

Everything must stay **cheap**: development and simulation scale linearly with the number of cells and synapses, run on
a laptop CPU for small systems, and say what they will cost before running (neurogenesis.cost).

Tasks are written so that different agents can work on them in parallel. Read `AGENTS.md` first.

---

## 1. Target architecture

```
Project (JSON + .npz, versioned schema)
├── Geometry          shapes in 2D / 3D: primitives, meshes, voxel masks; coordinate frames (e.g. cortical depth)
├── Fields            hand-made or generated data on the geometry: scalar (layer boundaries, morphogen gradients),
│                     vector (orientation, migration directions), labels (areas, layers), point sets (pinwheel
│                     centres, blob centres) — sampled at any position
├── Genome            nested dict of genes (existing neurogenesis.genome)
├── Schedule          ordered list of Stage configs, possibly repeated or looped
│     Stage = operator + parameters; every parameter is a Param:
│             const(value) | gene(path, low, high) | field(name, transform) | fit(target, metric) | expr(formula)
├── Data Sources      (optional) public connectome / reconstruction datasets & filters (Phase I)
├── Pharmacology      (optional) profile reference & transmitter-receptor dynamics (Phase P)
├── Morphology        (optional) branching neurite & arbor configurations (Phase N)
└── Plan              (existing BodyPlan) still usable: a plan is compiled into a default schedule

Tissue (struct of arrays, the state that stages transform)
  position (N, 3), parent / lineage id, birth stage, cell type, region label, expression (N, K genes),
  sign (exc / inh), neuron parameters, alive flag,
  transmitter (N, int8 bitmask / list), receptor_expression (N, R, float32),
  morphology (optional ArborStore: nodes, compartments, branches)  +
  Connectivity (sparse: pre, post, weight, delay, receptor_class, optional pre_node, post_node, path_length, dendritic_distance)

Stages (operators: Tissue x Params x rng -> Tissue)
  seed_cells, proliferate, apoptosis, migrate, sort / layer, mosaic, express (gene regulatory step), differentiate,
  identity, grow_axons (guidance rules), synaptogenesis, prune, refine_by_activity (waves, twitches, STDP),
  myelinate, scale (homeostasis), place_by_hand, connect_by_hand, freeze

Compiler: Tissue -> SNNNetwork (existing spiking kernel and models) ; simulation and cost (existing)
Optimisers: evolution of genes (existing islands) ; fitting of `fit` params to targets ; mixed
GUI (viz/): geometry and field editor, schedule editor, step-by-step development preview, export / import Project
```

**The single most important rule: hand, gene, field and fit are interchangeable at the level of each parameter.**
- Supervised development means every `Param` is `const`, `field` or hand placement.
- Unsupervised development means `gene` params evolved.
- Semi-supervised development mixes them.
- `fit` params are optimised against data: cell densities, layer thickness, connection statistics, receptive fields.

## 2. Design principles (binding for every task)
1. **Reproducibility.** Same project, genome and development seed give the same tissue and network, bit for bit on a
   given platform.
   - Each stage draws from its own random stream, `np.random.default_rng([seed, stage_index, stage_salt])`. Adding,
     removing or reordering one stage must not change the random numbers of the others.
   - The legacy `grow()` keeps its single stream (backward compatibility, section 5).
2. **Backward compatibility.** Existing plans and genomes keep growing the same networks (fingerprint tests). New
   options default to "off".
3. **Generality.** No species, task or environment names in the core: no "retina", "foraging" or "cortex" in
   `neurogenesis/`. Domain content lives in examples, modules or user projects.
4. **Low compute.**
   - Every operator is O(N) or O(N log N) in cells and O(E) in synapses, using spatial hashing or cell lists for every
     local interaction.
   - **Never build a dense N × N matrix** except below a documented size threshold. The current `grow()` builds a dense
     Ns × Nd probability matrix per projection; task D2 removes this bottleneck.
   - Use float32, struct of arrays and vectorised NumPy or JAX; process large tissues in chunks.
5. **Cost first.** Each stage declares its cost (memory and time as functions of N and E). `neurogenesis.cost` sums
   them before a run, as it already does for simulations, and refuses what cannot fit.
6. **Data, not code, in projects.** A Project is a JSON (+ `.npz` for large arrays) that validates against a schema.
   Plugins (Python modules registering rules, stages or models) are listed by name and imported on load, as
   `BodyPlan.plugins` already is.
7. **Each part is testable alone.** Stages are pure functions of (tissue, params, rng); the GUI only edits and previews
   Project files; Python runs the full development.

## 3. Current state (2026-11-01)
| Area | Present | Missing |
|---|---|---|
| Spiking | integer LIF kernel, bit-identical in Python, JAX and the browser; `two_compartment` and `hh` models; batched runs; cost estimator with machine calibration; STDP, Hebbian and three-factor plasticity (E1) | per-region choice of model |
| Development | `BodyPlan` (regions, projections), one fixed growth order (placement → sign → differentiation → identity → axons), rule registry in 5 phases (placement, shift, target, probability, weight), knockouts, tonic currents; geometry, fields, `Tissue`, stage schedule (A1–A5, B1–B5, C1–C13, D2, D3; see `docs/STAGES.md`) | chunked growth (D4), and the parts of C8, D1 and D2 marked partial below |
| Genome / evolution | gene paths, [0, 1] coding, gene groups, JSON; island model, robust fitness, audits; `Param` sources (A3); fitting of `Fit` params (E2), inner-loop fitting and Pareto evolution (E3) | gradient-based fitting |
| Modules | save / load, composition, plugins, neuron model recorded; versions, local registry (G1); validation assays (E4) | a shared online catalogue |
| GUI | 3D viewer and per-neuron editing of a finished network | geometry and field editor, schedule editor, development preview, Project import / export |
| CI | GitHub Actions: tests on Python 3.10 and 3.12, browser-kernel equivalence, viewer build, cost command line, fixed CPU performance benchmarks (report only, regressions above 30% flagged) | coverage |

---

## 4. Tasks

Each task gives: **goal, deliverables, interfaces, acceptance tests, dependencies.**
- A task is done when its tests pass locally (and in CI when run) and its documentation is written. (Until Dec 1, CI minutes are capped: local test runs with command + summary line are pasted into PRs for merge).
- Interfaces marked **[contract]** are shared by several tasks: change them only through task A1, and announce it in the PR.

### Phase A: foundations (start here; A1–A4 mostly sequential)

**A1. Project schema and I/O [contract].**
- **Deliverables:**
  - `neurogenesis/project/schema.py`: a JSON schema with a version field;
  - `Project.load` / `save` (JSON + `.npz` side file for large arrays);
  - migration functions between schema versions;
  - `docs/PROJECT_FORMAT.md`.
- **Contents:** geometry, fields, schedule, genome, optional plan, plugins, neuron model, metadata.
- **Tests:** round trip; schema rejects malformed files; version migration.
- **Dependencies:** none.

**A2. Tissue state [contract].**
- **Deliverables:** `neurogenesis/tissue.py`, a struct-of-arrays `Tissue`. Fields:
  - positions (N, 3) float32;
  - lineage (parent id), birth stage, cell type (int), region (int), expression (N, K) float32;
  - sign, neuron parameters (the `NeuronData` fields), alive mask;
  - optional sparse connectivity.
- **Operations:** add cells, kill (mask then compact), subset, concatenate, and `to_network()` → `SNNNetwork`.
- **Tests:** compaction keeps lineage consistent; `to_network` round trip; memory per cell documented.
- **Dependencies:** none.

**A3. Param sources [contract].**
- **Deliverables:** `neurogenesis/params.py`.
  - **Types:** `Param = Const | Gene(path, lo, hi, integer) | Field(name, transform) | Fit(target, init, lo, hi) | Expr(formula)`.
  - **Resolution:** `resolve(param, genome, fields, positions)` returns a scalar or a per-cell array.
  - **Evolution:** the genes of a schedule are collected automatically into the gene list used by evolution, so no
    hand-written gene lists are needed.
- **Tests:** each source; per-cell resolution through fields; gene collection equals the union of Gene params.
- **Dependencies:** A1.

**A4. Stage interface and scheduler [contract].**
- **Deliverables:** `neurogenesis/stages/base.py`, defining a stage as:
  - `Stage(name, operator, params: dict[str, Param], when=..., repeat=k)`;
  - an `@register_stage` registry;
  - `run_schedule(project, genome, seed) -> Tissue`, with one random stream per stage.
  - **Cost declaration per stage:** `cost(N, E, params) -> (bytes, ops)`, summed by `neurogenesis.cost`.
  - **Development checkpoints:** the tissue saved after each stage, for the GUI preview and for debugging.
- **Tests:**
  - adding a stage does not change the random numbers of the others;
  - repeat and loop semantics;
  - checkpoints reload.
- **Dependencies:** A2, A3.

**A5. Legacy compiler (backward compatibility).**
- **Deliverables:** `BodyPlan` + genome → a schedule whose stages reproduce `development.grow` exactly, including its single random stream, through a `legacy_stream=True` mode.
- **Tests:** the fingerprints of `tests/test_development.py` and of the frozen networks in dependent projects (ask the maintainer for their fixtures).
- **Dependencies:** A4.

### Phase B: geometry and fields (parallel after A1)

**B1. Geometry primitives.**
- **Shapes:** box, sphere, ellipsoid, cylinder, sheet (2D), curved sheet (parametric surface), union / difference.
- **Operations:** `contains(points)`, `sample(n, rng)` (uniform in volume or area), `bounding_box`.
- **Local frames:** for example (u, v) along a sheet and depth w across it.
- **Tests:** sampling uniformity (statistical test); contains / sample consistency.

**B2. Meshes and voxel masks.**
- Import OBJ / STL, with point-in-mesh by ray parity and a voxel cache.
- Voxel masks from `.npz`.
- **Tests:** closed-mesh containment; voxelisation volume within 2 %.
- **Dependencies:** B1.
- **Status:** done: OBJ / STL import, ray parity vectorised over faces with a voxel cache, uniform sampling on the
  mesh volume, voxel masks from `.npz` (`VoxelMaskGeometry`). See `docs/STAGES.md`.

**B3. Scalar, vector and label fields.**
- **Field kinds:**
  - grid-based (2D / 3D arrays, trilinear sampling);
  - analytic (gradients, Gaussians, sums);
  - layer stacks: label by depth with hand-set boundaries, e.g. a "cortical layering" helper with any number of layers and thicknesses as `Param`s.
- **Tests:** sampling accuracy; layer labels match boundaries.
- **Dependencies:** B1.
- **Status:** done: grid, analytic, vector, label and layer-stack fields; layer thicknesses are `Param`s, resolved
  by `Field.bind(genome)` in `run_schedule`.

**B4. Point patterns and maps.**
- **Patterns:** point sets (blobs, centres); regular, jittered and Poisson-disc (minimum distance) generation.
- **Orientation maps:** pinwheel maps from hand-placed singularities with given charges (±1/2), or from band-pass noise. Output: a vector or angle field and the pinwheel positions.
- **Tests:** pinwheel charges recovered; minimum distances respected.
- **Dependencies:** B3.
- **Status:** done: regular, jittered and Poisson-disc point patterns (functions and the registered `PointSetField`);
  `PinwheelField` (hand-placed singularities), `pinwheel_charges`, `find_pinwheels`; band-pass maps return their
  pinwheel positions and charges.

**B5. Field operations.**
- Arithmetic, thresholding, smoothing, distance transforms (distance to a boundary or a point set), gradients.
- Everything must be usable as a `Field` param.
- **Tests:** against analytic results.
- **Dependencies:** B3.
- **Status:** done: `Add`, `Subtract`, `Multiply`, `Threshold`, `GaussianSmooth`, `DistanceTransform` (distance to a
  point set), `Gradient` and `DistanceToBoundary`, in NumPy (no SciPy); composite fields pass `bind(genome)` to their
  sub-fields.

### Phase C: developmental stages (parallel after A4; each a registered stage with tests and cost declaration)

| Task | Stage | Content |
|---|---|---|
| C1 | `seed_cells` | Initial progenitors: by hand (a list of positions or a point set), sampled in a geometry with a density `Param` (possibly a field), or one cell. |
| C2 | `proliferate` | Symmetric or asymmetric division. Division probability per cell is a `Param` (gene, field, const). Daughter displacement; inheritance of expression with noise; lineage records; maximum cell count as a safety bound. |
| C3 | `apoptosis` | Death probability per cell (`Param`); neurotrophic variant: death when a cell gets too little input or output (after connectivity exists). |
| C4 | `migrate` | Movement along a vector field, up or down a scalar field (chemotaxis), radial or tangential, to a target layer (`Field` label), with steps and speed as `Param`s. Inside-out layering by birth order as a test case. Collisions through a cell list (O(N)). |
| C5 | `sort` / `mosaic` | Homotypic repulsion and differential adhesion (cell sorting), with a cell list (O(N)). Generalises the existing `mosaic` rule. |
| C6 | `express` | Gene-regulatory step: expression (N, K) updated by a small regulatory network (Hill-type or sigmoid, weights as `Param`s), with inputs from fields (morphogens) and from neighbours (Notch–Delta). Each step O(N K²); cell-list neighbours. |
| C7 | `differentiate` | Cell type from expression thresholds, fields, lineage or birth order (a rule table of `Param`s); sets the sign and neuron parameters per type. Generalises the existing lateral-inhibition step. |
| C8 | `grow_axons` | The existing guidance rules as a stage, on a sparse candidate search (needs D2). |
| C9 | `place_by_hand` / `connect_by_hand` | Supervised entry points: explicit cells, connection lists or connection rules from the GUI. |
| C10 | `prune` / `scale` | Remove weak synapses (threshold `Param`, optional activity criterion); homeostatic weight scaling to a target input. |
| C11 | `refine_by_activity` | A simulation phase inside development: spontaneous waves (sources and speed as `Param`s) or motor twitches with sensory feedback, a Hebbian or STDP rule, then optional pruning. Uses the spiking models; declares its simulation cost. |
| C12 | `myelinate` | Shorten delays of active or long projections (a `Param` factor). |
| C13 | `freeze` | Validate and compile the tissue to an `SNNNetwork` (end of development, or a checkpoint). |

**Status of C1–C13** (details and limits in `docs/STAGES.md`):
| Task | Status |
|---|---|
| C1 | done: count in a geometry or at one position, `density` (`Param` or field, thinning), point sets (lists, B4 patterns, `PointSetField`) |
| C2 | done: probability, displacement, lineage and `generation`, daughter type, asymmetric division, expression noise, `max_cells` bound |
| C3 | done: probability, density (cell list above N = 2048), neurotrophic in / out degree |
| C4 | done: steps along a direction (or a per-cell vector `Param`), radial, tangential, chemotaxis up / down a scalar field, stop field, boundary, target layer, `min_distance` collisions through the cell list |
| C5 | done: `sort` ranks positions along an axis by a key, differential adhesion (types × types matrix) through the cell list, and the `mosaic` stage (homotypic exclusion zones) |
| C6 | done: sigmoid or Hill step with morphogen and contact (cell-list) inputs |
| C7 | done for expression, field, lineage, birth order and position conditions (values as `Param`s) |
| C8 | partial: guidance rules as a stage; dense only up to 2048 cells per side, sparse cell-list search above (only three probability rules there, see D2); errors on missing guidance |
| C9 | done: `place_by_hand`, `connect_by_hand` (index lists, dense matrices up to 2048 cells, connection rules by region / type / expression with probability, distance and velocity) |
| C10 | done: `prune` by weight and by coactivity (activity criterion), `scale` to a target sum with a `rate` |
| C11 | done: `lif_int` run with Poisson drivers, injected spikes, spontaneous waves or motor twitches with sensory feedback, then STDP, Hebbian or three-factor plasticity (follow with `prune`) |
| C12 | done: one factor for all delays, or for synapses selected by length, regions or presynaptic activity |
| C13 | done: `freeze` validates and compiles (optionally writes JSON / NGB1); `develop(project, genome, seed)` |

**Acceptance tests for every stage:**
- determinism;
- no-op with neutral parameters;
- the documented biological behaviour on a toy tissue (e.g. C4: inside-out order of birth vs depth);
- cost declaration within a factor 3 of measured memory and time.

### Phase D: performance

**D1. Cell lists / spatial hash.**
- Shared neighbour search: radius queries and k-nearest, in NumPy, with optional JAX.
- **Tests:** exact against brute force on small sets; O(N) scaling measured.
- **Status:** partial: `CellList` radius and k-nearest queries, vectorised in NumPy (#45) with chunked memory and a
  declared cost; no JAX path.

**D2. Sparse guidance.**
- Candidate targets only within c·σ of the target point (cell lists), then the same probabilities as the dense version.
- **Must reproduce** the dense version exactly when the cutoff covers all candidates (`exact=True` mode, for backward compatibility).
- **Then** the default for large tissues.
- **Tests:** equality in exact mode; memory O(E) for 10⁵ cells.
- **Dependencies:** D1.
- **Status:** partial: `sparse_guidance` with an exact (dense) mode and a cell-list mode supporting three probability
  rules (`identity_expression`, `no_autapse`, `source_sign`); `grow_axons` uses the cell-list mode by default above
  2048 cells per side (#44). The sparse mode draws different random numbers from the dense one, and the legacy `grow()`
  stays dense (fingerprints).

**D3. Development cost model.**
- Per-stage cost declarations summed by `neurogenesis.cost`, with machine calibration as for simulations.
- **Command line:** `python -m neurogenesis estimate --project p.json`.
- **Dependencies:** A4.
- **Status:** done: `neurogenesis.devcost` walks the schedule without running it, predicts cells and synapses per stage
  (worst case for `Gene` / `Fit` params), sums the declared costs, calibrates seconds per declared op once per machine,
  and `check_development` refuses schedules whose peak memory does not fit. Synapse predictions of rules and guidance
  are upper estimates.

**D4. Chunked and streaming growth.**
- Tissues larger than memory processed in spatial chunks, writing synapses to disk (`.npz` shards).
- **Dependencies:** D1, D2.
- **Status:** done: `neurogenesis.streaming` (`grow_axons_streaming`, `SynapseShardManifest`, `assemble_shards`, `stream_stats`, `streaming_growth_cost`).

**D5. Performance regression CI.**
- `scripts/benchmark_performance.py` runs fixed CPU simulation and cell-list workloads. Each main-branch run stores its timings and machine fingerprint as a CI artifact and reports regressions above 30 % against the previous run when the machine matches (report only: shared runners vary too much for a gate). Locally, `--baseline perf.json --enforce` makes a regression fail on the machine that recorded the baseline.

### Fix wave (F1–F6, review fixes of Wave 2; not the Phase F viewer tasks)
- **F1** field and geometry instantiation: done (#28).
- **F2** remove `eval`: done (#29, #44): fields, conditions, `Expr` and `CurvedSheet` use the restricted evaluator.
- **F3** guidance through `Param`s, `"src->dst"` keys: done (#30); stricter errors in #38.
- **F4** low compute: done (#31, #44): apoptosis uses the cell list; `grow_axons` builds dense Ns × Nd arrays only up
  to 2048 cells per side (or with `exact=True` up to 2^24 pairs) and uses the sparse cell-list search above.
- **F5** delay limit of 31 ticks: done (#35).
- **F6** `refine_by_activity` correctness and sign preservation: done (#37).

### Phase E: learning and optimisation

**E1. Plasticity component.**
- STDP, Hebbian with normalisation, and three-factor (eligibility × modulator) rules, usable during simulation and in C11.
- Integer-friendly versions for `lif_int`.
- **Tests:** classic STDP window shape; weight bounds; determinism.
- **Status:** done: `STDPRule`, `HebbianRule` (normalised) and `ThreeFactorRule` in `neurogenesis.spiking.plasticity`,
  with integer traces for `lif_int`; used by `refine_by_activity` (C11).

**E2. Supervised fitting of `Fit` params.**
- Targets: cell density per region, layer thickness, connection probability vs distance, receptive-field metrics, firing rates.
- Optimisers: CMA-ES or another gradient-free method (default, robust to stochastic development); JAX gradients where a stage is differentiable.
- Multiple development seeds per evaluation (robustness).
- **Dependencies:** A3, A4.
- **Status:** done: `neurogenesis.fitting` (fitted values in `genome["__fit__"]`, metric registry, CMA-ES, multi-seed
  loss, `python -m neurogenesis fit`). Not done: JAX gradients, receptive-field metrics (add them as registered metrics).

**E3. Semi-supervised workflows.**
- Evolution of `Gene` params with `Fit` params refitted in an inner loop, or fixed.
- Multi-objective (Pareto) option.
- **Dependencies:** E2.
- **Status:** done: `neurogenesis.evolution.semi_supervised` (`inner_fit_evaluator` with refit or fixed `Fit` params,
  `evolve_pareto`, `pareto_front`).

**E4. Validation harness.**
- A declarative assay description (stimuli, readout, metric, gate), stored in modules and rerun by `neurogenesis validate module.json`.
- Knockout assays included.
- **Status:** done: `neurogenesis.validation` and `python -m neurogenesis validate module.json` (stimuli per region,
  rate or fraction-active readout, metrics, gates, pass fraction, knockouts).

### Phase F: Browser Viewer & Web Demo (viz/, TypeScript + three.js)

`viz/` remains the lightweight browser viewer, the reference browser kernel implementation (`kernel.ts`), and the interactive web demo. Full-featured editors move to the native desktop apps (Phase H), while non-UI infrastructure (command protocols, schemas, and streaming) is exposed as shared core contracts.

**F6. Network view enhancements [done].** Viewer colour modes (region, role, sign, mode, compartment) and population spike raster filtering.

**F7. Bridge streaming.** Local streaming (`neurogenesis/bridge/`) of development checkpoints and live simulation activity over standard protocols.

### Phase H: Native Desktop Applications (macOS, Windows, Linux)

Native desktop applications with zero developer setup required for end users:
- macOS app: SwiftUI in `desktop/mac/` (built by the macOS agent).
- Windows & Linux shared app: Avalonia (C# / .NET 8) in `desktop/avalonia/` (built by the Avalonia agent on a Windows machine).
- Both apps consume the portable C simulation kernel (`nglif`), communicate with the embedded Python runtime via the shared bridge (`neurogenesis/bridge/`), render dynamic UI panels generated from the UI schema, and style components per `visual_spec.json`.

- **Ownership & Isolation:**
  - `desktop/mac/` is owned strictly by the macOS agent.
  - `desktop/avalonia/` is owned strictly by the Avalonia agent.
  - Jules agents never edit `desktop/mac/` or `desktop/avalonia/`.
  - `desktop/common/` and `neurogenesis/bridge/` are shared contracts (protocol, NGB1 binary network format, UI schema, visual spec, C kernel `nglif`, golden fixtures, runtime scripts).
  - No app may duplicate shared logic. Everything about stages, Params, models, and genes is driven by the bridge and the UI schema. Visual look is specified by `visual_spec.json`. Simulation uses `nglif`.

- **Tasks:**
  - **H1. Bridge in the package [contract].** (`neurogenesis/bridge/`, protocol spec `desktop/common/PROTOCOL.md`, automated tests) — *by the Mac agent*.
  - **H2. Portable C kernel `nglif` + NGB1 I/O [contract].** (`desktop/common/native/nglif/`, golden fixtures `fixtures/`, 3-OS CI matrix) — *by the Mac agent*.
  - **H3. UI schema export from Python [contract, done].** Versioned JSON export from Python (`python -m neurogenesis ui-schema` and bridge `ui_schema` via `neurogenesis.project.ui_schema.export_ui_schema`): stage registry (Params, kinds, bounds, docs, cost samples), models with cost estimates, guidance/placement rules, genes of a schedule (`collect_genes`), Project schema.
  - **H4. Embedded Python runtime scripts.** Automated packaging scripts using `python-build-standalone` on all three OSes (macOS, Windows, and Linux, x86-64 and arm64).
  - **H5. Windows + Linux application (Avalonia).** (`desktop/avalonia/`, C# / .NET 8 cross-platform UI), consuming `nglif` through P/Invoke C ABI and the Python bridge via JSON-RPC/stdio protocol, dynamic panels generated from UI schema, colors from `visual_spec.json`. Packaging: Windows setup `.exe` + `.zip`, Linux AppImage. Built by the Avalonia agent.
  - **H6. Linux packaging extras (optional / later).** Flatpak manifest and distribution testing.
  - **H7. Release workflow.** GitHub Actions workflow triggered on version tags: builds and bundles macOS DMG (`desktop/mac/`), Windows setup/zip and Linux AppImage (`desktop/avalonia/`); smoke-tests bridge connection and kernel fixtures across all three operating systems.

### Pre-requisite Contract Changes: Connectomes, Pharmacology & Scale

Before implementing Phase I, P, and N, core contracts are updated in dedicated, isolated tasks:

**K1. Project schema extension (contract bump 1.0.0 -> 1.1.0).**
- Add optional top-level sections to Project schema: `data_sources` (dataset id, files, filters), `pharmacology` (profile reference, channel properties), and `morphology` (compartment models, dendritic arbor settings).
- Backward compatibility: schema version bump to `1.1.0` with explicit migration function `migrate_100_to_110()` in `neurogenesis/project/schema.py` ensuring all 1.0.0 projects load and execute identically without modification.
- Dedicated files: `neurogenesis/project/schema.py`, `neurogenesis/project/io.py`, `tests/test_project.py`.
- **Status:** done: `SCHEMA_VERSION = "1.1.0"`, optional sections validated, `migrate_100_to_110`, chained migrations,
  tests in `tests/test_project_schema.py`.

**K2. Tissue struct-of-arrays extensions (contract).**
- Extend `Tissue` with optional/defaulted arrays:
  - `transmitter`: `(N,)` `int8` bitmask or small list (co-transmission support; default 0 = undefined/classic sign).
  - `receptor_expression`: `(N, R)` `float32` (expression levels per receptor type, default empty/neutral).
  - `morphology`: optional reference to `ArborStore` (node arrays, branch parent indices, compartment types).
  - Synapse connectivity arrays extended with:
    - `receptor_class`: `(E,)` `uint8`;
    - optional morphology fields: `pre_node` `(E,)` `int32`, `post_node` `(E,)` `int32`, `path_length` `(E,)` `float32`, `dendritic_distance` `(E,)` `float32`.
- Preserves float64 positions, `clone_id` lineage tracking, and exact bit-for-bit output on existing stages and legacy plans.
- **Status:** done: `Tissue.transmitter`, `receptor_expression`, `morphology`; `SparseConnectivity.receptor_class` and
  the optional morphology arrays, kept aligned by `take` / `concat` / `append` in every stage; fingerprints unchanged.

**K3. Array-backed synapse store & uint32 neuron limit (scale invariant).**
- Lift neuron indexing from `uint16` to `uint32` across all network representations, CSR indices, NGB1 binary format, and spiking kernels (Python, JAX, browser TypeScript, and portable C `nglif`).
- Replace `SNNNetwork` Python list of `SynapseData` objects with a vectorized struct-of-arrays synapse store (`pre`, `post`, `weight`, `delay`, and per-synapse fields) for memory scalability ($O(E)$ memory, handling 10M–150M synapses).
- Vectorized `to_csr()` via `argsort(pre)` with a thin compatibility list view.
- Disallow JSON for networks of this scale; stream to `.npz` or NGB1.
- Synchronized after Mac agent's H2 merges (aligning NGB1 and `nglif` C kernel on uint32).
- **Status:** done: `SNNNetwork.from_arrays`, `_SynapseListView`, vectorized `to_csr` with `uint32` indices, `save_npz` / `load_npz`, `save_json` scale guard, and `uint32` `colIdx` in Python, JAX, browser (`viz/src/sim/types.ts`, `memory.ts`), and C (`nglif`).

**K4. Multi-word spike history for extended conduction delays (kernel contract).**
- Generalize spike history from 1 word (max 31 ticks) to `ceil((max_delay + 1) / 32)` 32-bit words per neuron across all four kernels (Python, JAX, browser `kernel.ts`, and C `nglif`).
- Bit-for-bit equivalence across all four kernels with memory overhead declared in `neurogenesis.cost`.
- Until K4 merges, tasks N3 and I3 must clip conduction delays exceeding 31 ms with a counted warning (never silently).

### Phase I: Connectome Data Layer

Enable importing public connectome datasets (supervised) and using them as statistical targets for developmental fitting (semi-supervised), without hardcoding species or dataset names in `neurogenesis/` core. Optional dependency `pip install -e ".[data]"` (lazy `pyarrow` import).

**I1. Connectome dataset downloader & catalogue.**
- Generic dataset manifest format (`datasets/<id>.json`): dataset URL, file checksums, license, format specifications (Feather, Parquet, CSV, SWC), column mappings, physical unit metadata, and citations.
- CLI command: `python -m neurogenesis data fetch <dataset_id> --target <dir>`.
- Prints dataset size and license before download; caches in `~/.cache/neurogenesis/data` outside repository tree. Resumable, verified against SHA256 checksums.
- Unit tests run against tiny synthetic fixtures created in-memory, never downloading over the network.
- **Status:** done: `neurogenesis.data.catalogue` (manifests, `fetch` with Range resume and SHA-256) and `python -m neurogenesis data info|fetch`.

**I2. Streaming connectome importer.**
- Memory-efficient streaming import via lazy `pyarrow`:
  - Stream neuron annotations (soma coordinates, predicted transmitters) using manifest column mappings.
  - Stream edge tables in record batches filtered with `pyarrow.compute.is_in(pre, post)` directly into sparse connectivity ($O(\text{selected edges})$ memory).
  - Filter criteria: cell type (list / regex), class / superclass, region / ROI, side, explicit ID list, bounding box, minimum synapse count.
  - Print cost estimate before allocating network.
  - Record license and citation metadata in the provenance of created `Tissue` / network.
- **Status:** done: `neurogenesis.data.import_connectome` (CSV with NumPy, Parquet / Feather / CSV with optional pyarrow; filters by type (list or regex), class, superclass, region, side, ids, bounding box, minimum synapses; provenance in `info`).

**I3. Coordinate frames & spatial registration.**
- Map raw voxel coordinates to physical units ($\mu\text{m}$) via affine transform declared in manifest (voxel size, origin offset, optional mirroring).
- Space units set conduction delays; region-local $[0, 1]^3$ coordinates are derived only inside regions.
- Neuropil ROI masks and column coordinates interfaced via `Geometry` and `Field` adapters.
- Clip delays $>31\text{ ms}$ with a counted warning until K4 merges.
- **Status:** partial: affine registration (voxel size, origin, mirroring) and clipped delays; ROI masks and column coordinates through `Geometry` / `Field` adapters are not done (use `VoxelMaskGeometry` and fields directly).

**I4. Synapse count to synaptic weight mapping.**
- Configurable mapping from anatomical synapse counts to functional weights (linear, Hill/saturating, or `Param`).
- Weight mapping fits into target int16 weight range (`w_clip` 512–2047).
- Depends on P1: sign and channel determination compiled through pharmacology profile. (Before P1 exists, accepts an explicit caller-provided transmitter $\to$ sign map).
- **Status:** done: `map_weights` (linear, Hill, log; `Param` values; `w_clip` 512–2047), signs from a transmitter map, transmitter bits from a profile.

**I5. Cell-type statistical targets for fitting.**
- Extract cell-type-level statistical targets for Phase E (`E2` / `E3` fitting):
  - Type $\times$ type synapse matrix, counts per type, degree and weight distributions, transmitter composition, distance dependence;
  - Topographical column fraction (inputs from same vs neighboring columns from B3/B4 field);
  - Spread across individuals/datasets sets fitting tolerance; metrics averaged over development seeds.
- Depends on E2 (`Fit` params).
- **Status:** done: `neurogenesis.data.targets` (`extract_fitting_targets`, `compare_type_statistics`, `mean_weight` and `column_fraction` metrics registered in `neurogenesis.fitting`).

**I6. Optic-lobe column benchmark example.**
- Supervised baseline: import verified subcircuit from local attributed CC-BY 4.0 test fixture (e.g. 14k-neuron visual circuit subset: Mi1, Tm3, Mi4, Mi9 $\to$ T4) and simulate.
- Grown circuit: semi-supervised development where hexagonal columns are a hand-drawn field, cell identities assigned, and developmental parameters fitted via I5/E2 to match imported type matrix and topography.
- Direct statistical comparison between grown and imported networks. Runnable on CPU in minutes.
- Note: Direction selectivity depends on dendritic placement and timing (evaluated post N3/N5), not point-neuron somata.
- **Status:** done: `examples/optic_lobe_column.py` and `tests/test_optic_lobe_column.py`.

### Phase P: Transmitter & Receptor Pharmacology

Transmitter action depends on receptors and developmental context, never a static fixed sign (+1 / -1) per transmitter.

**P1. Pharmacology profiles as data.**
- Profiles in `profiles/<profile_id>.json` mapping neurotransmitter IDs and receptor classes to post-synaptic reversal potentials, kinetics, and conductance parameters.
- Default profile reproduces today's per-neuron sign bit-for-bit (legacy fingerprints and A5 fingerprints unchanged); re-expresses existing `receptor_sign` rule (`gd["receptor"] = "inverting"`).
- Profile entries parameterizable via `Param` (const, gene, field, expr).
- Example documented profile entries with biological citations (e.g. GluCl, mGluR6-like, histamine-gated Cl-, GABA-A/glycine chloride equilibrium switches; Ben-Ari 2002 Nat Rev Neurosci).
- Support co-transmission: presynaptic neuron emits multiple transmitters. Dale's principle is optional.
- **Status:** done: `neurogenesis.pharmacology` (profiles, default profile bit-for-bit, `compile_weights`), example profile in `examples/profiles/`. Not done: re-expressing the legacy `receptor_sign` rule.

**P2. Receptor expression & assignment.**
- Cell-type-specific or field-dependent receptor expression profiles (`Tissue.receptor_expression`).
- Post-synaptic receptor type assignment during synaptogenesis based on transmitter-receptor compatibility rules.
- **Status:** done: `set_transmitters`, `express_receptors`, `assign_receptors` stages.

**P3. Developmental switches & context compilation.**
- Model developmental shifts in reversal potentials (e.g. GABA depolarizing early $\to$ hyperpolarizing later).
- Compile step maps (transmitter, receptor class, developmental context) into signed integer weight and channel assignment for `lif_int`, or conductance reversal potential for float models.
- Operates both during development (inside C11 `refine_by_activity`) and during network compilation.
- **Status:** partial: `pharmacology` stage compiles signed integer weights per context (run before and after `refine_by_activity`); reversal potentials for float models wait for P4.

**P4. Multi-channel & conductance-based spiking kernels (post H2, K3, K4).**
- Integer LIF: $k$ synaptic current channels with distinct decay shifts, bit-for-bit equivalent across all four kernels.
- Float models (`two_compartment`, `hh`): conductance-based synapses with reversal potentials, equivalent within floating-point tolerance.

**P5. Neuromodulation & volume transmission.**
- Diffuse neuromodulatory fields acting on plasticity eligibility traces (interfacing Phase E `ThreeFactorRule`).
- **Status:** done: `neurogenesis.neuromodulation` (`VolumeModulator`, `apply_modulated_plasticity`, `neuromodulate` stage).

### Phase N: Branching Neurites & Arbor Morphology

Grow realistic arbor morphologies and calculate conduction delays based on neurite path length rather than Euclidean soma distance.

**N1. ArborStore morphology representation & SWC I/O.**
- Low-memory struct-of-arrays representation of tree morphologies (`ArborStore`): node coordinates, radii, parent indices, compartment types.
- Generic compartment labels: soma, axon, dendrite, neurite + user labels (supporting unipolar invertebrate architectures without enforcing apical/basal).
- SWC format reader, downsampler, and writer.
- **Status:** done: `neurogenesis.arbors` (`ArborStore`, `read_swc`, `write_swc`, `downsample`, `to_budget`, path lengths).

**N2. `grow_arbors` developmental stage.**
- Stochastic branching stage: branching probability, elongation, branching angle, stop/target field rules, retraction.
- Every parameter is a `Param`; draws randomness strictly from stage `rng`.
- Cost declared and verified within factor 3.
- **Status:** done: `grow_arbors` stage (`docs/STAGES.md`).

**N3. Arbor synaptogenesis & path-length conduction delays.**
- Geometric proximity search between axons and dendrites using D1 `CellList` in $O(\text{nodes})$.
- Conduction delay calculated from path length along neurites + axonal velocity.
- Clips delays $>31\text{ ms}$ with counted warning until K4 merges.
- Populates per-synapse morphology fields (`pre_node`, `post_node`, `path_length`, `dendritic_distance`).
- **Status:** done: `arbor_synapses` stage (cell list over nodes, delays from path length, clipped with a counted warning).

**N4. Connectome SWC skeleton import & simplification.**
- Import reconstructed arbor skeletons from connectome datasets into `ArborStore` format with automatic downsampling/simplification to target compartment budgets.
- **Status:** done: `neurogenesis.data.skeletons` (`simplify_arbor_rdp`, `import_connectome_skeletons`, `attach_connectome_skeletons`).

**N5. Compartmental & dendritic attenuation simulation (post P4).**
- Multi-compartment or passive dendritic filtering approximation in spiking simulation to capture distal vs proximal synaptic efficacy based on `dendritic_distance`.
- **Status:** done: `neurogenesis.dendritic` (`apply_dendritic_attenuation`, `dendritic_attenuate` stage, distal compartment routing for `two_compartment`).

### Phase G: modules, docs and examples

**G1. Module registry.** Versioned modules (semantic version, toolbox version range), a local catalogue file, `neurogenesis install module.json`, compatibility checks.
- **Status:** done: `neurogenesis.modules.registry` (`version` and `toolbox` range on `Module`, catalogue with
  checksums, `install`, `modules`, `get` of the latest compatible version).

**G2. Worked examples**, each runnable on a laptop in minutes, each with a test:
1. a hand-built cortical column, with layers drawn by hand and genes deciding cell types within layers (semi-supervised);
2. a sheet with hand-placed orientation pinwheels, where proliferation and migration produce cell densities that follow the map (semi-supervised);
3. a fully genetic development with proliferation → migration → differentiation → proliferation of differentiated cells → axon growth (unsupervised, evolved on a toy objective);
4. a fully hand-built network (supervised), compiled and simulated.
- **Status:** done: `examples/hand_drawn_column.py` (1), `examples/pinwheel_sheet.py` (2),
  `examples/evolved_development.py` and `examples/layered_sheet.py` (3), `examples/hand_built_network.py` (4), each
  tested in `tests/test_examples.py`.

**G3. Documentation.** A tutorial per workflow (supervised / unsupervised / semi-supervised), the stage reference generated from the registry, and the cost guide.

---

## 5. Order of work and dependencies
```
A1 ─┬─ A3 ─┐
A2 ─┴──────┴─ A4 ─┬─ A5 (backward compatibility)
                  ├─ C1..C13 (parallel)      D1 ─ D2 ─ D4
B1 ─┬─ B2         ├─ D3                      E1 (parallel with C)
    └─ B3 ─┬─ B4  └─ E2 ─ E3 ; E4
           └─ B5
H1 (bridge, Mac agent) ─┬─ H2 (nglif C kernel, Mac agent)
                        ├─ H3 (UI schema export) ───┬─ H5 (Avalonia app, Win+Linux) ── H7 (release)
                        └─ H4 (python-build-standalone) ┴─ (H6 optional Linux extras)

Contracts:
K1 (schema 1.1.0) ─┬─ K2 (Tissue SOA) ─┬─ I1 ─ I2 ─ I3 ─┐
                   │                   ├─ P1 ─ P2 ─ P3 ─┴─ I4 ── I5 (needs E2) ── I6 (needs B3/B4)
                   │                   └─ N1 + N4 ─ N2 ─ N3 (clips >31ms until K4) ── N5 (needs P4)
                   │
                   └─ (after H2) ── K3 (uint32 store) ─┬─ K4 (multi-word delays) ── P4 (channels) ── P5
                                                       └─ N3 full delays

G1 any time after A1 ; G2 after the stages it uses ; G3 last
```

**Milestones:**
1. **M1:** A1–A5 and D1 merged; the legacy growth runs as a schedule with identical fingerprints.
2. **M2:** B1–B3, C1–C4, C7, C8 (with D2), C13; example G2.3 runs.
3. **M3:** B4, B5, C5, C6, C9–C12, E1, E2; examples G2.1, G2.2 and G2.4.
4. **M4:** H1–H4 merged; native desktop apps (macOS SwiftUI in `desktop/mac/`, Windows + Linux Avalonia in `desktop/avalonia/`) load a Project, dynamically render schedule and parameter editors from the UI schema, run development through the bridge, and simulate live with `nglif`.
5. **M5:** K1–K4, Phase I (connectome data layer & streaming import), Phase P (pharmacology profiles & multi-channel kernels), Phase N (morphology arbors & SWC import); example I6 (optic lobe column benchmark) runs.
6. **M6:** Re-express legacy growth as real C stages (placement, differentiation, identity, guidance) with fingerprints deliberately regenerated and certified.
