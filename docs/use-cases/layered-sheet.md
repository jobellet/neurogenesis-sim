# A layered sheet from progenitors (semi-supervised)

**Idea.** Draw what is known by hand — the sheet, its layer boundaries — and let development do the rest:
progenitors divide, daughters migrate to their layer according to their birth time, differentiate by layer, grow
axons with laminar targeting, and refine connections with spontaneous activity. Genes control the rates, the timing
and the guidance; the scaffold constrains them.

**Stages.** `seed_cells` (in a `Sheet2D` or `CurvedSheet`) → `proliferate` (repeated) → `migrate` (stop at a layer
field) → `differentiate` (types from layer and expression) → `grow_axons` (laminar targeting) →
`refine_by_activity` (spontaneous waves) → `prune`.

**Run the worked example.**
```bash
python examples/layered_sheet.py --cpu --out example_out
```
```text
Layered sheet grown: 120 cells, 618 synapses (580 exc, 38 inh).
Cells per type (0: VZ/deep exc, 1: mid exc, 2: superficial exc, 3: superficial inh): [44, 35, 33, 8]
Birth order vs laminar depth rank correlation: 0.865 (p=4.55e-37)
Connection matrix (pre \ post):
  [153, 59, 7, 2]
  [46, 121, 39, 3]
  [2, 44, 86, 18]
  [1, 16, 17, 4]
Delay distribution: min=1, max=22, mean=7.31
```
This produces `project.json` (Project schema), `network.json` (for the 3D viewer), and `stats.json`.

```{admonition} PLACEHOLDER
:class: placeholder
A quantitative comparison between birth-order rules (inside-out vs outside-in) and animated visualisations of each developmental stage.
```
