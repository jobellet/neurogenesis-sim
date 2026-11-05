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
- A task is done when its tests pass locally (and in CI when run) and its documentation is written. CI runs on every pull request (the repository is public).
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
| C8 | partial: guidance rules as a stage; dense only up to 2048 cells per side, sparse cell-list search above (only three probability rules there, see D2); errors on missing guidance; `expression_gradient` target rule (target map from named graded expression columns, per axis gain and sign, min-max or raw levels; dense and sparse) |
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

### Phase C, second wave: developmental stages C14–C24 (from a literature review)

Eleven stages proposed from the maintainer's literature review (2026-11-02). Each follows the stage
contract (`Tissue × Params × rng → Tissue`), every parameter a `Param`, neutral parameters = no-op, cost declared
O(N) or O(E) (cell list for neighbours), and a test of the documented behaviour on a toy tissue, phrased as "in this
simulation". Numbers (cycle lengths, fractions, bouton counts, ages) are `Param`s with defaults taken from the cited
sources, listed below the table.

| Task | Stage | Mechanism | What it changes | Needs |
|---|---|---|---|---|
| C14 | `cell_cycle_clock` | Cell-cycle algorithm of the ventricular epithelium (Takahashi, Nowakowski and Caviness): a fixed number of integer cycles; cycle length and its G1 phase lengthen; the fraction leaving the cycle (Q) rises while the self-renewing fraction (P = 1 − Q) falls. | Per cycle: reads `generation` (C2), sets each progenitor's exit probability Q(generation) (a `Param`: table, gene or field) and marks exiting cells postmitotic; optionally records the cycle length per generation as the birth time used by later stages. | C2; K6 (`cycling` flag) |
| C15 | `temporal_competence` | Progressive, irreversible loss of progenitor competence: early progenitors can make deep-layer and later superficial-layer neurons, older ones lose the early fates. | Updates competence expression channels as a one-way cascade (a channel can be switched off, never back on) driven by `generation` or stage index; `differentiate` conditions read them, so the same rule table gives birth-order-dependent fates. | C6, C7, C14 |
| C16 | `fasciculate` | Follower axons bundle along pioneer tracts through homophilic adhesion (e.g. L1, NCAM, Fasciclin II) and leave them where anti-adhesive cues act. | On growing arbors (N2): growth cones within a radius of a pioneer branch steer towards its direction, weighted by an adhesion code (`Param` matrix); a defasciculation field releases them. For `grow_axons` (no trajectories): followers inherit their pioneer's target offset, i.e. correlated targets. | N2, D1 |
| C17 | `choice_point` | Choice points (e.g. a midline): after crossing, guidance receptors are switched (attraction off, repulsion on), which prevents re-crossing; a new cue then steers the axon. | On N2 arbors: when a growth cone enters a choice-point geometry or field, its guidance rule set is replaced by a second one (`Param`s), and re-entry is blocked. For `grow_axons`: a projection through a waypoint region (target of leg 1 = source frame of leg 2). | N2, C8 |
| C18 | `partner_select` | Proximity is not enough (deviation from Peters' rule): synapses form only between compatible partners, through transmembrane recognition pairs (e.g. neurexin–neuroligin isoforms biasing excitatory versus inhibitory synapses). | Filters candidate synapses (from `grow_axons` or `arbor_synapses`) with a compatibility table of presynaptic × postsynaptic recognition channels (`Param` matrix, probabilities), optionally also by transmitter–receptor match (P2). Generalises the `identity_expression` rule. | P2, N3 |
| C19 | `cluster_boutons` | Connection multiplicity is cell-type specific: some connections use one or two contacts, others (e.g. basket-cell innervation) many clustered contacts per target, on specific compartments (soma, proximal dendrite, axon initial segment). | Draws a contact count per synapse from a per (pre type, post type) distribution (`Param`), stored as a per-synapse `contacts` field (weights scale with it); with morphology (N1), assigns `post_node`s on the chosen compartment labels. | K6; N1/N3 for placement |
| C20 | `gap_junction_couple` | Early circuits are coupled by gap junctions before chemical synapses mature; the coupling carries early spontaneous waves. | Creates symmetric electrical couplings between neighbouring cells (radius, probability, conductance, developmental window as `Param`s), stored apart from chemical synapses; `refine_by_activity` and the kernels simulate them. | K5 (kernels), D1 |
| C21 | `transporter_switch` | Chloride transporter switch (NKCC1 to KCC2): GABA / glycine depolarise immature neurons and hyperpolarise mature ones. | Sets each cell's chloride reversal potential (P4 conductance synapses) or its pharmacology context (P3) from its maturation: birth stage, time since birth, or accumulated activity (`Param`s). Extends the existing whole-tissue `immature` / `mature` context of the `pharmacology` stage to a per-cell, gradual switch. | P3, P4 |
| C22 | `competitive_elimination` | Synapse elimination is competitive: an input is removed when competing inputs onto the same target are active and it is not (neuromuscular junction, climbing fibres), not by disuse alone. | From the activity recorded in `refine_by_activity`: for each target, inputs whose activity (or correlation with the target) falls below a fraction of their strongest competitor lose weight or are removed. O(E) grouped by target. Differs from `prune` (absolute weight or coactivity). | C11 |
| C23 | `critical_period_gate` | Critical-period closure: maturation of inhibitory (e.g. parvalbumin-expressing) cells and perineuronal nets stabilise synapses and stop large-scale plasticity. | Sets a per-cell or per-synapse `plastic` mask from a maturation criterion (`Param`s: a cell type's maturity, stage index, a field); `refine_by_activity`, `prune`, `scale` and later structural stages skip masked synapses. | K6, C10, C11 |
| C24 | `tissue_expand` | Tissue grows: proliferation pushes existing cells, layers and tracts outward instead of crowding a fixed box (as in growth simulators such as Cx3D and NeuroDevSim). | Moves cells by a displacement field (radial, anisotropic or a vector `Field`) or by local volume pressure from cell density (cell list), and updates region boxes and geometries. Synapses keep their delays unless asked to recompute them from the new distances (a `Param`). | B1–B5, D1 |

**Contract changes needed (each a dedicated PR with versioned docs, as K1–K4):**
- **K5. Electrical synapses in the kernels.** A per-neuron coupling current `g · (v_j − v_i)` over a symmetric coupling
  list, in all four kernels (Python, JAX, browser, nglif) with equivalence tests, in NGB1 as an extension table, and in
  the cost model. Integer form to be defined (e.g. `(g · (v_j − v_i)) >> shift_g`), deterministic.
- **K6. Optional Tissue fields.** `cycling` (bool, C14), `plastic` (per synapse, C23) and `contacts` (per synapse, int,
  C19), defaulted so that existing code and networks are unchanged; carried by add / compact / subset / concatenate and
  into the network where they matter (contacts as weights, plastic for later plasticity).
  - **Status:** partial: `Tissue.cycling` (bool, per cell; `True` for `seed_cells` / `proliferate`, `False` for
    `place_by_hand`; carried by `add_cells` / `compact` / `subset` / `concatenate` / `to_network` / `from_network`;
    `proliferate` divides only cycling cells) done; `SparseConnectivity.plastic` (bool, per synapse; None = all
    plastic; carried by `take` / `concat` / `append` / `compact` / `subset` / `concatenate` and, in memory only, by
    `to_network` / `from_network`; `refine_by_activity`, `prune`, `scale` and `neuromodulate` leave non-plastic synapses
    untouched) done; `contacts` (C19) done.

**Status of C14–C24:**
| Task | Status |
|---|---|
| C14 | done: `cell_cycle_clock` (#68), Q(generation) as a power law or table, cycle-length table, `Tissue.cycling` (K6 part, #67) |
| C15 | done: `temporal_competence` (#69), one-way competence channels advanced by generation or a field, fixed at cycle exit |
| C21 | done: `transporter_switch` (#74), per-cell chloride reversal potential from maturation (NKCC1 → KCC2 switch) |
| C22 | done: `competitive_elimination` in `neurogenesis/stages/competition.py`, coactivity with the target versus a `fraction` of the strongest competitor, weaken by `delta` or remove; silent targets and non-plastic synapses unchanged; raster from `spikes` or `refine_by_activity` with `record` |
| C23 | done: `critical_period_gate`, sets the K6 `plastic` mask (#73): opens on inhibitory maturity from a source cell type (or a maturity `Param`, or explicitly), closes after a number of gate calls, a maturity threshold or explicitly; `reopen`; mouse / cat ages in `examples/profiles/critical_period_gate.json` |
| C16 | done: `fasciculate` in `neurogenesis/stages/fasciculation.py`, arbor tangent steering via `CellList` & adhesion matrix |
| C17 | done: `choice_point` in `neurogenesis/stages/fasciculation.py`, receptor switch in geometry/field & waypoint routing |
| C19 | partial: `contacts` and weight scaling done; `post_node` placement waits for N2/N3 |
| C24 | done: `tissue_expand` in `neurogenesis/stages/expansion.py`, dilation by `1 + kappa * N_new / N_total` about a centre along chosen axes; optional delay recompute |
| C18, C20 | not done |

**Order and priorities.** C14 → C15 first (they make birth-order-dependent layering emerge in G2.3, instead of being
imposed); C21, C22, C23 next (they use existing P3 / P4 and C11); C18 and C24 independent; C16, C17, C19 after N2 / N3;
C20 deferred (interim approximation below; K5 later).

**Defaults and sources** (from the maintainer's literature review, 2026-11-02; each default is a `Param` that a gene,
field or fit can replace; values are about the cited species and ages, and results are "in this simulation"):

- **C14 `cell_cycle_clock`** — mouse neocortex, neuronogenetic interval E11–E17 (Takahashi, Nowakowski and Caviness
  1995, J Neurosci 15:6046–6057; 1996, J Neurosci 16:6183–6196; Caviness, Takahashi and Nowakowski 2000, in Nelson and
  Luciana, eds., Handbook of Developmental Cognitive Neuroscience, MIT Press, pp. 7–22).
  - 11 integer cycles (CC1–CC11).
  - Cycle length T_C from 8.1 h (CC1, E11) to 18.4 h (CC11); T_G2+M constant at 2 h and T_S about 4 h without a trend;
    the lengthening is almost entirely G1 (3.2 h → 12.4 h, fourfold; Takahashi et al. 1995, Table 1).
  - Leaving fraction `Q(CC) = min(1, k · CC^a)`, defaults `k = 0.009`, `a = 1.97`; P = 1 − Q.
  - Reference table (one founder; `PVE_n = 2 · PVE_(n−1) · P_(n−1)` progenitors, `OUT_n = 2 · PVE_n · Q_n` neurons):

    | CC | age | T_C (h) | T_G1 (h) | Q | PVE | OUT | cumulative |
    |---|---|---|---|---|---|---|---|
    | 1 | E11.0 | 8.1 | 3.2 | 0.009 | 1.00 | 0.02 | 0.02 |
    | 2 | E11.3 | 8.8 | 3.2 | 0.035 | 1.98 | 0.14 | 0.16 |
    | 3 | E11.7 | 9.6 | 3.3 | 0.078 | 3.82 | 0.60 | 0.76 |
    | 4 | E12.1 | 10.3 | 3.5 | 0.138 | 7.05 | 1.95 | 2.70 |
    | 5 | E12.5 | 10.8 | 4.5 | 0.214 | 12.15 | 5.21 | 7.91 |
    | 6 | E13.0 | 11.4 | 5.5 | 0.307 | 19.09 | 11.72 | 19.64 |
    | 7 | E13.5 | 13.1 | 7.3 | 0.416 | 26.46 | 22.01 | 41.65 |
    | 8 | E14.0 | 15.1 | 9.3 | 0.541 | 30.90 | 33.45 | 75.10 |
    | 9 | E14.6 | 16.6 | 10.9 | 0.683 | 28.36 | 38.71 | 113.81 |
    | 10 | E15.3 | 17.8 | 12.0 | 0.840 | 18.01 | 30.25 | 144.06 |
    | 11 | E16.1 | 18.4 | 12.4 | 1.000 | 5.77 | 11.53 | 155.59 |

    Q and the counts follow from the formula (checked here). T_C and T_G1 were measured per embryonic day, E11–E16
    (Takahashi et al. 1995, Table 1: T_C 8.1, 10.2, 11.4, 15.1, 17.5, 18.4 h); the per-cycle values here are read from
    that table by linear interpolation at the start of each cycle, so they are defaults derived from data, not
    measurements. The age column is the age at the start of the cycle; the 11 cycles take 140 h (about 5.8 days).
  - Q passes 0.5 during CC8 (E14), when the progenitor pool peaks (about 31 founders' worth); about 27 % of the
    neurons are made in CC1–CC7. Without cell death a founder yields about 156 neurons; the reported mean of about 140
    corresponds to a basal progenitor death of about 1 % per cycle (the review's figure; 0.99^11 × 156 ≈ 140).
  - Acceptance tests: Q per cycle follows the formula; the first cycle with Q > 0.5 is CC8; the progenitor pool peaks
    at CC8; neurons per founder ≈ 156 with no death and ≈ 140 with 1 % death per cycle (averaged over development
    seeds); division times follow T_C(CC).
  - **Status:** done: `cell_cycle_clock` in `neurogenesis/stages/population.py`, `Tissue.birth_time`, reference profile
    `examples/profiles/cell_cycle_clock.json`, and 25-seed acceptance tests in `tests/test_stages_cell_cycle.py`.
- **C15 `temporal_competence`** — ferret neocortex (McConnell and Kaznowski 1991, Science 254:282–285; McConnell 1995,
  Neuron 15:761–768; for the invertebrate temporal cascade, Isshiki et al. 2001, Cell 106:511–521).
  - Birth order to layer: layer VI E30–E34, layer V E35–E38, layer IV E39–P0, layers II/III P1–P3.
  - Rules the stage must reproduce, from heterochronic transplantation: postmitotic neurons keep their fate; young
    progenitors transplanted in S phase into an old host adopt the host's (later) fate; old progenitors in a young host
    do not regain early fates. Hence: competence moves one way only, it can be advanced by the environment (a `Param`
    field), never reversed, and it is fixed at cell-cycle exit.
  - Acceptance test: the three transplantation outcomes, simulated as moving cells between tissues of different
    competence stages.
  - **Status:** done: `temporal_competence` in `neurogenesis/stages/differentiation.py`, reference profile
    `examples/profiles/temporal_competence.json`, and heterochronic transplantation tests in
    `tests/test_stages_temporal_competence.py`.
- **C19 `cluster_boutons`** — neocortex (cat, rat, macaque, human; DeFelipe 2002; Douglas and Martin 2004 and
  Shepherd and Grillner, eds., 2010, Handbook of Brain Microcircuits; Somogyi et al. 1982, 1983; Peters 1984; Shepherd,
  ed., 2004, The Synaptic Organization of the Brain, ch. 12).
  - Placement (with morphology): pyramidal → pyramidal on distal spines (not soma or axon initial segment); basket-cell
    boutons about one third each on spines, proximal dendritic shafts and soma; chandelier cartridges (up to about 40
    symmetric synapses) only on the axon initial segment; 3–5 chandelier cells per superficial-layer pyramidal axon
    initial segment; one chandelier cell contacts about 300 pyramidal neurons within 200–400 µm.
  - Contacts per connection (multiplicity of a unitary connection, distinct from convergence), defaults as
    distributions per (pre type, post type) `Param`:
    - pyramidal → pyramidal: 3–8 contacts (mean about 5–6; extremes 3–12) on dendritic spines ("3–12 synapses make up
      glutamatergic connections", Markram, DeFelipe and Thomson, in Shepherd and Grillner 2010, ch. 3; paired recordings
      with reconstruction: Markram et al. 1997, J Physiol 500:409–440, layer 5; Feldmeyer et al., layers 2/3 and 4);
    - basket → pyramidal: 5–15 contacts (mean about 10; "about 10 synapses on average with each target", Shepherd 2004,
      ch. 12, p. 520), split about 30 % soma, 35 % proximal dendrites, 35 % spines; convergence of 10–30 basket cells
      per soma is a separate number (it follows from connection probabilities, not from this stage);
    - chandelier → pyramidal: 8–14 contacts per cartridge on the axon initial segment, so that the 3–5 converging
      chandelier cells give the total of about 40 axon-initial-segment synapses of a layer 2/3 pyramidal cell (about
      12–15 for layer 5) (Shepherd 2004, ch. 12, p. 521; Somogyi et al. 1982; Peters 1984).
  - Acceptance tests: contact counts per type pair follow their distributions; with morphology, the compartment
    fractions match; in a layer 2/3 test tissue the total chandelier contacts per axon initial segment is about 40.
- **C21 `transporter_switch`** — rat and mouse (Rivera et al. 1999, Nature 397:251–255; Ben-Ari 2002, Nat Rev Neurosci
  3:728–739; retina: Vu et al. 2000).
  - Immature: high NKCC1, [Cl⁻]i about 25–40 mM, E_Cl about −50 to −40 mV (above a rest of −65 to −70 mV): GABA
    depolarises. Mature: KCC2, [Cl⁻]i about 4–5 mM, E_Cl about −75 mV: GABA hyperpolarises.
  - Timing: NKCC1-dominated from E12 to about P4; functional switch between P5 and P10 (hippocampus and neocortex), up
    to P12–P14 in superficial layers.
  - Mechanism: onset programmed by age, timing accelerated by activity (GABA-driven depolarisation → Ca²⁺ → BDNF /
    TrkB → KCC2). Default rule: E_Cl(cell) moves from E_Cl,immature to E_Cl,mature with the cell's age (a sigmoid with
    midpoint and width as `Param`s), and its accumulated activity shifts the midpoint earlier (gain `Param`, 0 = purely
    programmed).
  - **Status:** done: `transporter_switch` in `neurogenesis/stages/pharmacology.py` (per-synapse `e_rev` from the
    postsynaptic cell's E_Cl; signed weights for `lif_int` with `v_rest`), reference profile
    `examples/profiles/transporter_switch.json`, tests in `tests/test_stages_transporter_switch.py`. Activity is a
    `Param` (`refine_by_activity` does not record per-cell activity yet).
- **C22 `competitive_elimination`** — neonatal rat and mouse neuromuscular junction, P0 (poly-innervated) to P14
  (single input), and climbing fibres on Purkinje cells (P0–P20) (Willshaw 1981, Proc R Soc Lond B 212:401–419; Gouzé,
  Lasry and Changeux 1983, Biol Cybern 46:207–215; Balice-Gordon and Lichtman 1994, Nature 372:519–524).
  - Rule: an input is weakened or removed only when a competing input on the same target drives it above threshold
    while it is inactive or asynchronous; if the target is silent (no suprathreshold activity), nothing is eliminated.
  - Acceptance test: silent target → no elimination; one active input + inactive ones → the inactive ones are removed;
    synchronous inputs → both kept.
- **C23 `critical_period_gate`** — ocular dominance in V1 (Hensch 2005, Nat Rev Neurosci 6:877–888; Pizzorusso et al.
  2002, Science 298:1248–1251; Hubel and Wiesel 1970, J Physiol 206:419–436).
  - Mouse: opens at P19–P21 (about a week after eye opening at P13–P14), peaks at P26–P28, closes P32–P35. Cat: opens
    in weeks 3–4, peaks around week 6, closes by about 3 months.
  - Opening when parvalbumin-cell inhibition reaches a threshold (a `Param` on that type's mean inhibitory weight or
    maturity); closing by perineuronal-net condensation around parvalbumin cells (and myelin-associated factors),
    which the `plastic` mask represents; removing the mask (as chondroitinase ABC does) reopens plasticity.
- **C24 `tissue_expand`** — mouse, CC1–CC8 (E11–E15): ventricular epithelium volume × about 50, surface × about 25
  (about × 5 per tangential dimension) (Caviness, Takahashi and Nowakowski 2000). Growth simulators (Zubler and Douglas
  2009, Front Comput Neurosci 3:25; De Schutter 2023, Front Neuroinform 17:1212384) move cells with overdamped
  mechanics (`γ dx/dt = Σ repulsion + adhesion`, repulsion `k · max(0, R_i + R_j − |x_i − x_j|)`); too costly here.
  Default rule instead: after each proliferation step, dilate positions about a centre (or along chosen axes)
  by `1 + κ · N_new / N_total`, with κ and the axes as `Param`s; the existing `min_distance` collisions of `migrate`
  (cell list) handle local overlaps. Acceptance test: with κ chosen to give × 5 per tangential axis over CC1–CC8, the
  cell density stays bounded while the count grows.
- **C20 `gap_junction_couple`** — deferred. Bidirectional, instantaneous coupling (`I = g (V_i − V_j)`) does not fit
  the kernels' causal, delayed event scheme without an implicit solver or substeps, which would cost an order of
  magnitude and touch all four bit-identical kernels (K5). Interim approximation, no kernel change: reciprocal
  excitatory chemical synapses of delay 0 (first effect after one tick) between neighbouring cells within a
  developmental window. This passes spikes, not subthreshold currents: it can carry early synchronous waves, but it is
  not an electrical synapse, and the docs must say so. K5 stays on the roadmap for later.

### Phase D: performance

**D1. Cell lists / spatial hash.**
- Shared neighbour search: radius queries and k-nearest, in NumPy, with optional JAX.
- **Tests:** exact against brute force on small sets; O(N) scaling measured.
- **Status:** done: `CellList` radius and k-nearest queries, vectorised in NumPy (#45) with chunked memory and a
  declared cost, plus an optional `backend="jax"` path (float64 on the default JAX device, same indices as NumPy,
  distances within floating-point tolerance, plain NumPy arrays returned; no speed-up: about 1000 times slower than
  NumPy on a CPU, GPU not measured; `backend="auto"` keeps NumPy on a CPU and times both once on an accelerator).

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
  - Other agents never edit `desktop/mac/` or `desktop/avalonia/`.
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
- **Status:** done: multi-word spike history ($W = \lceil(\text{max\_delay} + 1) / 32\rceil$ 32-bit words) across Python `reference.py`, JAX `jax_backend.py` & `models/base.py`, browser `viz/src/sim/kernel.ts`, and C `nglif.c`, with memory overhead declared in `neurogenesis.cost`.

**K4b. Longer delays in the developmental stages.** The kernels accept delays beyond 31 ticks (K4), but `grow_axons`,
`connect_by_hand`, `myelinate` and `dendritic_attenuate` still clip computed delays at 31. Replace the hard-coded bound
with the `max_delay` Param (default: no clip, or a documented bound tied to the cost model), warn only when a
user-set bound clips, and test that a long projection keeps its delay and simulates identically in the four kernels.
- **Status:** partial (#72): `grow_axons` (and its streamed variant), `connect_by_hand`, `myelinate`,
  `dendritic_attenuate` and `freeze` use the `max_delay` Param, default the storage bound of 255 ticks
  (`MAX_DELAY_TICKS`), and warn only when clipping. Still clipped at 31: `arbor_synapses`
  (`neurogenesis/stages/arbors.py`) and the connectome importer (`neurogenesis/data/importer.py`).

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
- **Status:** done: affine registration (voxel size, origin, mirroring) and clipped delays; ROI masks and column coordinates interfaced via `Geometry` and `Field` adapters (`neurogenesis.data.registration`), with local tests in PR ([skip ci]).

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
- **Status:** done: `neurogenesis.pharmacology` (profiles, default profile bit-for-bit, `compile_weights`, legacy `receptor_sign` re-expressed), example profile in `examples/profiles/`.

**P2. Receptor expression & assignment.**
- Cell-type-specific or field-dependent receptor expression profiles (`Tissue.receptor_expression`).
- Post-synaptic receptor type assignment during synaptogenesis based on transmitter-receptor compatibility rules.
- **Status:** done: `set_transmitters`, `express_receptors`, `assign_receptors` stages.

**P3. Developmental switches & context compilation.**
- Model developmental shifts in reversal potentials (e.g. GABA depolarizing early $\to$ hyperpolarizing later).
- Compile step maps (transmitter, receptor class, developmental context) into signed integer weight and channel assignment for `lif_int`, or conductance reversal potential for float models.
- Operates both during development (inside C11 `refine_by_activity`) and during network compilation.
- **Status:** done: `pharmacology` stage (`compile_weights` and `compile_conductances`) compiles signed integer weights and conductance reversal potentials / decay time constants per context.

**P4. Multi-channel & conductance-based spiking kernels (post H2, K3, K4).**
- Integer LIF: $k$ synaptic current channels with distinct decay shifts, bit-for-bit equivalent across all four kernels.
- Float models (`two_compartment`, `hh`): conductance-based synapses with reversal potentials, equivalent within floating-point tolerance.
- **Status:** done: multi-channel synaptic currents in `lif_int` and conductance-based reversal potential synapses (`e_rev`, `tau_decay`) in `two_compartment` and `hh`.

**P5. Neuromodulation & volume transmission.**
- Diffuse neuromodulatory fields acting on plasticity eligibility traces (interfacing Phase E `ThreeFactorRule`).
- **Status:** done: `neurogenesis.neuromodulation` (`VolumeModulator`, `apply_modulated_plasticity`, `neuromodulate` stage; every parameter a `Param`, see `docs/STAGES.md`).

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

### Phase J: interoperability, shared metrics, benchmarks and outreach

Goal: make neurogenesis-sim the development front end of the computational-neuroscience ecosystem. Networks grown here
are exported to established simulators and neuromorphic toolchains, and public data (morphologies, gene-expression
atlases, recordings, connectomes) come in as fields, targets and benchmarks. Design rules for every J task:
- **Outside the kernel.** Importers and exporters live in `neurogenesis/interop/` (one module per format) and never
  change development or the integer kernels; determinism and kernel equivalence are untouched.
- **Optional dependencies.** Each format's package is an optional extra (`pip install "neurogenesis-sim[sonata]"`, ...),
  imported lazily, with a clear error naming the extra. CI installs the extras in one job so the tests never skip.
- **Honest mappings.** Every export returns an `ExportReport` listing what is exact, what is approximated (with the
  formula) and what is dropped (e.g. Poisson and burster drivers in formats without them). Formats that can carry
  toolbox-specific attributes (SONATA, NGB1) round-trip losslessly; this is tested.
- **One mapping of the dynamics.** All exporters share one documented translation of the integer LIF into a
  current-based exponential LIF (`neurogenesis/interop/dynamics.py`): `τ = −1 / ln(1 − 2^−shift)` ms (per-tick decay
  matched exactly; `2^shift` overestimates by up to 39 %), `V = E_L + s·v` (default `E_L` −65 mV, `s` = 15/1024 mV,
  so the default threshold is −50 mV), a weight `w` becomes the current jump `W = C_m·s·w·(1 − a)/(4a·τ_syn)`
  (`a = 2^−shift_s`, total charge matched), and a delay of `d` ticks becomes `d + 1` ms (the kernel's extra tick of
  synaptic latency, verified in the tests). Integer rounding, the minimum decrement and the ±2048 clamp are the
  approximation.
- **Licences.** Several target libraries are GPL (navis, NEST), LGPL (libsonata, Norse) or CeCILL (PyNN, Brian 2), and
  the Allen data are non-commercial: optional or test dependencies only, never vendored code or committed data.

**J1. Interop core [contract]. Status: done (`neurogenesis.interop`).** `neurogenesis.interop`: format registry (`register_format`), `export_network(net, fmt,
path, **opts) -> ExportReport`, `import_network(fmt, path) -> SNNNetwork`, `formats()`; `ExportReport` (exact /
approximated / dropped, as JSON); the shared dynamics mapping; CLI `python -m neurogenesis export <network> --format
<fmt> --out <path>` and `python -m neurogenesis import`. Accepts network JSON, NGB1 or an `SNNNetwork`.

**J2. SONATA (input and output). Status: done (`neurogenesis/interop/sonata.py`); BMTK / NEST run pending (J6).** Nodes and edges in HDF5 with node / edge type CSVs and a circuit config (Dai et al.
2020), so BMTK, NEST (via its SONATA reader), NEURON and libsonata tools can read grown circuits. SONATA is the primary export: it is the only target that carries
sparse connectivity, per-synapse delays and extra attributes. Every neuron and synapse field is stored raw (`ngs_*`,
lossless round trip, tested); positions as x, y, z; one population and one attribute group `0` (all libsonata reads);
NEST `iaf_psc_exp` dynamics per node; weights in pA and delays in ms from the shared mapping; edge indices with the
libsonata names (`node_id_to_ranges`). Reader for point-neuron circuits from other tools (inverse mapping). Tested with
libsonata (`node_id_to_ranges` / afferent and efferent edges). Drivers are written as nodes (rates kept); replaying
their spikes as a SONATA spikes input is a follow-up.

**J3. NIR (output, small modules).** The Neuromorphic Intermediate Representation (Pedersen et al. 2024, Nat Commun
15:8122; `pip install nir`): CubaLIF nodes and dense affine / linear weights, for snnTorch, Norse, Lava-DL, SpiNNaker2
and other NIR backends. NIR has no refractory period, no sparse connectivity and no per-synapse delays (its Delay node
is per channel), and its time units are not enforced: suited to small modules only; refractoriness and delays are
reported as approximated, and the time step is written explicitly. Drivers become external inputs or are dropped
(reported).

**J4. PyNN (output).** A self-contained script plus `.npz` arrays: populations of `IF_curr_exp` with the shared
mapping (C_m in nF, weights in nA), positions, `FromListConnector` (pre, post, weight, delay) projections, drivers as
`SpikeSourcePoisson` where possible; runs on PyNN's backends (NEST, NEURON, Brian 2) and SpiNNaker (sPyNNaker).
PyNN can also read SONATA (`pyNN.serialization.import_from_sonata`), which J6 uses as a cross-check.

**J5. NeuroML 2 (output).** `iafRefCell`-type cells, exponential synapses, populations with instance positions,
projections with weights and delays, written with libNeuroML and validated with its validator; for Open Source Brain
and NEURON / NetPyNE import.

**J6. Cross-simulator checks.** For each exporter with a runnable target, simulate reference networks there and in
`lif_int` and compare spike statistics (rates, CV of ISIs, pairwise correlations) with declared tolerances, report only.
Documents how close the exported model is, without claiming equivalence.

**J7. Morphologies in (with N4).** SWC and other skeleton formats through `navis` or `neurom` (no hand-written parser),
into the morphology store of N1, in the frames of I3.

**J8. Gene-expression atlases as fields.** Spatial gene-expression grids (e.g. the Allen Developing Mouse Brain Atlas,
in-situ hybridisation over developmental ages) imported as `GridField`s, registered to a Project's geometry, to drive
`express` / `differentiate` from measured expression (semi-supervised). Dataset manifests in `datasets/` (I1), with
licence and citation.
- **Status:** partial: annotation atlases as geometries (`neurogenesis.data.atlas`: NRRD / MetaImage volumes,
  structure ontologies with descendants, `structure_geometry` → `VoxelMaskGeometry`, `fit_to_box`), used by
  `examples/atlas_relay_mask.py` for the retina → relay example, run on the real P4 annotation of the Allen Developing
  Mouse Brain Atlas (manifest `examples/datasets/allen-devmouse-p4.json`; run 3 of the retina → relay use case, relay
  shaped by p2A because the P4 3D annotation does not delineate the dLGN). Gene-expression grids as fields and
  registration between ages are not done.

**J9. Recordings as fit targets.** Spike data from NWB (pynwb units tables) and neo spike trains, reduced to target
statistics (rates, CV, correlations, PSTHs) for `Fit` Params (E2) and validation (E4).

**J10. Shared connectivity metrics.** One metrics library used by I5, E2 and E4, with the vocabulary of statistical
connectome analysis: distance-dependent connection probability, degree and weight distributions, reciprocity, motif
and directed-simplex counts (Reimann et al. 2019 Nat Commun; Connectome-Manipulator, Pokorny et al. 2025), computed
on grown networks and on imported connectomes alike.

**J11. Public benchmarks.** Two reference problems with data, targets, scripts and a results table: the fly optic-lobe
motion circuit (I6, male CNS and FlyWire connectomes) and a mouse visual-cortex subset (MICrONS). Results are
statistical matches "in this simulation", with the spread between individuals as tolerance.

**J12. Zero-install web demo.** The browser viewer and kernel (Phase F) published with preset projects on the
documentation site, so anyone can grow and simulate a circuit without installing anything.

**J13. Citable releases.** `CITATION.cff`, a Zenodo DOI per tagged release, and a JOSS paper (`paper.md`) once the
repository is public.

### Phase M: functional connectomics, morphometry and continuous morphologies

Full task text: one agent, branch `task/connectomics-morphometry`, one push per working module. Reuse `ArborStore`, `grow_arbors`, `arbor_synapses`, `cluster_boutons`, `refine_by_activity`, `prune`, the fitting metric registry, the connectome catalogue pattern and `neurogenesis.validation`; do not re-implement them.

**M0. Remove the Jules references.** Docs use "agents"; isolation, generic-API and self-contained-test rules live in `AGENTS.md`. **Status:** done.

**M1. Morphometry (`neurogenesis/morphometry/`: `tmd.py`, `features.py`, `metrics.py`).**
- TMD persistence barcodes (Kanari 2018, Neuroinformatics; BlueBrain/TMD; siegert-lab/morphOMICs): filtration = path (or radial) distance from the soma, one (birth, death) pair per terminal branch, vectorised over the `ArborStore`; persistence images; squared Wasserstein (p = 2) with a documented O(n*m) bound and refusal above ~1e6 pairs.
- MorphoPy-style features (berenslab/MorphoPy): per-compartment 3D density, radial and path-distance distributions, branch angle vs somatic distance, laminar stratification profile; fixed-length float32 vectors, O(nodes).
- Fitting metrics `morphology_wasserstein_to_reference` and `laminar_density_profile_ks` (2D Fasano-Franceschini KS on two PCA components; UMAP optional, lazy, not added). SWC adapter `to_swc_bytes` round-tripping through `read_swc`.
- **Status:** partial: TMD barcodes, persistence images, Wasserstein, SWC adapter done (
eurogenesis/morphometry/tmd.py); MorphoPy features and fitting metrics not started.

**M2. Morphology catalogue and continuous latent sampling.**
- `neurogenesis/data/morphology_catalogue.py` mirroring the connectome catalogue (NeuroMorpho.Org, MICrONS manifests, SHA256, licence, no download in tests); manifests in `datasets/morphology/`.
- `neurogenesis/morphometry/latent.py`: descriptor, PCA, per-condition Gaussian with shrinkage covariance, `sample_cells(condition, n, rng)` with Gaussian-kernel weighting (continuum, not stereotypes; Weis, Hansel & Ecker, ssl_neuron). Optional lazy MorphOcc checkpoint adapter (no dependency, nothing bundled).
- Stage `instantiate_morphologies` (`neurogenesis/stages/morphologies.py`): samples morphologies per cell context, attaches ArborStore trees; neutral = no-op; declared cost; `max_nodes`.
- **Status:** not started.

**M3. Functional connectomics metrics and two-phase example.**
- `neurogenesis/metrics/function.py`: `pair_correlations`, `residual_correlations` (distance and RF corrected), `multiplicity_regression` (OLS slope, SE, p; reciprocity per bin), `tuning_metrics` (gOSI, surround suppression); registered as fitting metrics.
- `neurogenesis/metrics/stimuli.py`: deterministic seeded natural-movie-style input currents.
- `examples/cortical_microcircuit.py`: before eye opening, feedforward-driven selectivity with random recurrent L2/3; after, movie stimulation then `refine_by_activity` (STDP), `prune`, `scale`. Like-to-like must emerge, not be imposed (MICrONS, PMC11981947, Nature 640:8058; Ko et al., PubMed 23552948). Acceptance: positive multiplicity slope (P < 0.01), gOSI > 0.25 after pruning.
- **Status:** not started.

**M4. Docs and integration.** `docs/morphometry.md`, `docs/morphology-catalogue.md`, `docs/metrics.md` in the docs index; THIRD_PARTY.md entries (MorphoPy, TMD, morphOMICs, ssl_neuron, MorphOcc, NeuroMorpho.Org, MICrONS, awesome-connectomics); README status table. **Status:** not started.
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
  `examples/evolved_development.py` and `examples/layered_sheet.py` (3, with emergent inside-out layering via C14
  `cell_cycle_clock` -> C15 `temporal_competence` -> `differentiate` -> `migrate`, Spearman $r \ge 0.8$ across 5 seeds),
  `examples/hand_built_network.py` (4), each tested in `tests/test_examples.py`.

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

Second wave of stages:
C2 ─ C14 ─ C15 ─ (G2.3 with emergent layering) ;  P3 + P4 ─ C21 ;  C11 ─ C22 ;  K6 ─ C23, C19 ;  K5 ─ C20 ;
N2 ─ C16, C17 ;  P2 + N3 ─ C18 ;  B + D1 ─ C24

Interoperability:
J1 ─┬─ J2 (SONATA) ─┐
    ├─ J3 (NIR) ────┼─ J6 (cross-simulator checks)
    ├─ J4 (PyNN) ───┤
    └─ J5 (NeuroML) ┘
J10 (metrics) ── I5 / E2 / E4 ;  J7 with N4 ;  J8 after B3 + I1 ;  J9 after E2 ;  J11 after I6 + J10 ;  J12 any time ;
J13 at the public release

G1 any time after A1 ; G2 after the stages it uses ; G3 last
```

**Milestones:**
1. **M1:** A1–A5 and D1 merged; the legacy growth runs as a schedule with identical fingerprints.
2. **M2:** B1–B3, C1–C4, C7, C8 (with D2), C13; example G2.3 runs.
3. **M3:** B4, B5, C5, C6, C9–C12, E1, E2; examples G2.1, G2.2 and G2.4.
4. **M4:** H1–H4 merged; native desktop apps (macOS SwiftUI in `desktop/mac/`, Windows + Linux Avalonia in `desktop/avalonia/`) load a Project, dynamically render schedule and parameter editors from the UI schema, run development through the bridge, and simulate live with `nglif`.
5. **M5:** K1–K4, Phase I (connectome data layer & streaming import), Phase P (pharmacology profiles & multi-channel kernels), Phase N (morphology arbors & SWC import); example I6 (optic lobe column benchmark) runs.
6. **M6:** Re-express legacy growth as real C stages (placement, differentiation, identity, guidance) with fingerprints deliberately regenerated and certified.
7. **M7:** J1–J5 and J10 merged: a grown circuit is exported to SONATA, NIR, PyNN and NeuroML 2 with export reports, and
   its connectivity is described with the shared metrics.
8. **M8:** C14, C15, C21–C23 merged; example G2.3 grows its layers from the cell-cycle clock and temporal competence
   (birth order predicts layer across development seeds), with a GABA polarity switch and competitive refinement.
