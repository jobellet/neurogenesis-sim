"""Single-cell measures: responses of one neuron type, simulated in isolation."""
from __future__ import annotations

import numpy as np


def fi_curve(currents, shift_v=5, shift_s=4, threshold=1024, refractory=3, ticks=1000, model="lif_int"):
    """Firing probability per tick of one isolated neuron for each constant external current (added every tick), each
    current applied to a fresh copy of the neuron starting from rest (models with bistability, such as Hodgkin-Huxley,
    would otherwise depend on the order of the currents): the frequency-current curve of a cell type."""
    from ..spiking.batch import simulate_counts
    from ..spiking.network import NeuronData, SNNNetwork
    cur = np.asarray(currents, np.int32)
    nets = [SNNNetwork(neurons=[NeuronData(id=0, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, shift_v=shift_v,
                                           shift_s=shift_s, base_weight=1, conn_radius=0.0, conn_prob=0.0, refractory=refractory,
                                           threshold=threshold)], synapses=[]) for _ in cur]
    counts = simulate_counts(nets, [np.asarray([[c]], np.int32) for c in cur], ticks=ticks, model=model)
    return counts[:, 0, 0] / ticks


_SCANS = {}


def spike_raster(net, model="lif_int", ext=None, ticks=None, n_substeps=None, seed=12345):
    """(ticks, N) uint8 spikes of `net` under a neuron model, from rest, for any input over time.

    ext: (N,) int32 current added every tick, or (ticks, N) one row per tick (pulses, ramps, steps). `n_substeps`
    changes the substeps of a float model (`step_convergence`). The kernel seed is `seed`.
    """
    import jax
    import jax.numpy as jnp
    from ..spiking.jax_backend import pack
    from ..spiking.models import get_model
    mdl = get_model(model)
    arr = pack(net)
    ext = jnp.zeros(net.num_neurons, jnp.int32) if ext is None else jnp.asarray(ext, jnp.int32)
    if ext.ndim == 2 and ext.shape[1] < arr["mode"].shape[-1]:
        ext = jnp.pad(ext, ((0, 0), (0, arr["mode"].shape[-1] - ext.shape[1])))
    elif ext.ndim == 1 and ext.shape[0] < arr["mode"].shape[-1]:
        ext = jnp.pad(ext, (0, arr["mode"].shape[-1] - ext.shape[0]))
    inputs = ext if ext.ndim == 2 else jnp.broadcast_to(ext, (int(ticks),) + ext.shape)
    key = (model, n_substeps)
    if key not in _SCANS:
        kw = {} if n_substeps is None else {"n_substeps": n_substeps}

        def run(arr, st, inputs):
            def step(st, e):
                st, spk, _ = mdl.tick(arr, st, e, **kw)
                return st, spk
            return jax.lax.scan(step, st, inputs)[1]
        _SCANS[key] = jax.jit(run)
    spikes = _SCANS[key](arr, mdl.init_state(arr, seed), inputs)
    return np.asarray(spikes)[:, :net.num_neurons]


_raster = spike_raster


def step_convergence(net, model, ext, ticks=500, factor=2, seed=12345):
    """Step-halving check of a float neuron model on a network: runs it with the model's substeps and with `factor`
    times as many, and compares the spikes. Fixed-step integration can move spike times and change network synchrony
    (Hansel et al. 1998, Neural Comput; Brette et al. 2007, J Comput Neurosci); if a smaller step changes little, the
    step is small enough. `lif_int` is defined on the 1 ms tick and has no smaller step.

    ext: (N,) int32 current added every tick, or (ticks, N). Returns dict: `spikes` and `spikes_fine` (totals),
    `rate_change` (absolute difference of the totals / max(total, 1)), `matched` (fraction of spikes of the normal run that the finer run
    has in the same neuron within +-1 tick), `max_count_change` (largest per-neuron change of the spike count).
    Neither the network nor `ext` is changed.
    """
    from ..spiking.models import get_model
    mdl = get_model(model)
    if model == "lif_int":
        raise ValueError("step_convergence: lif_int is defined on the 1 ms tick; there is no smaller step to compare")
    a = spike_raster(net, model, ext, ticks, mdl.substeps, seed)
    b = spike_raster(net, model, ext, ticks, mdl.substeps * int(factor), seed)
    near = b.astype(bool).copy()
    near[1:] |= b[:-1].astype(bool)
    near[:-1] |= b[1:].astype(bool)
    total = int(a.sum())
    matched = float((a.astype(bool) & near).sum() / total) if total else 1.0
    return dict(spikes=total, spikes_fine=int(b.sum()), rate_change=abs(int(b.sum()) - total) / max(total, 1),
                matched=matched, max_count_change=int(np.max(np.abs(a.sum(0).astype(int) - b.sum(0).astype(int)), initial=0)))
