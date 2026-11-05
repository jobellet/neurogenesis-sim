# neurogenesis-sim

**Grow spiking neural networks the way nervous systems are built — by hand, by genes, or both — and simulate them
cheaply.**

neurogenesis-sim is a general toolbox for building circuits through development. You describe where tissue is (2D or
3D shapes) and what is already known about it (layers, areas, maps, cell positions). You then choose a sequence of
developmental stages (cell division, migration, differentiation, axon growth, pruning, activity-dependent refinement
...). For every parameter of every stage you decide whether it is set **by hand**, read from a **hand-drawn field**,
controlled by **genes** (and then evolved), or **fitted to data**. The result is a spiking network that can be
simulated, measured, evolved and shared as a module.

```{figure} _static/media/topographic_map_growth.gif
:alt: A sensor sheet growing a topographic projection onto a map
:width: 80%
:class: gif-demo

A sensor sheet → map circuit grown from a genome (see {doc}`use-cases/topographic-map`).
```

| Workflow | What you specify | What development does |
|---|---|---|
| Supervised (by hand) | geometry, cells, connections or connection rules | compiles and simulates exactly what you specified |
| Unsupervised (genetic) | a genome and a schedule of stages | genes control every stage; evolution searches genomes that work for every developmental seed |
| Semi-supervised | a hand-made scaffold (layers, maps, landmarks) plus a schedule | genes and fitted parameters work on top of the scaffold |

## For AI assistants
The whole documentation is also published as one Markdown file, with a generated status section (what exists, what
is not done yet, open pull requests), to paste or upload into a chat with an AI assistant:
[neurogenesis-sim-context.md](https://jobellet.github.io/neurogenesis-sim/neurogenesis-sim-context.md) (about 70k
tokens), or the short [neurogenesis-sim-brief.md](https://jobellet.github.io/neurogenesis-sim/neurogenesis-sim-brief.md)
(about 11k tokens). Both are rebuilt with the site; `python scripts/build_context.py` makes them locally.

## Highlights
- **One integer spiking kernel, four implementations with identical spikes:** Python reference, JAX (CPU / GPU), the
  browser (TypeScript) and a portable C library (`nglif`) used by the desktop apps.
- **Switchable neuron models** on the same grown network: integer LIF, two-compartment, Hodgkin–Huxley.
- **Know the cost before you run:** memory and time per model, calibrated on your machine
  (`python -m neurogenesis estimate`).
- **Development as data:** body plans, genomes, schedules of stages and parameter sources are JSON files.
- **Evolution that generalises across development:** island model with fresh developmental seeds each generation and
  audits on held-out seeds.
- **Modules:** share a working circuit (plan + genome + interface + validation) and compose it with others.
- **Viewers and apps:** a 3D browser viewer, a native macOS app and a Windows / Linux app (in progress).

```{admonition} Project status (November 2026)
:class: warning
The spiking kernels, neuron models, cost estimates, body plans with the fixed growth procedure, genomes, evolution,
modules, the browser viewer and the bridge are tested and usable. Configurable developmental stages, fields,
geometries, fitting, connectome import, pharmacology, arbors and SONATA export work end to end and are tested; the
stages are young and their API may still change (see
{doc}`development/roadmap`).
```

```{toctree}
:maxdepth: 2
:caption: Getting started

getting-started/installation
getting-started/quickstart
getting-started/concepts
```

```{toctree}
:maxdepth: 2
:caption: Tutorials

tutorials/index
```

```{toctree}
:maxdepth: 2
:caption: Use cases

use-cases/index
```

```{toctree}
:maxdepth: 2
:caption: Integration

integration/index
```

```{toctree}
:maxdepth: 2
:caption: Reference

reference/cli
reference/stages
reference/api
reference/project-format
reference/profiles
reference/neuron-models
morphometry
morphology-catalogue
metrics
reference/bridge-protocol
reference/ui-schema
reference/glossary
```

```{toctree}
:maxdepth: 2
:caption: Background

background/design-principles
background/literature
background/developmental-questions
```

```{toctree}
:maxdepth: 1
:caption: Project

development/roadmap
development/contributing
development/agents
development/extending
development/third-party
faq
citing
changelog
```
