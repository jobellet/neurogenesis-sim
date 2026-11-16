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
| NIR | Neuromorphic Intermediate Representation HDF5 graph (`CubaLIF` + `Linear`) | `neurogenesis.interop` (`export_network(net, "nir", path)`, `import_network`) | {doc}`other-simulators` |
| SWC | neuron morphologies (skeletons) | `neurogenesis.arbors.read_swc`, `write_swc`; connectome skeletons with simplification: `neurogenesis.data.skeletons` | {doc}`../reference/stages` (arbors) |
| Voxel masks & atlas volumes | `.npz` boolean occupancy masks (`mask`, `origin`, `voxel_size` / `affine`); `.nrrd` / `.mhd` annotation volumes | `VoxelMaskGeometry.from_npz`, `neurogenesis.data.atlas` | {doc}`../reference/stages` (geometry) |
| Dataset manifests & profiles | connectome table specs (`datasets/<id>.json`) and provenance-tracked parameter profiles (`profiles/*.json`) | `neurogenesis.data.catalogue`, `neurogenesis.profiles` | {doc}`../tutorials/connectome-data`, {doc}`../reference/profiles` |
| Circuit card (`neurogenesis-card/1`) | validated project, genome, targets, compute cost, and provenance bundle | `python -m neurogenesis share` | {doc}`../catalogue` |

## Exchanging networks
```python
from neurogenesis.spiking.network import SNNNetwork
net = SNNNetwork.load_json("network.json")
row_ptr, col_idx, weights, delays = net.to_csr()          # NumPy arrays (presynaptic rows)
```
The CSR arrays can be loaded into SciPy (`scipy.sparse.csr_matrix((weights, col_idx, row_ptr))`), NetworkX or any
graph library.

## NIR graphs and atlas voxel masks
Export an integer LIF network to NIR (for snnTorch, Norse, or Lava; requires `pip install "neurogenesis-sim[nir]"`):

```python
from neurogenesis.interop import export_network, import_network

report = export_network(net, "nir", "circuit.nir")
print(report)                         # exact / approximated / dropped attributes
net_roundtrip = import_network("nir", "circuit.nir")
```

Turn a labelled volumetric atlas (`.nrrd`, `.mhd`, or `.npz`) and structure ontology JSON into a `VoxelMaskGeometry`
for seeding or constraining regions:

```python
from neurogenesis.data.atlas import Ontology, fit_to_box, read_volume, structure_geometry

vol, origin, spacing = read_volume("annotation.nrrd")
onto = Ontology.load("structures.json")
geom = fit_to_box(structure_geometry(vol, onto, ["LGd"], origin, spacing), center=[50, 50, 50], extent=40.0)
geom.save_npz("relay_mask.npz")       # referenced in Project geometry as {"type": "voxel_mask", "npz": "relay_mask.npz"}
```
