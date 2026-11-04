# Command-line reference

## `python -m neurogenesis`

| Command | Purpose | Key options |
|---|---|---|
| `generate` | preset network (column, layered, microcircuit) | `--neurons --morphology --exc-ratio --pace-ratio --radius --height --layers --conduction-velocity --weight-scale --inh-scale --refractory --seed --out` |
| `simulate` | run the integer reference kernel | `--network --ticks --raster --seed` |
| `stats` | topology and degree statistics | `--network` |
| `export-presets` | three preset networks for the viewer | `--out-dir` |
| `estimate` | memory and time per neuron model; with `--project`, of a development schedule stage by stage | `--neurons --synapses-per-neuron --seconds --model (repeatable) --project --no-calibrate` |
| `fit` | fit a Project's `Fit` params to data targets (CMA-ES) | `--project --targets --seeds --iterations --seed --out` |
| `validate` | rerun a module's validation assays (exit 1 on failure) | `module.json --assays` |
| `install` | install a module into the local catalogue | `module.json --catalogue --force` |
| `modules` | list installed modules | `--catalogue` |
| `data info` / `data fetch` | dataset size, license, citation; resumable, checksum-verified download | `dataset --manifest --target --yes` |
| `profile check` / `profile show` / `profile report` | check that every parameter of a profile has a status and a source (exit 1 on failure); list parameters with their status; what a project's parameters rest on (`metadata.profiles`, genes, `Fit`) | `profiles --all --online`, `project` |
| `ui-schema` | export the versioned UI schema JSON for the desktop apps | `--project --calibrated` |
| `export` | write a network (JSON or NGB1) in another format; prints the export report | `network --format {sonata} --out` |
| `import` | read a network from another format into network JSON | `path --format {sonata} --out` |

Every command has `--help`. Worked examples: {doc}`../tutorials/cli`.

## `python -m neurogenesis.bridge`
JSON-lines server for apps and other programs. No options; see {doc}`bridge-protocol`.

## Environment variables
| Variable | Effect |
|---|---|
| `JAX_PLATFORMS=cpu` | force JAX onto the CPU |
| `XLA_PYTHON_CLIENT_MEM_FRACTION` | fraction of GPU memory JAX may take |
| `NEUROGENESIS_CACHE` | calibration cache directory (default `~/.cache/neurogenesis`) |
| `NEUROGENESIS_MODULES` | module catalogue directory (default `~/.cache/neurogenesis/modules`) |
| `NEUROGENESIS_DATA`, `NEUROGENESIS_DATASETS` | dataset cache; extra manifest directory |
| `NEUROGENESIS_PROFILES` | pharmacology profile directory |

```{admonition} PLACEHOLDER
:class: placeholder
Planned: `neurogenesis run`, `neurogenesis stages --json`, `neurogenesis data list`.
```
