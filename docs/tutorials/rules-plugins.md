# Tutorial 7 — Your own rules, stages and models

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/rules-plugins.ipynb)

The toolbox is extended through registries. Your code lives in **your** package (a plugin); projects and modules
list the plugin, and it is imported whenever they are loaded.

## A developmental rule
Rules modify the fixed growth procedure in five phases: `placement`, `shift`, `target`, `probability`, `weight`.

```python
# my_project/rules.py
import numpy as np
from neurogenesis.development import register

@register("weight", "saturating_receptor")
def saturating_receptor(ctx):
    """gd["w_max"]: receptors saturate; weights above w_max are compressed."""
    if "w_max" in ctx.gd:                      # inactive unless its gene is present
        m = ctx.gd["w_max"]
        ctx.w = np.sign(ctx.w) * m * np.tanh(np.abs(ctx.w) / m)
```
```python
plan = BodyPlan(..., plugins=["my_project.rules"])
plan.rules["weight"] += ("saturating_receptor",)
genome["guidance"][("a", "b")]["w_max"] = 300.0
```
Rules must (1) act only when their genes are present, (2) draw no random numbers, (3) be listed in the plan. The
built-in rules are listed in {doc}`../development/extending`.

## A developmental stage
```python
# my_project/stages.py
import numpy as np
from neurogenesis.stages.base import register_stage
from neurogenesis.params import Const, resolve

@register_stage("shrink")
class Shrink:
    """Scales positions towards the origin by `factor` (1 = no change)."""

    def run(self, tissue, params, genome, fields, rng):
        f = resolve(params.get("factor", Const(1.0)), genome, fields, tissue.positions)
        tissue.positions = tissue.positions * f
        return tissue

    @staticmethod
    def cost(N, E, params):
        return 3 * 8 * N, 3 * N          # bytes, operations
```
A stage must: read every parameter through a Param, use only the `rng` it is given, be a no-op with neutral
parameters, declare its cost, and come with a test on a toy tissue (see `AGENTS.md`).

## A neuron model
Register a module with `name`, `description`, `substeps`, `state_bytes`, `flops`, `init_state(net, seed)` and
`tick(net, state, ext)`, using `models.base.drivers` and `models.base.transmit` so that drivers and delays behave as
in every other model:
```python
from neurogenesis.spiking.models import register_model
import my_project.izhikevich as izh
register_model(izh)
```
Details: {doc}`../reference/neuron-models`.

## A geometry or field type
```python
from neurogenesis.geometry import register_geometry
from neurogenesis.geometry.primitives import Geometry

@register_geometry("torus")
class Torus(Geometry):
    ...   # contains, sample, bounding_box, local_coordinates, to_dict, from_dict
```

## Plugin & module repository template
Keep plugins and shareable modules in their own Python package so projects can list them in `plugins` without modifying
the core toolbox (`neurogenesis/`):

```text
my-neurogenesis-plugin/
  pyproject.toml                 # depends on "neurogenesis-sim>=0.1"
  my_plugin/
    __init__.py                  # imports rules, stages, models so listing "my_plugin" registers all of them
    rules.py                     # @register("weight", ...) developmental rules
    stages.py                    # @register_stage(...) stages with Param + cost(N, E, params)
    plan.py                      # body plan / Project + founding_genome() + assay()
  tests/
    test_plugin.py               # determinism, neutral params = no-op, declared cost within 3x, toy behaviour
  .github/workflows/ci.yml       # JAX_PLATFORMS=cpu pytest -q
```

Minimal `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "my-neurogenesis-plugin"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["neurogenesis-sim>=0.1"]
```

Minimal `tests/test_plugin.py` checking the invariants from `AGENTS.md`:

```python
import numpy as np
import my_plugin  # noqa: F401
from neurogenesis.stages.base import STAGE_REGISTRY, run_schedule

def test_shrink_neutral_and_deterministic():
    proj = {"schedule": [{"name": "s", "operator": "seed_cells", "params": {"N": 10, "position": [1, 2, 3]}},
                         {"name": "sh", "operator": "shrink", "params": {}}]}
    t1 = run_schedule(proj, {}, seed=0)
    t2 = run_schedule(proj, {}, seed=0)
    assert np.array_equal(t1.positions, t2.positions)
```

Once a circuit built with your plugin passes validation assays (`python -m neurogenesis validate module.json`), bundle
its project, genome, targets, and cost estimate into a catalogue card with
`python -m neurogenesis share --project project.json --orcid ... --author ...` ({doc}`../catalogue`).
