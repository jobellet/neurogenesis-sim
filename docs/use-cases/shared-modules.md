# Building circuits from shared modules

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/use-cases/shared-modules.ipynb)

**Idea.** One group designs or evolves a circuit — for example an early sensory stage whose output cells respond to
increments and decrements of their input (ON / OFF) — validates it, and publishes it as a module. Another group
loads it and connects it to its own circuit, without re-evolving it.

**How.**
1. Plan and assay first (what are the inputs, the outputs, the metric).
2. **Capacity test** with a hand-set genome: can this architecture do the task at all?
3. Evolve from a founding genome that does not contain the hand-set answer.
4. Audit on development seeds never used, including knockouts that biology says must break the function.
5. Save with `Module(..., validation=..., provenance=...)`; publish the JSON and the plugin package.
6. Others `Module.load(...)` and `compose(...)` it ({doc}`../tutorials/modules`), then re-audit the composed system.

Recommended repository layout for a module: see {doc}`../development/extending`.

## Worked example: ON / OFF sensory module composed with a topographic map
Here a 12-channel sensory `Module` splits photoreceptor drive into an excited `on_out` population and a tonically
active `off_out` population suppressed via `receptor="inverting"` (`receptor_sign` rule). Both declarative validation
assays (`validate_module`) pass on `1.0` of seeds `1000..1004`, an `audit` across 10 held-out seeds (`1000..1009`)
confirms opposite step responses (`on_out`: `0.0 → 155.7 → 82.8` Hz; `off_out`: `62.5 → 17.5 → 33.9` Hz across
baseline / step ON / step OFF), and `compose` links `eye.on_out` to `cortex.sensor` of the topographic map:

```python
import numpy as np
from neurogenesis.development import BodyPlan, FixedPlacement, Region
from neurogenesis.modules import Module, compose
from neurogenesis.validation import validate_module

pos_1d = [[(i + 0.5) / 12, 0.5, 0.5] for i in range(12)]
on_off_plan = BodyPlan(
    name="on_off_sensory",
    regions=[
        Region("receptor", (0, 0, 0), (10, 30, 5), FixedPlacement(pos_1d), role=1),
        Region("inter", (15, 0, 0), (10, 30, 5), FixedPlacement(pos_1d), role=0),
        Region("on_out", (30, 0, 0), (10, 30, 5), FixedPlacement(pos_1d), role=2),
        Region("off_out", (30, 10, 0), (10, 30, 5), FixedPlacement(pos_1d), role=2),
    ],
    projections=[("receptor", "on_out"), ("receptor", "inter"), ("inter", "on_out"), ("receptor", "off_out")],
)
on_off_genome = dict(
    count={}, inh_weight_factor=2.0, w_clip=2047,
    inhibitory=dict(receptor=dict(a0=-8.0, a=np.zeros(3)), inter=dict(a0=8.0, a=np.zeros(3)),
                    on_out=dict(a0=-8.0, a=np.zeros(3)), off_out=dict(a0=-8.0, a=np.zeros(3))),
    tonic=dict(off_out=35.0),
    guidance={
        ("receptor", "on_out"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.06, p0=1.0, w=900.0),
        ("receptor", "inter"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.06, p0=1.0, w=900.0),
        ("inter", "on_out"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.08, p0=1.0, w=500.0),
        ("receptor", "off_out"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.06, p0=1.0, w=900.0,
                                      receptor="inverting"),
    },
)
assays = [
    {"name": "on_responds_to_step", "ticks": 80, "blank": 20, "seeds": [1000, 1001, 1002, 1003, 1004],
     "stimuli": [{}, {"receptor": 80}], "readout": {"region": "on_out", "measure": "rate"},
     "metric": "difference", "gate": {"min": 20.0}, "pass_fraction": 1.0},
    {"name": "off_suppressed_by_step", "ticks": 80, "blank": 20, "seeds": [1000, 1001, 1002, 1003, 1004],
     "stimuli": [{}, {"receptor": 80}], "readout": {"region": "off_out", "measure": "rate"},
     "metric": "difference", "gate": {"max": -20.0}, "pass_fraction": 1.0},
]
eye = Module("on_off_sensory", on_off_plan, on_off_genome, inputs=["receptor"], outputs=["on_out", "off_out"],
             validation={"assays": assays})
print(validate_module(eye))

# Compose with the topographic map module from examples/topographic_map.py
brain = compose("sensory+map", {"eye": eye, "cortex": topo_mod}, offsets={"cortex": (60.0, 0.0, 0.0)},
                links=[("eye.on_out", "cortex.sensor", dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.15, p0=0.9, w=800.0))])
net = brain.grow(seed=0)
```

```{figure} ../_static/media/shared_module_composition.png
:width: 96%

Left: ON and OFF population rates across 10 held-out seeds during a step stimulus (`audit` pass fraction `1.00`). Right: spatial response profile in `cortex.map` when stimulating low vs. high channels of `eye.receptor` in the composed `sensory+map` circuit.
```
