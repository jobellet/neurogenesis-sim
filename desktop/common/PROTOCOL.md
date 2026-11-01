# Bridge protocol, version 1.0

The desktop apps drive the toolbox through one server, which ships with the toolbox:

```bash
python -m neurogenesis.bridge
```

The server code is in `neurogenesis/bridge/`, and `tests/test_bridge.py` exercises every method. Run the server with
a Python that has the toolbox installed, or with its checkout first on `PYTHONPATH`.

## 1. Transport
- The client writes requests to the server's **stdin** and reads its messages on **stdout**.
- Every message is one UTF-8 JSON object on one line (`\n` terminated).
- The server's **stderr** carries free-form logs (library prints, tracebacks). Show them in a console, never parse them.
- The server first sends a `ready` event, after its heavy imports (a few seconds). Clients queue their requests until it arrives.
- The server stops when its stdin closes.

## 2. Messages
| Kind | Shape |
|---|---|
| request | `{"id": <int>, "method": "<name>", "params": {...}}`. `params` may be omitted. |
| result | `{"id": <same>, "result": <any JSON>}` |
| error | `{"id": <same>, "error": "<Type>: <message>", "kind": "error" \| "resource", "trace": "<python traceback>"}` |
| event | `{"event": "ready", "data": {"python": "3.12.4", "protocol": "1.0", "ngb": 1}}` or `{"event": "progress", "job": <request id>, "data": {...}}` |

- Ids are chosen by the client and must be unique among pending requests.
- Requests run one at a time, in order. The exception is long jobs (`evolve`), which run beside the others and send
  `progress` events tagged with their request id.
- `kind: "resource"` means the server refused the action before running it, because it would not fit in this
  machine's memory or temporary disk. The message says what it needs and what is free. Show it to the user (the Mac
  app uses an alert). Refusals have no `trace`.
- An unknown method returns an error. Clients must ignore unknown fields and events, so that minor versions stay
  compatible.

## 3. Versions
- **`protocol`.** The version is `MAJOR.MINOR`, in the `ready` event and in `capabilities`. MINOR adds methods or
  optional fields. MAJOR changes or removes them. A client checks MAJOR and warns on a mismatch.
- **`ngb`.** The NGB1 format version (section 6) is an integer.

## 4. Capability discovery
The server reports what the installed toolbox provides, so features merged later appear in the apps without changing
them.
- **`capabilities`** returns `{tasks: [{task, name, available}], python, executable, repo, platform, protocol, ngb}`.
  `task` is a roadmap id ("A4", "C2", …, or "core"). `repo` is where the toolbox is imported from.
- **`stages`** returns `{available, stages: [{name, task, available, doc, params: [{name, default}], has_cost}]}`. This
  is the roadmap's catalogue (C1–C13) merged with the registered stages. `available` at the top is true when the
  scheduler (A4) is present.
- **`models`** returns `{models: [{name, description, substeps, state_bytes, flops}]}`.
- **`rules`** returns `{phase: [rule names]}`.
- **`plasticity_rules`** returns `{available, rules: [{name, params: [{name, default}]}]}`.
- **`geometry_types`** returns `{types: [{type, doc, params: [{name, kind: "vec3" | "float" | "string" | "geometry", default}]}]}`.

## 5. Methods
Networks are passed by NGB1 file path (section 6). Results that contain a network have the form
`{path, neurons, synapses, morphology, regions?}`, where `regions` names the compartment ids of a grown body plan.
Files written by the server live in its temporary directory until it exits.

