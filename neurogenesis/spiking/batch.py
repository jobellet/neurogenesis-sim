"""Batched simulation of many networks with the JAX kernel: each network sees its own sequence of constant stimuli.

Bit-identical to running each network alone with neurogenesis.spiking.jax_backend.tick (padding neurons never spike).
"""
from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np

from . import jax_backend

_JIT = {}


def pad_sizes(nets):
    """Common padded sizes: neurons rounded up to a multiple of 128, synapses to a power of 2 (fewer recompilations),
    Poisson drivers to the largest number in the batch (at least 1)."""
    N = int(np.ceil(max(n.num_neurons for n in nets) / 128) * 128)
    E = int(2 ** np.ceil(np.log2(max(max(n.num_synapses for n in nets), 1))))
    P = max(max(sum(x.mode == 1 for x in n.neurons) for n in nets), 1)
    return N, E, P


def stack(nets):
    """Packed, padded and stacked arrays of a list of networks (leading axis = network)."""
    N, E, P = pad_sizes(nets)
    packs = [jax_backend.pack(n, N, E, P) for n in nets]
    return {k: np.stack([p[k] for p in packs]) for k in packs[0]}, N


def simulate_counts(nets, ext_list, ticks=50, blank=0):
    """Spike counts (S, N_pad) per network for a sequence of S stimuli.

    ext_list[i]: (S, n_i) int32 external currents of network i, one row per stimulus, applied at every tick of the
    stimulus. Each stimulus lasts `ticks` ticks and is preceded by `blank` ticks without input; only stimulus ticks are
    counted. The network state is carried over from one stimulus to the next. Network i uses kernel seed i.
    """
    arr, N = stack(nets)
    ext = np.stack([np.pad(x, ((0, 0), (0, N - x.shape[1]))) for x in ext_list]).astype(np.int32)

    def run(a, ext, seed):
        st = jax_backend.init_state(a, seed)

        def stim(st, e):
            def tick(cc, inp):
                st, tot = cc
                st, spk, _ = jax_backend.tick(a, st, inp[0] * e)
                return (st, tot + spk * inp[1]), None
            on = jnp.concatenate([jnp.zeros(blank, jnp.int32), jnp.ones(ticks, jnp.int32)])
            (st, tot), _ = jax.lax.scan(tick, (st, jnp.zeros(e.shape[0], jnp.int32)), (on, on))
            return st, tot
        return jax.lax.scan(stim, st, ext)[1]
    key = (ticks, blank)
    if key not in _JIT:
        _JIT[key] = jax.jit(jax.vmap(run))
    return np.asarray(_JIT[key](arr, ext, np.arange(len(nets), dtype=np.uint32)))
