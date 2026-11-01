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
  transmitter (N, int8), receptor_expression (N, R, float32),
  morphology (optional ArborStore: nodes, compartments, branches)  +
  Connectivity (sparse: pre, post, weight, delay, receptor_class)

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
| Spiking | integer LIF kernel, bit-identical in Python, JAX and the browser; `two_compartment` and `hh` models; batched runs; cost estimator with machine calibration | plasticity during simulation as a reusable component (STDP, three-factor); per-region choice of model |
| Development | `BodyPlan` (regions, projections), one fixed growth order (placement → sign → differentiation → identity → axons), rule registry in 5 phases (placement, shift, target, probability, weight), knockouts, tonic currents | geometry, fields, tissue state, stages, schedule, proliferation, apoptosis, true migration dynamics, gene-expression dynamics, activity-dependent refinement, sparse guidance |
| Genome / evolution | gene paths, [0, 1] coding, gene groups, JSON; island model, robust fitness, audits | `Param` sources (hand / gene / field / fit); supervised fitting; multi-objective |
| Modules | save / load, composition, plugins, neuron model recorded | module registry and versioning; validation harness |
| GUI | 3D viewer and per-neuron editing of a finished network | geometry and field editor, schedule editor, development preview, Project import / export |
| CI | GitHub Actions: tests on Python 3.10 and 3.12, browser-kernel equivalence, viewer build, cost command line | coverage and performance regression checks |

---

## 4. Tasks

Each task gives: **goal, deliverables, interfaces, acceptance tests, dependencies.**
- A task is done when its tests pass in CI and its documentation is written.
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

**B3. Scalar, vector and label fields.**
- **Field kinds:**
  - grid-based (2D / 3D arrays, trilinear sampling);
  - analytic (gradients, Gaussians, sums);
  - layer stacks: label by depth with hand-set boundaries, e.g. a "cortical layering" helper with any number of layers and thicknesses as `Param`s.
- **Tests:** sampling accuracy; layer labels match boundaries.
- **Dependencies:** B1.

**B4. Point patterns and maps.**
- **Patterns:** point sets (blobs, centres); regular, jittered and Poisson-disc (minimum distance) generation.
- **Orientation maps:** pinwheel maps from hand-placed singularities with given charges (±1/2), or from band-pass noise. Output: a vector or angle field and the pinwheel positions.
- **Tests:** pinwheel charges recovered; minimum distances respected.
- **Dependencies:** B3.

**B5. Field operations.**
- Arithmetic, thresholding, smoothing, distance transforms (distance to a boundary or a point set), gradients.
- Everything must be usable as a `Field` param.
- **Tests:** against analytic results.
- **Dependencies:** B3.

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

**Acceptance tests for every stage:**
- determinism;
- no-op with neutral parameters;
- the documented biological behaviour on a toy tissue (e.g. C4: inside-out order of birth vs depth);
- cost declaration within a factor 3 of measured memory and time.

### Phase D: performance

**D1. Cell lists / spatial hash.**
- Shared neighbour search: radius queries and k-nearest, in NumPy, with optional JAX.
- **Tests:** exact against brute force on small sets; O(N) scaling measured.

**D2. Sparse guidance.**
- Candidate targets only within c·σ of the target point (cell lists), then the same probabilities as the dense version.
- **Must reproduce** the dense version exactly when the cutoff covers all candidates (`exact=True` mode, for backward compatibility).
- **Then** the default for large tissues.
- **Tests:** equality in exact mode; memory O(E) for 10⁵ cells.
- **Dependencies:** D1.

**D3. Development cost model.**
- Per-stage cost declarations summed by `neurogenesis.cost`, with machine calibration as for simulations.
- **Command line:** `python -m neurogenesis estimate --project p.json`.
- **Dependencies:** A4.

**D4. Chunked and streaming growth.**
- Tissues larger than memory processed in spatial chunks, writing synapses to disk (`.npz` shards).
- **Dependencies:** D1, D2.

**D5. Performance regression CI.**
- Timing of fixed benchmarks stored per commit; CI fails if a benchmark is more than 30 % slower.

### Phase E: learning and optimisation

