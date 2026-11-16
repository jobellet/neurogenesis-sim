# FAQ

**Why an integer neuron model by default?**
Integer arithmetic makes spikes identical across Python, JAX, the browser and C, which makes results reproducible
and lets the apps simulate live with the same kernel. More detailed models (`two_compartment`, `hh`) run on the same
networks when needed.

**Can I model a whole cortical area with Hodgkin–Huxley neurons?**
Ask the estimator first: `python -m neurogenesis estimate --neurons 3e8 --synapses-per-neuron 5000 --model hh`.
On one machine the answer is no (tens of terabytes of synapse memory); the toolbox refuses before trying.

**Is the toolbox specific to one species or brain area?**
No. Region names, cell types, stimuli and tasks belong to your project. Species-specific knowledge (e.g. transmitter
effects) is planned as data profiles outside the core.

**Do evolved circuits explain biology?**
They show what a mechanism can do in the simulation. Statements should be phrased as "in this simulation"; biological
claims need biological evidence.

**How long can delays be?**
Up to 255 ticks (the storage bound of the delay column). The kernels keep a multi-word spike history, (max_delay + 32) // 32
words per neuron (8 words at 255), and give identical spikes in Python, JAX, the browser and `nglif`. Developmental stages
write the distance-derived delay unchanged unless you set a `max_delay` Param, in which case clipped synapses are counted
in a warning.

**How large can networks be?**
The CSR conversion and the browser kernel currently use 16-bit column indices (at most 65,535 neurons); NGB1 and
`nglif` already use 32-bit indices. Lifting the limit everywhere is roadmap task K3.

**My results changed after updating the toolbox.**
Freeze network fingerprints in your project ({doc}`integration/python-dependency`) and pin the toolbox commit.

**How do I check whether a project's parameters come from measurements or assumptions?**
Use parameter profiles ({doc}`reference/profiles`): `python -m neurogenesis profile show <profile>` lists every
parameter with its provenance status (`measured`, `derived`, `assumed`, or `free`) and DOI, `profile check --all`
validates every profile (with `--online` checking DOIs against Crossref), and `profile report project.json`
summarises what a Project depends on.

**Why did `fit` warn that a `Fit` parameter or target is unconstrained?**
Before running CMA-ES, `neurogenesis.fitting.fit` evaluates a local central-difference Jacobian over $\pm 5\%$ of each
`Fit` range across the fitting seeds. It warns if a parameter does not move any target metric or if no parameter moves a
target; inspect `FitResult.identifiability` (`identifiability_report`) to see the scaled Jacobian singular values and
drop unconstrained terms or add sensitive targets.

**How do I run on CPU or GPU?**
Set `JAX_PLATFORMS=cpu` (or pass `--cpu` to example scripts) to force CPU execution without GPU allocation. For CUDA
GPUs, install `pip install -U "jax[cuda12]"` and control GPU memory pre-allocation with
`XLA_PYTHON_CLIENT_MEM_FRACTION` ({doc}`integration/cluster`).

**How do I export a grown network to NEST, NEURON, Brian 2, or neuromorphic tools?**
Use `python -m neurogenesis export network.json --format sonata --out circuit/` for SONATA (read by BMTK, libsonata,
and PyNN) or `--format nir --out circuit.nir` for NIR (snnTorch, Norse, Lava). Both print an `ExportReport` listing
exact, approximated, and dropped attributes ({doc}`integration/other-simulators`).
