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
| Change transmitter polarity during development | `pharmacology` (`context="immature"` / `"mature"`) and `transporter_switch` stages ({doc}`../reference/stages`) |

A list of well-characterised developmental steps, with the questions the toolbox could address, is in
{doc}`../background/developmental-questions`.

Results are statements about the simulation: "in this simulation, removing X abolishes Y across 95 / 100 seeds", not
claims about the animal.

## Worked knockout study across 50 held-out seeds
Applying targeted single-gene knockouts and `knockout(genome, projections=[("sensor", "map")])` to
`examples/topographic_map.py` across 50 held-out seeds (`1000..1049`) isolates axis-specific guidance cues from
across-seed developmental noise:

```python
import copy
from neurogenesis.development import grow, knockout, region_of

ko_x = copy.deepcopy(base)
ko_x["guidance"][("sensor", "map")]["B"][0, 0] = 0.0          # knock out horizontal chemoaffinity gradient
ko_proj = knockout(base, projections=[("sensor", "map")])       # ablate projection completely (0 synapses)
```

```{figure} ../_static/media/topographic_knockouts.png
:width: 85%

Topographic Pearson correlations $r_x$ and $r_y$ (mean $\pm$ SD and individual seeds) across 50 held-out seeds (`1000..1049`) under wild type (`WT`), single-axis knockouts (`B[0,0]=0`, `B[1,1]=0`), double knockout (`B=0`), and broad arbor (`sigma=0.50`).
```

| Condition (50 seeds, `1000..1049`) | $r_x$ (mean $\pm$ SD) | $r_y$ (mean $\pm$ SD) |
|---|---|---|
| Wild type (`WT`) | `0.961 ± 0.010` | `0.964 ± 0.008` |
| `B[0,0] = 0` (x-cue knockout) | `-0.024 ± 0.159` | `0.971 ± 0.007` |
| `B[1,1] = 0` (y-cue knockout) | `0.971 ± 0.007` | `-0.005 ± 0.152` |
| `B = 0` (double cue knockout) | `0.004 ± 0.174` | `0.002 ± 0.139` |
| `sigma = 0.50` (broad arbor) | `0.959 ± 0.010` | `0.961 ± 0.008` |
| `knockout(..., projections=[("sensor", "map")])` | — (`0` synapses in all 50 seeds) | — (`0` synapses in all 50 seeds) |
