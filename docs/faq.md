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
The four kernels keep a spike history of as many 32-bit words as the longest delay needs (roadmap task K4), so
networks can carry any delay. The developmental stages that compute delays (`grow_axons`, `myelinate`,
`connect_by_hand`, dendritic delays) still clip them at 31 ticks with a warning; lifting that is an open task.

**How large can networks be?**
Neuron indices are 32-bit everywhere and synapses are stored as arrays (roadmap task K3), so the limit is memory:
ask `python -m neurogenesis estimate` before running. Very large networks are saved as NGB1 or `.npz`, not JSON.

**My results changed after updating the toolbox.**
Freeze network fingerprints in your project ({doc}`integration/python-dependency`) and pin the toolbox commit.

```{admonition} PLACEHOLDER
:class: placeholder
Questions collected from users once the repository is public.
```
