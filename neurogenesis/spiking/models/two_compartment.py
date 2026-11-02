"""Two-compartment integrate-and-fire neuron (soma + dendrite): an intermediate level between point neurons and
Hodgkin-Huxley models.

    C dVs/dt = -gL (Vs - EL) - gc (Vs - Vd) + I_ext + I_inh          (soma: external input, perisomatic inhibition)
    C dVd/dt = -gL (Vd - EL) - gc (Vd - Vs) + I_exc                  (dendrite: excitatory synapses)
Spike when Vs >= theta, then Vs = V_reset for the neuron's refractory period. Units: mV, ms, uA/cm2, uF/cm2 (C = 1).
Per neuron, from the grown network: membrane time constant 2^shift_v ms (gL = C / tau), synaptic time constant
2^shift_s ms, threshold theta = EL + 15 mV x threshold / 1024, refractory period in ticks. Coupling gc = 0.5 gL.
Mapping of toolbox current units: I = SCALE x units, SCALE chosen so that the somatic rheobase of the default neuron
equals the integer LIF rheobase (8.5 units); a synaptic weight w delivers the charge of SCALE x w over 1 ms.
Euler integration, dt = 0.25 ms.
"""
from __future__ import annotations

import jax.numpy as jnp

from .base import RHEOBASE_UNITS, drivers, transmit

name = "two_compartment"
description = "two-compartment (soma + dendrite) integrate-and-fire; 4 Euler substeps per 1 ms tick"
substeps = 4
state_bytes = 32                    # Vs, Vd, I_exc, I_inh, refractory, spike register, burst phase, rng share (32-bit)
flops = 22
EL, V_RESET, DT = -65.0, -70.0, 0.25
_g_eff_default = (1 / 32) * (1 + 0.5 / 1.5)                     # gL + gc gL / (gL + gc) with gc = 0.5 gL, tau 32 ms
SCALE = 15.0 * _g_eff_default / RHEOBASE_UNITS                  # uA/cm2 per toolbox current unit


def init_state(net, seed=12345):
    import numpy as np
    N = np.shape(net["mode"])[-1]
    f = jnp.zeros(N, jnp.float32)
    bits = jnp.zeros_like(net["bits0"], dtype=jnp.uint32) if "bits0" in net else jnp.zeros(N, jnp.uint32)
    st = dict(vs=f + EL, vd=f + EL, i_exc=f, i_inh=f, refr=jnp.zeros(N, jnp.int32),
              bits=bits, phase=jnp.zeros(N, jnp.int32), rng=jnp.asarray(seed, jnp.uint32))
    if "e_rev" in net:
        st["g_exc"] = f
        st["g_inh"] = f
        st["g_exc_rev"] = f
        st["g_inh_rev"] = f
    return st


def tick(net, st, ext):
    net = {k: jnp.asarray(x) for k, x in net.items()}
    gl = 1.0 / (2.0 ** net["shift_v"].astype(jnp.float32))
    gc = 0.5 * gl
    tau_s = 2.0 ** net["shift_s"].astype(jnp.float32)
    theta = EL + 15.0 * net["threshold"].astype(jnp.float32) / 1024.0
    i_ext = SCALE * ext.astype(jnp.float32)
    vs, vd, ie, ii = st["vs"], st["vd"], st["i_exc"], st["i_inh"]
    in_refr = st["refr"] > 0
    crossed = jnp.zeros(vs.shape, bool)
    decay = jnp.exp(-DT / tau_s)
    cond_mode = "e_rev" in net
    if cond_mode:
        ge = st["g_exc"]
        gi = st["g_inh"]
        gerev = st["g_exc_rev"]
        girev = st["g_inh_rev"]
    for _ in range(substeps):
        dvs = -gl * (vs - EL) - gc * (vs - vd) + i_ext + ii
        dvd = -gl * (vd - EL) - gc * (vd - vs) + ie
        if cond_mode:
            vs_next = (vs + DT * (dvs + girev)) / (1.0 + DT * gi)
            vd_next = (vd + DT * (dvd + gerev)) / (1.0 + DT * ge)
            vs = jnp.where(in_refr, V_RESET, vs_next)
            vd = vd_next
        else:
            vs = jnp.where(in_refr, V_RESET, vs + DT * dvs)
            vd = vd + DT * dvd
        crossed = crossed | ((vs >= theta) & ~in_refr)
        vs = jnp.where(crossed, V_RESET, vs)
        ie, ii = ie * decay, ii * decay
        if cond_mode:
            ge, gi = ge * decay, gi * decay
            gerev, girev = gerev * decay, girev * decay
    forced, rng, phase = drivers(net, st["rng"], st["phase"])
    spiked = crossed | (forced & ~in_refr)
    refr = jnp.where(in_refr, st["refr"] - 1, jnp.where(spiked, net["refractory"], 0))
    bits, arrivals = transmit(net, st["bits"], spiked)
    q = arrivals.astype(jnp.float32) * net["weight"].astype(jnp.float32) * SCALE / tau_s[net["post"]]
    if cond_mode:
        is_cond = ~jnp.isnan(net["e_rev"])
        q_curr = jnp.where(is_cond, 0.0, q)
        ie = ie.at[net["post"]].add(jnp.maximum(q_curr, 0.0))
        ii = ii.at[net["post"]].add(jnp.minimum(q_curr, 0.0))
        g_inc = jnp.where(is_cond, jnp.abs(q), 0.0)
        e_rev = jnp.where(is_cond, net["e_rev"], 0.0)
        is_exc = jnp.where(is_cond, e_rev >= EL, net["weight"] >= 0)
        g_exc_inc = jnp.where(is_exc, g_inc, 0.0)
        g_inh_inc = jnp.where(is_exc, 0.0, g_inc)
        ge = ge.at[net["post"]].add(g_exc_inc)
        gerev = gerev.at[net["post"]].add(g_exc_inc * e_rev)
        gi = gi.at[net["post"]].add(g_inh_inc)
        girev = girev.at[net["post"]].add(g_inh_inc * e_rev)
    else:
        ie = ie.at[net["post"]].add(jnp.maximum(q, 0.0))
        ii = ii.at[net["post"]].add(jnp.minimum(q, 0.0))
    out_st = dict(vs=vs, vd=vd, i_exc=ie, i_inh=ii, refr=refr, bits=bits, phase=phase, rng=rng)
    if cond_mode:
        out_st["g_exc"] = ge
        out_st["g_inh"] = gi
        out_st["g_exc_rev"] = gerev
        out_st["g_inh_rev"] = girev
    return out_st, spiked.astype(jnp.uint8), arrivals
