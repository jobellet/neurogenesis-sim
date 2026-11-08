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

```{admonition} PLACEHOLDER
:class: placeholder
A worked example module (an ON / OFF sensory stage) with its capacity test, evolution logs, audit report and
screenshots, published in its own repository and composed with the topographic-map example.
```
