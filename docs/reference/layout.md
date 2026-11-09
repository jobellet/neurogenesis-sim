# Package layout: grow, simulate, measure

The toolbox has three kinds of code. Keep them apart: a new piece of code goes with its kind, so that whoever looks for
"how do I measure X" or "how do I grow Y" finds everything in one place.

| Kind | What it does | Where | Examples |
|---|---|---|---|
| **Development** | builds or changes a tissue / network from genes, rules and data | `neurogenesis.stages`, `neurogenesis.development`, `neurogenesis.tissue`, `neurogenesis.genome`, `neurogenesis.params`, `neurogenesis.geometry`, `neurogenesis.fields`, `neurogenesis.arbors`, `neurogenesis.pharmacology`, `neurogenesis.streaming` | `proliferate`, `express`, `connect_by_hand`, `scale`, body plans |
| **Simulation** | runs a network in time and returns its activity | `neurogenesis.spiking` (kernels, neuron models, plasticity, batched runs) | `jax_backend`, `reference`, `numba_backend`, `batch.simulate_counts` |
| **Analysis** | measures a tissue, a network or recorded activity; never changes them | `neurogenesis.analysis` | `structure.modularity`, `criticality.summary`, `cells.fi_curve` |

Evolution (`neurogenesis.evolution`), fitting, cost estimates, validation, modules and the bridge use the three kinds
and sit beside them.

## Analysis (`neurogenesis.analysis`)
One module per kind of measure:

| Module | Measures | Input |
|---|---|---|
| `cells` | single-cell responses: frequency-current curve from rest (`fi_curve`) | neuron parameters |
| `structure` | anatomy and wiring: mosaic regularity (`nearest_neighbour_regularity`), synapse lengths (`connection_lengths`), fraction of synapses inside groups such as clones (`within_group_fraction`), modularity Q of a partition (`modularity`, Leicht & Newman 2008) | positions, `pre` / `post` arrays, labels |
| `criticality` | population dynamics: branching parameter by multistep regression (`branching_mr`, Wilting & Priesemann 2018), avalanches and their size / duration exponents (`avalanches`, `powerlaw_fit`, `powerlaw_fit_xmin`, Clauset et al. 2009), the crackling scaling relation (`crackling`), all at once (`summary`), and a driven branching process with known m for testing (`branching_process`) | spike counts per tick |
| `connectome` | statistical connectome measures (J10) on the binary directed graph: in / out degrees and their skewness (`degrees`, `degree_stats`), weight distributions with log-normal parameters (`weight_stats`), the 16-class triad census (`triad_census`, Holland & Leinhardt 1976), reciprocity with its over-representation and the Pearson r between A_ij and A_ji (`reciprocity`), connection probability by distance (`distance_dependent_probability`, cell list) and by number of common neighbours (`common_neighbour_probability`, Perin et al. 2011), directed simplex counts (`directed_simplices`, Reimann et al. 2017), all at once (`summary`) | `pre` / `post` arrays, number of cells, positions |
| `morphology` | arbor morphometry (N6): morphometrics per cell (`morphometrics`: branch points, tips, stems, lengths, extents, branch order, tortuosity, branch angles; MorphoPy feature set, Laturnus et al. 2020), branch order (`branch_order`), Sholl profiles (`sholl`), topological morphology descriptor barcodes (`tmd_barcodes`, Kanari et al. 2018), persistence images and their distance (`persistence_image`, `barcode_distance`, Adams et al. 2017), barcode time series during growth (`snapshot`, `temporal_barcodes`, `barcode_series_distance`) | `ArborStore`; history from `grow_arbors` |
| `geometry` | geometry of representations and connectivity: cross-validated PCA of two repeats (`cvpca`, Stringer et al. 2019: reliable variance per dimension, reliable fraction, dimension), participation ratio of a spectrum (`participation_ratio`), dimensionality of a weight matrix (`connectivity_dimensionality`) | responses (stimuli x neurons) in two repeats; `pre` / `post` / weights |

The common names are importable from the package itself (`from neurogenesis.analysis import fi_curve, modularity`);
older imports (`from neurogenesis.analysis import fi_curve, nearest_neighbour_regularity`) keep working.

Rules for a new measure:
- **Where.** In the module of its kind; a new module in `neurogenesis/analysis/` for a new kind (for example
  `information` for entropies and decoding, `spectral` for power spectra), listed here and in the API page.
- **What it takes.** Plain arrays (positions, `pre` / `post`, labels, spike counts or rasters) or a `Tissue` /
  `SNNNetwork`. It must not modify them, simulate for its own sake (except single-cell measures such as `fi_curve`) or
  draw global random numbers.
- **Cost.** NumPy, O(N + E) or O(T); a dense N × N computation only below a stated size.
- **Tests.** A known answer (a synthetic process or graph whose value is known, such as a branching process of given
  m or two disconnected modules), degenerate inputs (empty, constant), and the failure mode the measure is known for.
- **Docs.** A row in the table above and in the API page; the source of the method in the docstring.

## Simulation backends (`neurogenesis.spiking`)
| Backend | Runs on | Cost per tick | Notes |
|---|---|---|---|
| `reference` | Python | O(N + E) | the specification; slow |
| `jax_backend` | CPU or GPU, batched with `vmap` | O(N + E) | the main kernel; all neuron models through `batch` |
| `numba_backend` | CPU (optional: `pip install "neurogenesis-sim[fast]"`) | O(N + spikes x out-degree) | event-driven, fast for sparse activity on a laptop; `lif_int` with single-channel synapses; optional forced inputs, short-term depression, threshold homeostasis (off by default, not in the other kernels) |
| `nglif` (C), browser | native apps, viewer | O(N + E) | shared contract with the apps |

All of them give the same `lif_int` spikes, per neuron and tick (`tests/test_kernel.py`, `tests/test_numba_backend.py`,
the `nglif` fixtures).
