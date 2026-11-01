# UI schema, version 1.0

The UI schema is a JSON document that tells the desktop apps what the installed toolbox offers. It covers
developmental stages and their parameters, neuron models and their costs, development rules, the genes of a
schedule, and the Project schema version.

The apps build their editors from it. Nothing about an individual stage, Param, model, rule or gene is coded into an
app; app code is only layout, look and interaction. The macOS, Windows and Linux apps therefore show the same panels,
and a stage merged into the toolbox appears in all three without changing them.

| | |
|---|---|
| Format owner | desktop apps (this file). Changes need a PR that keeps all three apps working. |
| Exporter | `python -m neurogenesis ui-schema` (roadmap task H3), and the bridge method `ui_schema` |
| Machine-checkable form | `ui_schema.schema.json` (JSON Schema 2020-12) |
| Complete example | `ui_schema.example.json`; `tests/test_ui_schema.py` validates it against the schema |

## 1. Versioning
- `"format": "neurogenesis-ui-schema"` and `"version": "MAJOR.MINOR"`.
- A MINOR bump adds optional fields or new enum values. Apps ignore fields they do not know. Apps show an item with
  an unknown `type` or `cost` form as read-only JSON, never as an error.
- A MAJOR bump renames, removes or changes the meaning of a field. Apps refuse a MAJOR version they do not know and
  tell the user to update.

## 2. Document
```json
{
  "format": "neurogenesis-ui-schema",
  "version": "1.0",
  "generated_by": {"toolbox": "0.1.0", "python": "3.12.15", "date": "2026-11-01T18:00:00Z"},
  "project_schema_version": "1.0.0",
  "param_sources": [...],
  "stages": [...],
  "models": [...],
  "rule_phases": [...],
  "rules": [...],
  "schedule_genes": [...]
}
```
Every top-level key is required. A list may be empty: for example, `stages` before any stage is registered.

### 2.1 `param_sources`: where a parameter's value comes from (A3)
Each entry has these fields:

| Field | Meaning |
|---|---|
| `type` | `"Const"`, `"Gene"`, `"Field"`, `"Fit"` or `"Expr"`. These are the `type` values of A3 param dicts. |
| `title` | Short label. |
| `doc` | One or two sentences. |
| `inputs` | The fields to edit for this source, each `{name, type, doc}`. For example, Gene has `path` (a gene path), `lo`, `hi` and `integer`. |

Apps render the source switch and its inputs from this list. When a source has an input of an unknown type, apps edit
that input as raw JSON.

### 2.2 `stages`: registered stages (A4) and planned ones
Each stage has these fields:

| Field | Meaning |
|---|---|
| `operator` | Registry name, used in schedule entries (`{"operator": ...}`). |
| `title`, `description` | Label and help text. `description` is the first paragraph of the stage's docstring. |
| `task` | Roadmap id (`"C2"`), or `"plugin"` for a stage that comes from a plugin. |
| `available` | False for planned stages that are not registered yet. Apps show them but cannot run them. |
| `params` | A list of Param specs (2.3), in display order. |
| `cost` | `null` if the stage declares no cost. Otherwise `{"declared": true, "samples": [{"N", "E", "bytes", "ops"}]}`: the stage's `cost(N, E, defaults)` evaluated at the exporter's reference sizes, so apps can show how the stage scales. Exact costs for a real schedule come from the bridge (`schedule_info`). |
| `repeatable` | The stage accepts `repeat` greater than 1. |
| `conditional` | The stage accepts a `when` condition. |

### 2.3 Param spec
| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Key in the schedule entry's `params`. |
| `title` | yes | Label. |
| `doc` | yes | Help text, shown by the (?) button: what the parameter is and what it changes. |
| `type` | yes | The value's type: `float`, `int`, `bool`, `string`, `choice`, `vec3`, `geometry` (name of a project geometry), `field` (name of a project field), `gene_path`, `json`. |
| `default` | yes | An A3 param dict, e.g. `{"type": "Const", "value": 0.1}`, as a new schedule entry stores it. |
| `sources` | yes | Allowed `param_sources` types, e.g. `["Const", "Gene", "Field"]`. |
| `units` | no | E.g. `"per tick"`, `"space units"`, `"ms"`. Empty or absent means dimensionless. |
| `min`, `max` | no | Bounds of the value (inclusive). They also bound Gene `lo` / `hi` and Fit `init`. |
| `step` | no | Increment for steppers and sliders. |
| `choices` | for `choice` | `[{"value", "title"}]` |
| `per_cell` | no | True if the parameter can vary across cells (sources `Field` and `Expr` resolve per cell). |
| `advanced` | no | Shown collapsed by default. |

**Widgets by type.** The apps choose widgets from the type, never from the name:

| `type` | Widget |
|---|---|
| `float`, `int` | Number field. A slider is added when both bounds are finite. |
| `bool` | Toggle. |
| `string` | Text field. |
| `choice` | Picker. |
| `vec3` | Three number fields, x / y / z. |
| `geometry` | Picker over the project's geometry names. |
| `field` | Picker over the project's field names. |
| `gene_path` | Gene path editor. |
| `json` | JSON editor. |
| anything else | Read-only JSON. |

Every widget has a label (`title`) and a (?) help (`doc`, with `units` and the bounds).

### 2.4 `models`: neuron models and their costs
Each model has these fields:

| Field | Meaning |
|---|---|
| `name`, `title`, `description` | Identity and help text. |
| `substeps` | Updates per 1 ms tick. |
| `state_bytes` | Per neuron. |
| `flops` | Per neuron and substep. |
| `cost` | `{"bytes_per_neuron", "bytes_per_synapse", "seconds_per_neuron_substep", "seconds_per_synapse_tick", "seconds_per_tick_overhead", "device"}`. The `seconds_*` fields and `device` come from `neurogenesis.cost` calibration and are `null` when this machine is not calibrated. |
| `native` | True when the apps can run the model live (`lif_int`, through `nglif`); otherwise it runs through the bridge's `simulate`. |

### 2.5 `rule_phases` and `rules`: development rules (`neurogenesis.development.rules`)
- `rule_phases` lists every phase, in order: `[{"name": "placement", "title", "doc"}, ...]`.
- `rules` lists every rule, as `[{"phase", "name", "doc", "genes": [gene path patterns that activate it], "default": bool}]`.
  `default` is true when the rule is in the default plan rules.

### 2.6 `schedule_genes`: the genes a schedule uses (A3 `collect_genes`)
Each gene is `{"path", "lo", "hi", "integer", "used_by": [{"stage", "param"}]}`. Its path is a gene path (2.7).

The list is empty in a document exported without a project. With a project (`ui-schema --project p.json`, or the
bridge method `ui_schema` with `project`), it lists the genes of that project's schedule. The Evolution panel offers
exactly these genes.

### 2.7 Gene paths
A gene path is a JSON list of keys. `"src->dst"` stands for a projection key (a tuple in Python), and integers index
arrays. For example, `["guidance", "sensor->map", "B", 0, 1]`. The same convention is used in PROTOCOL.md.

## 3. Obtaining it
- `python -m neurogenesis ui-schema [--project p.json] [--calibrated]` writes the document to stdout (H3).
- Bridge method `ui_schema`, with params `{project?}`, returns the same document. Apps call it after `ready`, and
  again after the user refreshes the toolbox.
- Until H3 is merged, apps may render `ui_schema.example.json` to develop and test their panels. They mark
  `available: false` stages as not runnable.
