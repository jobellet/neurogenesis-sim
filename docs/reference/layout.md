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
