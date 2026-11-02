# Tutorial 8 — Modules: share and compose circuits

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
fraction of held-out seeds that pass. A declarative assay format, re-run by `neurogenesis validate module.json`, is
planned (roadmap task E4).

```{admonition} PLACEHOLDER
:class: placeholder
A module registry (roadmap G1): `neurogenesis install <module>`, semantic versions, compatibility with toolbox
versions, and a browsable gallery of published modules with their validation reports and screenshots.
```

## Versions, registry and validation
`Module` has a semantic `version` and a `toolbox` range. `python -m neurogenesis install module.json` copies it into
the local catalogue, and `neurogenesis.modules.registry.get(name)` loads the latest compatible version. Assays stored
in `validation["assays"]` are rerun by `python -m neurogenesis validate module.json`. See {doc}`fitting-validation`.
