"""Hodgkin-Huxley point neuron (squid giant axon, Hodgkin & Huxley 1952; modern sign convention, rest near -65 mV).

    C dV/dt = -gNa m^3 h (V - ENa) - gK n^4 (V - EK) - gL (V - EL) + I_ext + I_syn
Gates by exponential Euler (exact for frozen voltage), voltage by forward Euler, dt = 0.025 ms (40 substeps per 1 ms
tick). A spike is an upward crossing of 0 mV within the tick. The neuron's own channels set its threshold and
refractoriness: the grown threshold and refractory fields are not used (drivers are, as in every model).
Synaptic current: exponential, time constant 2^shift_s ms. Mapping of toolbox current units: I = SCALE x units, SCALE
chosen so that the onset of repetitive firing (about 6.3 uA/cm2 for these parameters) matches the integer LIF rheobase
(8.5 units); a synaptic weight w delivers the charge of SCALE x w over 1 ms.
"""
from __future__ import annotations

import jax.numpy as jnp

from .base import RHEOBASE_UNITS, drivers, transmit

name = "hh"
description = "Hodgkin-Huxley point neuron (Na, K, leak); 40 substeps of 0.025 ms per 1 ms tick"
substeps = 40
state_bytes = 36                    # V, m, h, n, I_syn, spike register, burst phase, previous-V flag, rng share
flops = 90                          # 6 exponentials and about 40 arithmetic operations per substep
G_NA, G_K, G_L, E_NA, E_K, E_L, DT = 120.0, 36.0, 0.3, 50.0, -77.0, -54.387, 0.025
SCALE = 6.3 / RHEOBASE_UNITS


def _vtrap(x, y):
    """x / (exp(x / y) - 1), finite at x = 0."""
    return jnp.where(jnp.abs(x / y) < 1e-6, y * (1 - x / y / 2), x / (jnp.exp(x / y) - 1))


def _rates(v):
    am = 0.1 * _vtrap(-(v + 40.0), 10.0)
    bm = 4.0 * jnp.exp(-(v + 65.0) / 18.0)
    ah = 0.07 * jnp.exp(-(v + 65.0) / 20.0)
    bh = 1.0 / (1.0 + jnp.exp(-(v + 35.0) / 10.0))
    an = 0.01 * _vtrap(-(v + 55.0), 10.0)
    bn = 0.125 * jnp.exp(-(v + 65.0) / 80.0)
    return am, bm, ah, bh, an, bn


def init_state(net, seed=12345):
    import numpy as np
    N = np.shape(net["mode"])[-1]
    v0 = jnp.full(N, -65.0, jnp.float32)
    am, bm, ah, bh, an, bn = _rates(v0)
    bits = jnp.zeros_like(net["bits0"], dtype=jnp.uint32) if "bits0" in net else jnp.zeros(N, jnp.uint32)
    return dict(v=v0, m=am / (am + bm), h=ah / (ah + bh), n=an / (an + bn), i_syn=jnp.zeros(N, jnp.float32),
                refr=jnp.zeros(N, jnp.int32), bits=bits, phase=jnp.zeros(N, jnp.int32),
                rng=jnp.asarray(seed, jnp.uint32))


def tick(net, st, ext):
    net = {k: jnp.asarray(x) for k, x in net.items()}
    tau_s = 2.0 ** net["shift_s"].astype(jnp.float32)
    i_ext = SCALE * ext.astype(jnp.float32)
    v, m, h, n, isyn = st["v"], st["m"], st["h"], st["n"], st["i_syn"]
    decay = jnp.exp(-DT / tau_s)
    crossed = jnp.zeros(v.shape, bool)
    for _ in range(substeps):
        am, bm, ah, bh, an, bn = _rates(v)
        m = am / (am + bm) + (m - am / (am + bm)) * jnp.exp(-DT * (am + bm))
        h = ah / (ah + bh) + (h - ah / (ah + bh)) * jnp.exp(-DT * (ah + bh))
        n = an / (an + bn) + (n - an / (an + bn)) * jnp.exp(-DT * (an + bn))
        i_ion = G_NA * m ** 3 * h * (v - E_NA) + G_K * n ** 4 * (v - E_K) + G_L * (v - E_L)
        v_new = v + DT * (-i_ion + i_ext + isyn)
        crossed = crossed | ((v < 0.0) & (v_new >= 0.0))
        v = v_new
        isyn = isyn * decay
    forced, rng, phase = drivers(net, st["rng"], st["phase"])
    in_refr = st["refr"] > 0
    spiked = crossed | (forced & ~in_refr)
    refr = jnp.where(in_refr, st["refr"] - 1, jnp.where(forced & ~in_refr, net["refractory"], 0))   # drivers only
    bits, arrivals = transmit(net, st["bits"], spiked)
    isyn = isyn.at[net["post"]].add(arrivals.astype(jnp.float32) * net["weight"].astype(jnp.float32) * SCALE / tau_s[net["post"]])
    return dict(v=v, m=m, h=h, n=n, i_syn=isyn, refr=refr, bits=bits, phase=phase, rng=rng), spiked.astype(jnp.uint8), arrivals
