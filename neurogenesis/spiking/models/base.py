"""Neuron models: a common interface over one shared transmission layer.

Every model simulates the same grown network (neurogenesis.spiking.network.SNNNetwork, packed by jax_backend.pack):
the same synapses, axonal delays (a 32-tick spike shift register) and driver neurons (Poisson drivers drawn with the same
xorshift32 generator, intrinsic bursters on the same schedule). Models differ in how a neuron integrates its inputs
between spikes. One tick is 1 ms; float models subdivide it into `substeps`.

A model provides
  name, description, substeps (per 1 ms tick), state_bytes (per neuron), flops (per neuron and substep, approximate),
  init_state(net, seed) -> state, tick(net, state, ext) -> (state, spikes (N,) uint8, arrivals (E,) int32).
ext (N,) int32 is the external current in the integer units of the toolbox (see each model's mapping to physical units).
"""
from __future__ import annotations

import jax
import jax.numpy as jnp

from ..jax_backend import U32, _xorshift

RHEOBASE_UNITS = 8.5          # external current (toolbox units) at which the integer LIF neuron starts firing (fi_curve)


def drivers(net, rng, phase):
    """Forced spikes of driver neurons, exactly as in the integer kernel: Poisson drivers (mode 1), one xorshift32 draw per
    Poisson neuron in index order; intrinsic bursters (mode 2), every 4th tick of the first `duty` ticks of each period."""
    P = net["pois_idx"].shape[-1]

    def draw(x, k):
        x2 = jnp.where(k < net["n_pois"], _xorshift(x), x)
        return x2, x2
    rng, draws = jax.lax.scan(draw, rng, jnp.arange(P))
    fire_p = (net["pois_idx"] >= 0) & (draws < net["poisson_thresh"][jnp.maximum(net["pois_idx"], 0)])
    pois = jnp.zeros(net["mode"].shape, bool).at[jnp.maximum(net["pois_idx"], 0)].max(fire_p) & (net["mode"] == 1)
    period = jnp.where(net["burst_period"] == 0, 200, net["burst_period"])
    duty = jnp.where(net["burst_duty"] == 0, 24, net["burst_duty"])
    is_b = net["mode"] == 2
    phase = jnp.where(is_b, (phase + 1) % period, phase)
    burst = is_b & (phase < duty) & ((phase & 3) == 0)
    return pois | burst, rng, phase


def transmit(net, bits, spiked):
    """Shift the spike register and return (bits, arrivals): arrivals[e] = 1 when the presynaptic spike of synapse e,
    emitted `delay` ticks ago, reaches it now."""
    if bits.ndim == 1:
        bits = (bits << U32(1)) | spiked.astype(U32)
        arrivals = ((bits[net["pre"]] >> net["delay"].astype(U32)) & U32(1)).astype(jnp.int32) * net["valid"]
    else:
        W = bits.shape[-1]
        words = [(bits[:, 0] << U32(1)) | spiked.astype(U32)]
        for w in range(1, W):
            words.append((bits[:, w] << U32(1)) | (bits[:, w - 1] >> U32(31)))
        bits = jnp.stack(words, axis=-1)
        delay_word = net["delay"] >> 5
        delay_bit = net["delay"] & 31
        pre_bits = bits[net["pre"]]
        selected_word = jnp.take_along_axis(pre_bits, delay_word[:, None].astype(jnp.int32), axis=1).squeeze(axis=1)
        arrivals = ((selected_word >> delay_bit.astype(U32)) & U32(1)).astype(jnp.int32) * net["valid"]
    return bits, arrivals
