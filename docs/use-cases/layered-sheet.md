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
Layered sheet grown: 111 cells, 736 synapses.
Cells per layer: [37, 30, 44]
Connection matrix (pre \ post):
  [172, 55, 1]
  [37, 125, 31]
  [2, 71, 242]
Delay distribution: min=1, max=18, mean=6.14
```
This produces `project.json` (Project schema), `network.json` (for the 3D viewer), and `stats.json`.

```{admonition} PLACEHOLDER
:class: placeholder
A quantitative comparison between birth-order rules (inside-out vs outside-in) and animated visualisations of each developmental stage.
```
