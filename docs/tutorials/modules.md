# Tutorial 8 — Modules: share and compose circuits

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/modules.ipynb)

A **module** is what one person designs or evolves and another reuses as-is: a body plan, a genome, an interface
(input and output regions), validation records, provenance and the neuron model it was validated with.

## Save
```python
from neurogenesis.modules import Module

m = Module("topographic map", plan, genome,
           inputs=["sensor"], outputs=["map"],
           description="sensor sheet -> topographic map; input: constant current 120 on sensor cells",
           validation={"seeds": [0, 1, 2], "metric": "topographic precision", "pass_fraction": 1.0},
           provenance={"authors": ["..."], "repository": "...", "commit": "..."},
           neuron_model="lif_int")
m.save("topographic_map.module.json")
```

## Load and grow
```python
m = Module.load("topographic_map.module.json")   # its plugins are imported, its genes kept
net = m.grow(seed=3)
```

## Compose
```python
from neurogenesis.modules import compose
eye = Module.load("eye.module.json")
circuit = Module.load("circuit.module.json")
system = compose("eye+circuit", {"eye": eye, "circuit": circuit},
                 links=[("eye.output", "circuit.input",
                         dict(B=np.eye(3), c=np.zeros(3), sigma=0.2, p0=0.5, w=200.0))])
net = system.grow(seed=0)
```
- Region names get the module prefix (`eye.output`); each module keeps its own genes and plugin rules.
- Links add projections with their own guidance genes, which can themselves be evolved.
- **Re-audit the composed system**: a module validated alone may behave differently once connected.

## Validation records
Write in `validation` how the module was tested: stimuli, readout, metric, the development seeds used, and the
fraction of held-out seeds that pass. Declarative assays stored in `validation["assays"]` are rerun automatically by
`python -m neurogenesis validate module.json` (see {doc}`fitting-validation`).

## Versions, registry and validation
`Module` has a semantic `version` and a `toolbox` range (for example `">=0.1, <0.2"`). Install a validated module into
the local catalogue (`$NEUROGENESIS_MODULES`, default `~/.cache/neurogenesis/modules`), inspect it, and retrieve the
latest compatible version from Python:

```bash
python -m neurogenesis validate topographic_map.module.json
python -m neurogenesis install topographic_map.module.json
python -m neurogenesis modules
```

```python
from neurogenesis.modules.registry import get

m = get("topographic map")                  # latest version compatible with this toolbox
```

To publish a validated circuit as a catalogue card (`neurogenesis-card/1`) with compute-cost telemetry and author
provenance for the {doc}`../catalogue`, run:

```bash
python -m neurogenesis share --project project.json --genome genome.json \
  --orcid 0000-0002-1825-0097 --author "A. Researcher" --out topographic_map.card.json
```

For a full worked example building, auditing, and composing an ON / OFF sensory module with the topographic map, see
{doc}`../use-cases/shared-modules`.
