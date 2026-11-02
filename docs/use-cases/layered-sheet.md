# A layered sheet from progenitors (semi-supervised)

**Idea.** Draw what is known by hand — the sheet, its layer boundaries — and let development do the rest:
progenitors advance through cell cycles and exit (`cell_cycle_clock`), progressively restrict their laminar competence
(`temporal_competence`), differentiate from their competence at cycle exit (`differentiate`), migrate to the target
layer of their cell type (`migrate`), grow axons with laminar targeting (`grow_axons`), and refine connections with
spontaneous activity (`refine_by_activity` → `prune`). Genes control the rates, the timing and the guidance; the
scaffold constrains them.

**Stages.** `seed_cells` (in a `Sheet2D` or `CurvedSheet`) → `cell_cycle_clock` (C14) → `temporal_competence` (C15) →
`proliferate` (C2, repeated across 3 cycles) → `differentiate` (C7, cell types from competence at cycle exit) →
`migrate` (C4, stop at the target layer of each cell's type in a `LayerStackField`) → `grow_axons` (C8, laminar
targeting) → `refine_by_activity` (C11, STDP) → `prune` (C10).

**Run the worked example.**
```bash
python examples/layered_sheet.py --cpu --out example_out
```
```text
Layered sheet grown: 112 cells, 686 synapses (587 exc, 99 inh).
Cells per type (0: deep exc, 1: mid exc, 2: superficial exc, 3: superficial inh): [22, 22, 51, 17]
Birth cycle vs laminar depth rank correlation: 0.872 (p=3.41e-78)
Connection matrix (pre \ post):
  [48, 30, 4, 1]
  [21, 47, 35, 9]
  [5, 45, 274, 68]
  [1, 11, 69, 18]
Delay distribution: min=1, max=20, mean=6.79
```
This produces `project.json` (Project schema), `network.json` (for the 3D viewer), and `stats.json`.

## Quantitative comparison of birth-order rules (in this simulation)

| Rule | Target layer formula (`migrate`) | Spearman rank correlation $r(\text{generation}, z)$ (seed 42) | 5-seed range (`[42, 101, 7, 1234, 999]`) |
|---|---|---|---|
| Inside-out (later-born cells migrate to more superficial layers) | `np.minimum(cell_type, 2) * layer_scale` | `+0.872` ($p = 3.41 \times 10^{-78}$) | `+0.872` to `+0.909` (mean `+0.890`) |
| Outside-in (later-born cells remain in deeper layers) | `(2 - np.minimum(cell_type, 2)) * layer_scale` | `-0.872` ($p = 3.41 \times 10^{-78}$) | `-0.909` to `-0.872` (mean `-0.890`) |
