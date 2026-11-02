# Command-line reference

## `python -m neurogenesis`

| Command | Purpose | Key options |
|---|---|---|
| `generate` | preset network (column, layered, microcircuit) | `--neurons --morphology --exc-ratio --pace-ratio --radius --height --layers --conduction-velocity --weight-scale --inh-scale --refractory --seed --out` |
| `simulate` | run the integer reference kernel | `--network --ticks --raster --seed` |
| `stats` | topology and degree statistics | `--network` |
| `export-presets` | three preset networks for the viewer | `--out-dir` |
| `estimate` | memory and time per neuron model | `--neurons --synapses-per-neuron --seconds --model (repeatable)` |

Every command has `--help`. Worked examples: {doc}`../tutorials/cli`.

## `python -m neurogenesis.bridge`
JSON-lines server for apps and other programs. No options; see {doc}`bridge-protocol`.

## Environment variables
| Variable | Effect |
|---|---|
| `JAX_PLATFORMS=cpu` | force JAX onto the CPU |
| `XLA_PYTHON_CLIENT_MEM_FRACTION` | fraction of GPU memory JAX may take |

```{admonition} PLACEHOLDER
:class: placeholder
Planned: `neurogenesis run`, `neurogenesis stages --json`, `neurogenesis ui-schema`, `neurogenesis validate`,
`neurogenesis install`, `neurogenesis data list|info|fetch`.
```
