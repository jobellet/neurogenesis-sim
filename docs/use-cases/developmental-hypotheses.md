# Testing developmental hypotheses

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/use-cases/developmental-hypotheses.ipynb)

Because development is explicit and seeded, one can ask "what if" questions and test them across many developmental
seeds:

| Manipulation | How |
|---|---|
| Remove a cell population or a projection | `knockout(genome, regions=[...], projections=[...])` |
| Remove a guidance cue | delete or neutralise its gene; rules are inactive without their genes |
| Change the timing of a stage | reorder the schedule, change `repeat` or `when` |
| Block spontaneous activity | remove or silence the `refine_by_activity` stage |
| Change a cell type's resting state | `genome["tonic"][region]` (standing currents) |
| Change transmitter polarity during development | planned (phase P: stage-dependent pharmacology) |

A list of well-characterised developmental steps, with the questions the toolbox could address, is in
{doc}`../background/developmental-questions`.

Results are statements about the simulation: "in this simulation, removing X abolishes Y across 95 / 100 seeds", not
claims about the animal.

```{admonition} PLACEHOLDER
:class: placeholder
A worked knockout study on the topographic-map example (which genes are necessary for topography, measured across
held-out seeds), with figures.
```
