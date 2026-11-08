# neurogenesis-sim

**A collaborative discovery platform to grow, perturb, and evolve spiking neural circuits.**

```python
from neurogenesis.data import register_target
from neurogenesis.development import BodyPlan, Region, grow
from neurogenesis.fitting import evolve_circuit
from neurogenesis.modules import share

# 1. Define Target: evolvable objective with non-spiking or dynamic readout
@register_target(name="alpha_sync")
def target_alpha_sync(activity):
    return score_alpha_oscillation(activity, target_freq=10.0, e_i_ratio=4.0)

# 2. Grow & Perturb: biological schedule with gene and drug parameters
plan = BodyPlan(name="cortex", regions=[Region("sheet", size=(40, 40, 5))])
net = grow(plan, founding_genome, pharmacology={"GABA_antagonist": 0.2})

# 3. Evolve & Share: optimize genome + pharmacology, export catalogue card
evolved_genome, best_score = evolve_circuit(plan, target="alpha_sync", generations=20)
share(plan, evolved_genome, target="alpha_sync", author="Bellet et al.", doi="10.1101/...")
```

<div class="circuit-preview-grid" style="display: flex; gap: 20px; margin: 24px 0; flex-wrap: wrap;">
  <div style="flex: 1; min-width: 280px; border: 1px solid #e1e4e8; border-radius: 8px; padding: 14px; background: #fafbfc;">
    <h4 style="margin-top: 0; color: #d73a49; font-weight: 600;">Baseline / Disordered Circuit</h4>
    <img src="_static/media/viewer_raster.png" alt="Baseline asynchronous circuit" style="width: 100%; border-radius: 4px; border: 1px solid #e1e4e8;" />
    <p style="font-size: 0.9em; color: #586069; margin-top: 10px; margin-bottom: 0;">
      <strong>Pre-optimization:</strong> Asynchronous irregular firing; unaligned synaptic projections.
    </p>
  </div>
  <div style="flex: 1; min-width: 280px; border: 1px solid #e1e4e8; border-radius: 8px; padding: 14px; background: #fafbfc;">
    <h4 style="margin-top: 0; color: #28a745; font-weight: 600;">Evolved Synchronous Circuit</h4>
    <img src="_static/media/topographic_map_growth.gif" alt="Evolved topographic synchronous circuit" style="width: 100%; border-radius: 4px; border: 1px solid #e1e4e8;" />
    <p style="font-size: 0.9em; color: #586069; margin-top: 10px; margin-bottom: 0;">
      <strong>Post-optimization:</strong> Emergence of 10 Hz synchronous oscillations and balanced E/I ratio ($R \ge 65\%$).
    </p>
  </div>
</div>

neurogenesis-sim is a general toolbox for building circuits through development. You describe where tissue is (2D or
3D shapes) and what is already known about it (layers, areas, maps, cell positions). You then choose a sequence of
developmental stages (cell division, migration, differentiation, axon growth, pruning, activity-dependent refinement
...). For every parameter of every stage you decide whether it is set **by hand**, read from a **hand-drawn field**,
controlled by **genes** (and then evolved), or **fitted to data**. The result is a spiking network that can be
simulated, measured, evolved and shared as a module.

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
:caption: Discovery Catalogue

catalogue
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

reference/layout
reference/cli
reference/stages
reference/api
reference/project-format
reference/profiles
reference/neuron-models
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