| Method | Params | Result |
|---|---|---|
| `ping` | – | `"pong"` |
| `capabilities`, `stages`, `models`, `rules`, `plasticity_rules`, `geometry_types` | – | section 4 |
| `resources` | – | `{available, physical, cores, disk_free, fraction}` (bytes) |
| `generate` | `morphology` (column \| layered \| microcircuit), `neurons`, `seed`, preset options | network |
| `load_network` | `path` (network JSON) | network |
| `save_network` | `ngb`, `path`, `morphology?` | `{path}` |
| `wire` | `ngb`, `seed`, `conduction_velocity` | network (rewired by distance) |
| `stats` | `ngb` | topology statistics |
| `plan_defaults` | `plan`, `genome` | `{genome}` completed with neutral genes for every region and projection |
| `estimate_grow` | `plan`, `genome` | `{neurons, synapses, bytes, disk, regions, fits, message, available}` |
| `grow` | `plan`, `genome`, `seed`, `projections?` | network |
| `grow_steps` | `plan`, `genome`, `seed` | `{steps: [network + label], source}`: placement, then one step per projection |
| `plan_load`, `plan_save` | `path` (and `plan`) | `{plan}` / `{path}` |
| `project_new`, `project_load`, `project_save`, `project_validate` | `path`, `project` | `{project}` / `{path}` / `{ok, message}` |
| `geometry_preview` | `geometry`, `n`, `seed` | `{points: [[x, y, z]], lo, hi}`. Empty shapes are refused. |
| `geometry_cells` | `geometry`, `n`, `seed`, `inh_fraction`, `role`, `compartment`, `refractory`, `weight` | network (unconnected) |
| `run_schedule` | `project`, `seed` | `{steps: [network + label], source}`: one checkpoint per stage repetition |
| `schedule_info` | `project`, `N`, `E` | `{genes: [text], gene_list: [{path, lo, hi, integer}], cost: {bytes, ops}}` |
| `simulate` | `ngb`, `model`, `ticks`, `ext: {"index": current}`, `seed` | `{ticks, t: [...], i: [...], model}`: spike times |
| `estimate` | `neurons`, `synapses`, `ticks`, `models?`, `calibrate?` | `{estimates: [{model, memory_bytes, fits, verdict, ...}]}` |
| `fi_curve` | `shift_v`, `shift_s`, `threshold`, `refractory`, `hi`, `step`, `ticks`, `model` | `{currents, rate_hz}` |
| `regularity` | `ngb`, `indices?` (at most 2048) | `{regularity, cells}` |
| `plasticity` | `ngb`, `rule`, `params`, `ticks`, `t`, `i` (recorded spikes) | `{weights: [per synapse], mean_change}` |
| `genes` | `genome` | `{genes: [{path, value}]}`: every number of the genome |
| `evolve` (long) | `plan`, `genome`, `genes: [{path, lo, hi}]`, `target_hz`, `gens`, `pop`, `seeds`, `ticks`, `input_current` | `{history, genome}`, plus a `progress` event per generation |
| `module_load` | `path`, `seed` | `{name, plan, genome, inputs, outputs, description, neuron_model, validation, network}` |
| `module_save` | `name`, `plan`, `genome`, `inputs`, `outputs`, `description`, `neuron_model`, `path` | `{path}` |
| `module_compose` | `paths`, `prefixes?`, `links: [[src, dst, genes?]]`, `offsets?`, `name`, `seed` | `{name, plan, genome, prefixes, network}` |

**JSON conventions.**
- **Genomes** use `neurogenesis.genome.io`: a projection key is `"src->dst"`, and arrays are lists.
- **Schedules** are A4 entries, `{name, operator, params, when?, repeat}`, where each param is an A3 dict
  `{"type": "Const" | "Gene" | "Field" | "Fit" | "Expr", ...}`.
- **Gene paths** are lists of keys, `"src->dst"` projection keys and integer indices, for example
  `["guidance", "a->b", "sigma"]`.

## 6. NGB1 network format (version 1)
NGB1 is little endian, with no padding and no alignment requirement. Writer and reader: `neurogenesis/bridge/ngb.py`.

| Offset | Content |
|---|---|
| 0 | magic `"NGB1"` (4 bytes) |
| 4 | int32 N, the number of neurons |
| 8 | int32 E, the number of synapses |
| 12 | int32 flags, 0 (reserved) |
| 16 | positions: N × 3 float64 (x, y, z, row-major) |
| | directions: N × 3 float64 |
| | 10 int32 columns of N values each, in this order: mode, shift_v, shift_s, base_weight, burst_period, burst_duty, refractory, role, compartment, threshold |
| | 3 float64 columns of N values each: poisson_hz, conn_radius, conn_prob |
| | 4 int32 columns of E values each: pre, post, weight, delay |

- **Size.** The file is exactly `16 + 104 N + 16 E` bytes. Readers reject any other size.
- **Field meanings.** They are those of `neurogenesis.spiking.network.NeuronData` and `SynapseData`. mode: 0 LIF,
  1 Poisson, 2 burster. role: 0 internal, 1 input, 2 output. compartment: −1 means none.
- **Exactness.** Float64 keeps positions and Poisson rates exactly as in Python, so a round trip through NGB1 is
  exact. A kernel that reads NGB1 must compute the Poisson threshold as
  `min(4294967295, trunc(poisson_hz / 1000 × 2³²))`, as `neurogenesis.spiking.reference` does.
- **Future changes.** A new layout gets a new magic (`NGB2`), and readers keep accepting NGB1.