**E1. Plasticity component.**
- STDP, Hebbian with normalisation, and three-factor (eligibility × modulator) rules, usable during simulation and in C11.
- Integer-friendly versions for `lif_int`.
- **Tests:** classic STDP window shape; weight bounds; determinism.

**E2. Supervised fitting of `Fit` params.**
- Targets: cell density per region, layer thickness, connection probability vs distance, receptive-field metrics, firing rates.
- Optimisers: CMA-ES or another gradient-free method (default, robust to stochastic development); JAX gradients where a stage is differentiable.
- Multiple development seeds per evaluation (robustness).
- **Dependencies:** A3, A4.

**E3. Semi-supervised workflows.**
- Evolution of `Gene` params with `Fit` params refitted in an inner loop, or fixed.
- Multi-objective (Pareto) option.
- **Dependencies:** E2.

**E4. Validation harness.**
- A declarative assay description (stimuli, readout, metric, gate), stored in modules and rerun by `neurogenesis validate module.json`.
- Knockout assays included.

### Phase F: Browser Viewer & Web Demo (viz/, TypeScript + three.js)

`viz/` remains the lightweight browser viewer, the reference browser kernel implementation (`kernel.ts`), and the interactive web demo. Full-featured editors move to the native desktop apps (Phase H), while non-UI infrastructure (command protocols, schemas, and streaming) is exposed as shared core contracts.

**F6. Network view enhancements [done].** Viewer colour modes (region, role, sign, mode, compartment) and population spike raster filtering.

**F7. Bridge streaming.** Local streaming (`neurogenesis/bridge/`) of development checkpoints and live simulation activity over standard protocols.

### Phase H: Native Desktop Applications (macOS, Windows, Linux)

Three native desktop applications with zero developer setup required for end users (embedded Python runtimes, native installers, portable C simulation kernel).

- **Ownership & Isolation:**
  - `desktop/mac/` is owned strictly by the macOS agent.
  - `desktop/windows/` is owned by the Windows agent.
  - `desktop/linux/` is owned by the Linux agent.
  - `desktop/common/` and `neurogenesis/bridge/` are shared contracts (protocol, NGB1 binary network format, UI schema, visual spec, C kernel `nglif`, golden fixtures, runtime scripts).
  - No app may duplicate shared logic. Everything about stages, Params, models, and genes is driven by the bridge and the UI schema. Visual look is specified by `visual_spec.json`. Simulation uses `nglif`.

