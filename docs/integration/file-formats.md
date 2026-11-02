# File formats

| Format | Content | Writer / reader | Spec |
|---|---|---|---|
| Project JSON (+ `.npz` sidecar) | geometry, fields, schedule, genome, plan, plugins, neuron model | `neurogenesis.project.Project` | {doc}`../reference/project-format` |
| Network JSON | neurons and synapses of an `SNNNetwork` | `net.save_json`, `SNNNetwork.load_json` | readable; for small and medium networks |
| NGB1 | binary network: int32 indices, float64 positions, optional extension columns | `neurogenesis.bridge.ngb` | {doc}`../reference/bridge-protocol` (section 6) |
| Module JSON (`neurogenesis-module/1`) | plan, genome, interface, validation, provenance | `Module.save`, `Module.load` | {doc}`../tutorials/modules` |
| Genome JSON | genome with `"src->dst"` projection keys | `neurogenesis.genome.to_json`, `from_json` | {doc}`../getting-started/concepts` |
| CSR arrays | `row_ptr`, `col_idx`, `weights`, `delays` | `net.to_csr()` | kernels |
| SONATA | nodes / edges HDF5, type tables, circuit config, for BMTK, NEST, NEURON, libsonata | `neurogenesis.interop` (`export_network(net, "sonata", dir)`, `import_network`) | {doc}`other-simulators` |
| SWC | neuron morphologies (skeletons) | `neurogenesis.arbors.read_swc`, `write_swc`; connectome skeletons with simplification: `neurogenesis.data.skeletons` | {doc}`../reference/stages` (arbors) |

## Exchanging networks
```python
from neurogenesis.spiking.network import SNNNetwork
net = SNNNetwork.load_json("network.json")
row_ptr, col_idx, weights, delays = net.to_csr()          # NumPy arrays (presynaptic rows)
```
The CSR arrays can be loaded into SciPy (`scipy.sparse.csr_matrix((weights, col_idx, row_ptr))`), NetworkX or any
graph library.

```{admonition} PLACEHOLDER
:class: placeholder
Further formats (roadmap phase J): NIR, PyNN scripts, NeuroML 2 / LEMS (Gleeson et al. 2010), gene-expression atlas
grids as fields, NWB / neo recordings as fitting targets.
```
