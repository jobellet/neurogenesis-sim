# Extending neurogenesis-sim and building module projects

## 1. Where new biology goes
| You want to model... | Mechanism | Where |
|---|---|---|
| A new cell population | a `Region` in your plan (fixed placement or grown) | your project |
| Where neurons end up (mosaics, layering, sorting) | a **placement** rule: moves a region's local positions after migration, before signs are drawn | `@register("placement", name)` |
| A new axon-guidance molecule | a **shift** / **target** / **probability** rule: changes where axons aim or the chance of a synapse | `@register(phase, name)` |
| How a receptor transforms a synapse (sign, gain, saturation) | a **weight** rule: modifies the new synapses' weights before rounding and clipping | `@register("weight", name)` |
| A standing current of a cell type (e.g. depolarised at rest) | `genome["tonic"][region]`; add `tonic_current(net, plan, genome)` to the stimulus currents | built in |
| A knockout or an ablation | `knockout(genome, regions=[...], projections=[...])` | built in |

A rule receives a context (`PlacementContext`, `GuidanceContext` or `WeightContext`) and modifies it. Rules must:
1. **read genes and act only when they are present**, so that adding a rule to a plan changes no existing network;
2. **draw no random numbers** (development must stay reproducible for a given seed);
3. **be listed in the plan**, `plan.rules[phase]`. The order in the list is the order of application.

```python
# my_project/rules.py
import numpy as np
from neurogenesis.development import register

@register("weight", "saturating_receptor")
def saturating_receptor(ctx):
    """gd["w_max"]: receptors saturate; weights above w_max are compressed."""
    if "w_max" in ctx.gd:
        m = ctx.gd["w_max"]
        ctx.w = np.sign(ctx.w) * m * np.tanh(np.abs(ctx.w) / m)
```
Then, in the plan:
```python
plan = BodyPlan(..., plugins=["my_project.rules"])
plan.rules["weight"] += ("saturating_receptor",)
```

`plugins` are Python modules imported whenever the plan is built or loaded. A saved module therefore brings its rules
along, provided the plugin package is installed.

Built-in rules, each inactive unless its gene is present:

| Phase | Rule | Genes |
|---|---|---|
| placement | `mosaic` | `genome["mosaic"][region] = {spacing, iters}` |
| shift | `identity_offset` | `guidance[p]["type_c"]` with `genome["identity"][region]` |
| target | `topographic` | `guidance[p]["topographic"] = [1, 1, 0]` |
| target | `lamina` | `guidance[p]["lamina"]` |
| target | `expression_gradient` | `guidance[p]["expression_gradient"] = [{"gene": "EphA", "axis": 0, "gain": 2, "sign": "attract", "normalize": "minmax"}, ...]` (or `{"genes": [...], "mode": "replace" / "modulate"}`); reads `Tissue.expression` columns named by `express(names=...)`; a missing gene or no expression raises `ValueError` |
| probability | `identity_expression` | `guidance[p]["type_s"]` |
| probability | `no_autapse` | always active |
| probability | `source_sign` | `guidance[p]["source"] = "exc" / "inh"` |
| weight | `receptor_sign` | `guidance[p]["receptor"] = "inverting"` |

In a Project, the `grow_axons` stage takes these genes from its `guidance` param, keyed `"src->dst"` (or a list of
`{"src", "dst", ...}`); any value may be a `Gene` read from the genome, e.g.
`"guidance": {"0->1": {"sigma": 0.3, "p0": 0.9, "w": {"type": "Gene", "path": ["axon", "w"], "lo": 10, "hi": 100}}}`.
It does not read `genome["guidance"]`. A listed projection without guidance, or no `projections`/`guidance` at all,
raises ValueError; `"projections": []` is the no-op.

## 2. A module project, step by step
Recommended layout (one repository per module or family of modules):
```
my-module/
  my_module/plan.py        # make_plan(), founding_genome(), handset_genome(); region names are yours
  my_module/assay.py       # stimuli -> external currents; responses -> metrics; the gate of one individual
  my_module/rules.py       # optional plugin rules
  scripts/capacity.py      # hand-set genome: can this architecture do the task at all?
  scripts/evolve.py        # islands (neurogenesis.evolution.evolve) from the founding genome
  scripts/audit.py         # held-out development seeds, knockouts, writes the module JSON
  docs/HYPOTHESES.md       # dated plans, declared before each run, and dated results
  tests/
```
**Order of work:**
1. **Plan and assay first.**
2. **Capacity test** with a hand-set genome. If the architecture cannot do the task, no search will find it.
3. **Evolve** from a founding genome that does not contain the hand-set answer.
4. **Audit** on development seeds never used, including the knockouts that biology says must break the function.
5. **Save** with `Module(..., validation=..., provenance=...)`.

## 3. Using someone else's module
```python
from neurogenesis.modules import Module, compose
retina = Module.load("retina.module.json")             # its plugins are imported, its genes kept
mine = Module.load("my_circuit.module.json")
brain = compose("eye+circuit", {"retina": retina, "circuit": mine},
                links=[("retina.ganglion_on", "circuit.input", dict(B=..., c=..., sigma=0.2, p0=0.5, w=200.0))])
net = brain.grow(seed=0)
```
- **Inputs and outputs** keep their meaning, with the prefix ("retina.photoreceptor").
- **The input coding** (which current means which stimulus) is described in the module's `description` and `validation`.
- **Re-audit the composed system:** a module validated alone may behave differently once connected.
