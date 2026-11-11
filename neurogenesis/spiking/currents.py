"""Slow intrinsic currents for any neuron model, without Hodgkin-Huxley gates.

Linear and piecewise-linear reductions of voltage-gated channels. Each current keeps ONE float state per neuron, is advanced
once per 1 ms tick with an exact exponential step, and is given to the model as external current (the `ext` argument of
`tick`), so the integer kernel and its equivalent implementations are not changed. Voltages and currents are in the units of
the model in use (integer kernel: rest 0, threshold 1024 by default, reset -256).

- `t_current`: low-threshold (T-type calcium-like) current in its integrate-and-fire-or-burst form (Smith, Cox, Sherman &
  Rinzel 2000, J Neurophysiol 83:588). An inactivation variable h in [0, 1] recovers while the neuron is hyperpolarised
  below `v_h` and decays above it; above `v_h` the neuron receives the current g x h. A neuron held depolarised has h = 0
  (tonic mode: no extra current). A neuron released from a long enough hyperpolarisation receives a transient inward current
  (rebound burst).
- `recovery_current`: one linear recovery variable u with du/dt = (kappa x v - u) / tau and a jump `d` at each spike; the
  neuron receives -u. kappa > 0: a restorative current (sag, resonance; h-current-like). d > 0: spike-frequency adaptation.
  This is the first-order (quasi-active) reduction of a gated current around an operating point (Koch 1984; Richardson,
  Brunel & Hakim 2003), i.e. the extra variable of a generalised integrate-and-fire neuron.

Cost per neuron and tick: 4 bytes of state and about 6 floating-point operations for each current.
Neutral parameters (g = 0; kappa = 0 and d = 0) give a zero current.
"""
from __future__ import annotations

import jax.numpy as jnp

STATE_BYTES = 4      # per neuron and current
FLOPS = 6            # per neuron and tick, approximate


def t_decays(tau_minus, tau_plus):
    """Per-tick decay factors (exp(-1 / tau)) of `t_current` from its two time constants in ms."""
    return jnp.exp(-1.0 / jnp.asarray(tau_minus, jnp.float32)), jnp.exp(-1.0 / jnp.asarray(tau_plus, jnp.float32))


def t_current(h, v, g, v_h, dec_minus, dec_plus, hold=None):
    """One tick of the low-threshold current. h (N,) float32 in [0, 1]; v (N,) membrane potential before the tick; g (N,)
    maximal current; v_h (N,) de-inactivation threshold; dec_minus, dec_plus: decay factors of h above v_h (inactivation,
    about 20 ms) and of 1 - h below it (recovery, about 100 ms). hold (N,) bool: neurons whose h is frozen this tick
    (use the refractory flag when the reset potential is below v_h). Returns (h_new, current (N,) float32)."""
    below = v < v_h
    h_new = jnp.where(below, 1.0 - (1.0 - h) * dec_plus, h * dec_minus)
    if hold is not None:
        h_new = jnp.where(hold, h, h_new)
    return h_new.astype(jnp.float32), jnp.where(below, 0.0, g * h).astype(jnp.float32)


def recovery_current(u, v, spiked, kappa, dec, d=0.0):
    """One tick of a linear recovery variable. u (N,) float32; v (N,) membrane potential relative to the operating point;
    spiked (N,) the neuron's spikes of the previous tick; kappa (N,) coupling (current per unit of v); dec = exp(-1 / tau);
    d (N,) jump of u per spike. Returns (u_new, current = -u_new)."""
    u_new = kappa * v + (u - kappa * v) * dec + d * jnp.asarray(spiked, jnp.float32)
    return u_new.astype(jnp.float32), (-u_new).astype(jnp.float32)
