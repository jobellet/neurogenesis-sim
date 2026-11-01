# A layered sheet from progenitors (semi-supervised)

**Idea.** Draw what is known by hand — the sheet, its layer boundaries — and let development do the rest:
progenitors divide, daughters migrate to their layer according to their birth time, differentiate by layer, grow
axons with laminar targeting, and refine connections with spontaneous activity. Genes control the rates, the timing
and the guidance; the scaffold constrains them.

**Stages.** `seed_cells` (in a `Sheet2D` or `CurvedSheet`) → `proliferate` (repeated) → `migrate` (stop at a layer
field) → `differentiate` (types from layer and expression) → `grow_axons` (laminar targeting) →
`refine_by_activity` (spontaneous waves) → `prune`.

```{admonition} PLACEHOLDER
:class: placeholder
Worked example G2.3 of the roadmap (milestone M2): the full Project JSON, a GIF of each stage, layer-wise cell counts
and connection matrices, and a comparison between birth-order rules (inside-out vs outside-in) — once the stage fix
wave (F1–F9) is merged.
```
