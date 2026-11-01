"""The integer leaky integrate-and-fire kernel (neurogenesis.spiking.jax_backend), bit-identical to the reference."""
from __future__ import annotations

from .. import jax_backend

name = "lif_int"
description = ("integer leaky integrate-and-fire: bit-shift leak and synaptic decay, per-neuron threshold, refractory "
               "period; 1 update per 1 ms tick; identical spikes in Python, JAX and the browser")
substeps = 1
state_bytes = 20                    # v, i_syn, spike register, burst phase, refractory counter (int32 each)
flops = 12


def init_state(net, seed=12345):
    return jax_backend.init_state(net, seed)


def tick(net, st, ext):
    return jax_backend.tick(net, st, ext)
