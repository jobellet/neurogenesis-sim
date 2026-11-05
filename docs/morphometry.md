# Morphometry

`neurogenesis.morphometry` measures arbor shape on an `ArborStore` with vectorised NumPy, O(nodes) time and memory.

## Topological morphology descriptor (TMD)

Kanari et al. (2018, Neuroinformatics; BlueBrain/TMD; population statistics: siegert-lab/morphOMICs). A filtration
`f(v)` (path distance from the soma, or Euclidean radial distance) is evaluated on every node. At each bifurcation the
subtree reaching the farthest tip continues the bar of its parent; each other child subtree is a terminal branch that
yields one bar `(birth, death)` = (`f` at the bifurcation, `f` at the farthest tip). Each tree adds one bar from its
root (`f = 0`) to its farthest tip. Bars are invariant to rotation and translation.

```python
from neurogenesis.morphometry import barcodes, persistence_images, wasserstein_squared
bars = barcodes(store, filtration="path", compartments=["dendrite"])   # cell, birth, death
img = persistence_images(bars, n_cells=N, grid=20, bounds=(0, 500))     # (N, 400) float32
d2 = wasserstein_squared(bars.of_cell(0), bars.of_cell(1))
```

- `persistence_images`: Gaussian-smoothed 2D histogram over (birth, death) on a fixed grid, one fixed-length vector per
  cell.
- `wasserstein_squared`: exact squared 2-Wasserstein distance between two diagrams, bars may match the diagonal.
  O(n·m) memory; calls with n·m above `MAX_WASSERSTEIN_PAIRS` (10^6) are refused with a warning, counted in
  `WASSERSTEIN_REFUSALS`, and return NaN.
- `to_swc_bytes(store, cells)`: in-memory SWC for MorphoPy and TMD; `read_swc` reads SWC back.
- `barcodes_cost(n_nodes)`: declared (bytes, operations).
