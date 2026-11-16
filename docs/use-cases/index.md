# Use cases

| Use case | Workflow | Status |
|---|---|---|
| {doc}`topographic-map` | unsupervised (genes) | runs today (`examples/topographic_map.py`) |
| {doc}`shared-modules` | supervised + genetic, shared as modules | runs today (`Module`, `compose`, `validate_module`) |
| {doc}`layered-sheet` | semi-supervised (hand-made layers + stages) | runs today (`examples/layered_sheet.py`) |
| {doc}`connectome-constrained` | supervised import + semi-supervised fitting to connectome statistics | runs today (`examples/optic_lobe_column.py`) |
| {doc}`developmental-hypotheses` | knockouts, timing changes, activity manipulations | runs today (`knockout`, stage schedules, `pharmacology`) |
| {doc}`retinothalamic` | genes + activity, four conditions with pre-registered hypotheses | runs today (`examples/retinothalamic.py`) |
| {doc}`teaching` | interactive exploration in the browser playground and 3D viewer | available |

```{toctree}
:hidden:

topographic-map
shared-modules
layered-sheet
connectome-constrained
developmental-hypotheses
retinothalamic
teaching
```