- **Tasks:**
  - **H1. Bridge in the package [contract].** (`neurogenesis/bridge/`, protocol spec `desktop/common/PROTOCOL.md`, automated tests) — *by the Mac agent*.
  - **H2. Portable C kernel `nglif` + NGB1 I/O [contract].** (`desktop/common/native/nglif/`, golden fixtures `fixtures/`, 3-OS CI matrix) — *by the Mac agent*.
  - **H3. UI schema export from Python [contract].** Versioned JSON export from Python (`python -m neurogenesis ui-schema`): stage registry (Params, kinds, bounds, docs), models with cost estimates, guidance/placement rules, genes of a schedule (`collect_genes`), Project schema. Jules task once H1/PR #5 is merged.
  - **H4. Embedded Python runtime scripts.** Automated packaging scripts for embedded Python runtimes on macOS, Windows, and Linux (x86-64 and arm64).
  - **H5. Windows application.** (`desktop/windows/`, e.g. C# / WinUI 3 or .NET + GPU renderer), consuming `nglif` through C ABI and the Python bridge via JSON-RPC/stdio protocol, dynamic panels generated from UI schema, colors from `visual_spec.json`; MSIX/installer artifact.
  - **H6. Linux application.** (`desktop/linux/`, e.g. GTK4 or Qt), consuming `nglif` and the bridge identically; AppImage and/or Flatpak artifact.
  - **H7. Release workflow.** GitHub Actions workflow triggered on version tags: builds and bundles all three native installer artifacts; smoke-tests bridge connection and kernel fixtures across all three operating systems.

### Pre-requisite Contract Changes: Connectomes, Pharmacology & Scale

Before implementing Phase I, P, and N, three versioned contract changes are delivered in dedicated PRs:

**C-1. Project schema extension (contract bump).**
- Add optional top-level sections to Project schema: `data_sources` (dataset id, files, filters), `pharmacology` (profile reference, channel properties), and `morphology` (compartment models, dendritic arbor settings).
- Backward compatibility: schema version bump with validation ensuring existing project files load seamlessly with default values.

**C-2. Tissue struct-of-arrays extensions (contract).**
- Extend `Tissue` with optional/defaulted arrays:
  - `transmitter`: `(N,)` `int8` (index into pharmacology profile, default 0 = undefined/classic sign).
  - `receptor_expression`: `(N, R)` `float32` (expression levels per receptor type, default empty/neutral).
  - `morphology`: optional reference to `ArborStore` (node arrays, branch parent indices, compartment types).
  - Synapse connectivity arrays extended with `receptor_class`: `(E,)` `uint8`.
- Existing stages and legacy growth keep their identical behavior and signatures.

**C-3. Lift 65,535 neuron index limit to uint32 (scale invariant).**
- Upgrade neuron indexing from `uint16` to `uint32` across all network representations, CSR indices, NGB1 binary format, and spiking kernels (Python, JAX, browser TypeScript, and C `nglif`).
- Enables 100k+ to 1M+ neuron connectomes (such as FlyEM male CNS with 211k bodies).
- Equivalence tests must pass across all four kernels.

### Phase I: Connectome Data Layer

Enable importing public connectome datasets (supervised) and using them as statistical targets for developmental fitting (semi-supervised), without hardcoding species/organ names in `neurogenesis/` core.

**I1. Connectome dataset downloader & catalogue.**
- Generic dataset manifest format (`datasets/<id>.json`): dataset URL, file checksums, license, format specifications (e.g. Feather, Parquet, CSV, SWC), citation metadata.
- CLI command: `python -m neurogenesis data fetch <dataset_id> --target <dir>`.
- Automated checksum verification, resumable downloads, and caching.

**I2. Streaming connectome importer.**
- Memory-efficient streaming import via `pyarrow` without loading multi-gigabyte files into monolithic Python memory:
  - Stream neuron annotations (ID, type, soma positions, neurotransmitter predictions).
  - Stream weights / synapse tables directly into sparse connectivity (pre, post, weight) in $O(E)$ memory.
  - Subsetting filters: bounding box, cell type regex/list, minimum synapse count threshold.
- Outputs standard `Tissue` or `SNNNetwork`.

**I3. Coordinate frames & spatial registration.**
- Transform physical voxel coordinates (e.g. 8 nm voxels) to normalized $[0, 1]^3$ simulation boxes and geometry coordinates.
- Support hexagonal column coordinates and neuropil ROI masks as `Geometry` / `Field` adapters.

**I4. Synapse count to synaptic weight mapping.**
- Configurable mapping from raw anatomical synapse counts to functional conductance/weight: linear, saturating/Hill function, or parameterized via `Param` (`const`, `gene`, or `fit`).
- Sign determination via predicted neurotransmitter and target receptor profile.

**I5. Cell-type statistical targets for fitting.**
- Extract empirical statistics from connectome data to serve as targets for Phase E (`E2` / `E3` fitting):
  - Cell type counts and spatial density distributions;
  - Layer- or column-specific connection probability matrices;
  - Convergence and divergence degree distributions.
- Enables developmental stages to grow networks that match real connectome statistics.

**I6. Optic-lobe column benchmark example.**
- Example importing a verified subcircuit (e.g. 14k-neuron visual motion detection circuit: Mi1, Tm3, Mi4, Mi9 $\to$ T4a–d) and simulating motion-direction selectivity.
- Self-contained, runnable on CPU within minutes, with automated regression test.

### Phase P: Transmitter & Receptor Pharmacology

Transmitter action must depend on target receptors and developmental context, never a static fixed sign (+1 / -1) per transmitter.

**P1. Pharmacology profiles & configuration.**
- External profile definitions in `profiles/<profile_id>.json` mapping neurotransmitters and receptors to post-synaptic reversal potentials, kinetics, and conductance parameters.
- No hardcoded chemical names inside core simulation loops; core references integer IDs.

**P2. Receptor expression & assignment.**
- Cell-type-specific or field-dependent receptor expression profiles (`Tissue.receptor_expression`).
- Post-synaptic receptor type assignment during synaptogenesis based on transmitter-receptor compatibility rules.

**P3. Developmental switches & context-dependent reversal potentials.**
- Model developmental shifts in reversal potentials (e.g. early depolarizing to late hyperpolarizing transmission via dynamic chloride equilibria).
- Dynamic parameterization via developmental stages (e.g. `maturation` or `activity_dependent_shift`).

**P4. Multi-channel & conductance-based spiking kernels.**
- Support multiple synaptic currents per neuron (e.g. fast excitation, slow excitation, fast inhibition, slow inhibition) driven by receptor classes.
- Bit-for-bit equivalence across Python, JAX, TypeScript, and C `nglif`.

**P5. Neuromodulation & volume transmission.**
- Diffuse neuromodulatory fields acting on plasticity eligibility traces (interfacing Phase E `ThreeFactorRule`).

### Phase N: Branching Neurites & Arbor Morphology

Grow realistic arbor morphologies and calculate conduction delays based on neurite path length rather than Euclidean soma distance.

**N1. ArborStore morphology representation.**
- Low-memory struct-of-arrays representation of tree morphologies (`ArborStore`): node coordinates, radii, parent pointers, compartment labels (axon, apical dendrite, basal dendrite).
- Seamless conversion to/from standard SWC format.

**N2. `grow_arbors` developmental stage.**
- Developmental stage growing synthetic dendritic and axonal trees using stochastic branching models constrained by tissue boundaries and morphogen guidance fields.

**N3. Arbor synaptogenesis & path-length conduction delays.**
- Synapse formation evaluated by geometric proximity between axonal and dendritic branches (Peters' rule).
- Conduction delay calculated from physical arbor path length + axonal transmission velocity.

**N4. Connectome SWC skeleton import.**
- Import reconstructed arbor skeletons from connectome datasets into `ArborStore` format with automatic downsampling/simplification to target compartment budgets.

**N5. Compartmental / dendritic attenuation simulation.**
- Multi-compartment or passive dendritic filtering approximation in spiking simulation to capture distal vs proximal synaptic efficacy.

### Phase G: modules, docs and examples

**G1. Module registry.** Versioned modules (semantic version, toolbox version range), a local catalogue file, `neurogenesis install module.json`, compatibility checks.

**G2. Worked examples**, each runnable on a laptop in minutes, each with a test:
1. a hand-built cortical column, with layers drawn by hand and genes deciding cell types within layers (semi-supervised);
2. a sheet with hand-placed orientation pinwheels, where proliferation and migration produce cell densities that follow the map (semi-supervised);
3. a fully genetic development with proliferation → migration → differentiation → proliferation of differentiated cells → axon growth (unsupervised, evolved on a toy objective);
4. a fully hand-built network (supervised), compiled and simulated.

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
                        ├─ H3 (UI schema export) ───┬─ H5 (Windows app)
                        └─ H4 (embedded runtimes) ──┴─ H6 (Linux app) ── H7 (release)

Contracts: C-1 (Project schema) ─┬─ C-2 (Tissue SOAs) ── C-3 (uint32 index lift)
                                 ├─ I1 ─ I2 ─ I3 ─ I4 ── I5 (fitting targets) ── I6 (benchmark)
                                 ├─ P1 ─ P2 ─ P3 ── P4 (conductance kernel) ── P5
                                 └─ N1 ─ N2 ─ N3 ── N4 (SWC import) ────────── N5

G1 any time after A1 ; G2 after the stages it uses ; G3 last
```

**Milestones:**
1. **M1:** A1–A5 and D1 merged; the legacy growth runs as a schedule with identical fingerprints.
2. **M2:** B1–B3, C1–C4, C7, C8 (with D2), C13; example G2.3 runs.
3. **M3:** B4, B5, C5, C6, C9–C12, E1, E2; examples G2.1, G2.2 and G2.4.
4. **M4:** H1–H4 merged; the three native desktop apps (macOS, Windows, Linux) load a Project, dynamically render schedule and parameter editors from the UI schema, run development through the bridge, and simulate live with `nglif`.
5. **M5:** C-1..C-3, Phase I (connectome data layer & streaming import), Phase P (pharmacology profiles & multi-channel kernels), Phase N (morphology arbors & SWC import); example I6 (optic lobe column benchmark) runs.
