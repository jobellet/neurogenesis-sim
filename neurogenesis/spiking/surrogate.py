"""Surrogate gradients of the integer kernel with respect to synaptic weights (JAX; part of E2).

`run_differentiable` returns the exact `lif_int` spikes of `jax_backend` (same integers, same spikes per neuron and tick:
the kernel itself is not changed) and lets `jax.grad` pass through them. Each state value (membrane potential,
synaptic current, spike) is the exact integer one, but its derivative is that of a smooth relaxation of the update,
evaluated along the exact trajectory (straight-through estimators; Bengio et al. 2013, arXiv:1308.3432):
- bit-shift decays x - (x >> k) are differentiated as x (1 - 2^-k), and i >> 2 as i / 4;
- the threshold step is differentiated as a fast sigmoid, d spike / d v = 1 / (1 + beta |v - threshold| / threshold)^2
  (surrogate gradients: Zenke & Ganguli 2018, Neural Comput 30:1514; Neftci et al. 2019, IEEE Signal Process Mag);
- weights are rounded to integers in the forward pass and differentiated as the identity.
So gradients are approximate (a descent direction for losses on spike counts or rates), while the forward pass stays
bit-identical. Gradients pass through leaky integrate-and-fire neurons (mode 0) only; Poisson and burster neurons keep
their exact spikes with zero derivative. Single-channel synapses (no `channel` array). Memory O(T (N + E)) for the
backward pass; time O(T (N + E)).
"""
from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np

from . import jax_backend as jb


def _surrogate_step(x, beta):
    """Value 0 (exact spikes are added by the caller), derivative 1 / (1 + beta |x|)^2."""
    sg = x / (1.0 + beta * jnp.abs(x))
    return sg - jax.lax.stop_gradient(sg)


def run_differentiable(net: dict, weight, ticks: int, ext=None, seed: int = 12345, beta: float = 5.0):
    """Spikes (ticks, N) float32 of a packed network (`jax_backend.pack`) with float synaptic `weight` (E,), exact in
    value (equal to `jax_backend` with round(weight)) and differentiable with respect to `weight` and `ext`.
    ext: (ticks, N) external current per tick (integers in value), or None. `net` must hold concrete arrays (it
    may be closed over by a jitted function; `weight` and `ext` may be traced)."""
    if "channel" in net:
        raise ValueError("run_differentiable supports single-channel synapses only")
    D = int(np.max(np.asarray(net["delay"]))) + 1          # history depth; `net` holds concrete (numpy) arrays
    net = {k: jnp.asarray(v) for k, v in net.items()}
    N = net["mode"].shape[-1]
    weight = jnp.asarray(weight, jnp.float32)
    w_int = jnp.round(jax.lax.stop_gradient(weight)).astype(jnp.int32)
    w_ste = weight + jax.lax.stop_gradient(w_int.astype(jnp.float32) - weight)
    exact_net = dict(net, weight=w_int)
    ext = jnp.zeros((ticks, N), jnp.float32) if ext is None else jnp.asarray(ext, jnp.float32)
    ext_int = jnp.round(jax.lax.stop_gradient(ext)).astype(jnp.int32)
    ext = ext + jax.lax.stop_gradient(ext_int.astype(jnp.float32) - ext)
    a_v = 1.0 - jnp.exp2(-net["shift_v"].astype(jnp.float32))
    a_s = 1.0 - jnp.exp2(-net["shift_s"].astype(jnp.float32))
    thr = net["threshold"].astype(jnp.float32)
    lif = (net["mode"] == 0).astype(jnp.float32)
    valid = net["valid"].astype(jnp.float32)
    st0 = jb.init_state(exact_net, seed)
    carry0 = (st0, jnp.zeros(N, jnp.float32), jnp.zeros(N, jnp.float32), jnp.zeros((D, N), jnp.float32))
    sg = jax.lax.stop_gradient

    def step(carry, inputs):
        st, v, i, H = carry
        e_f, e_i = inputs
        new, spk, _ = jb.tick(exact_net, st, e_i)
        # exact pre-threshold potential of LIF neurons, as in jax_backend.tick
        i_in_exact = st["i_syn"] + e_i
        v_pre_exact = jnp.clip(jb._decay(st["v"], net["shift_v"]) + jnp.right_shift(jb._decay(i_in_exact, net["shift_s"]), 2),
                               -2048, 2048).astype(jnp.float32)
        i_dec = (i + e_f) * a_s
        v_pre = jnp.clip(v * a_v + i_dec / 4.0, -2048.0, 2048.0)
        v_pre = v_pre + sg(v_pre_exact - v_pre)
        s = spk.astype(jnp.float32) + lif * _surrogate_step((v_pre - thr) / thr, beta)
        refr = (st["refr"] > 0).astype(jnp.float32)
        keep = (1.0 - s) * (1.0 - refr)
        v_new = v_pre * keep - 256.0 * (1.0 - keep)
        v_new = v_new + sg(new["v"].astype(jnp.float32) - v_new)
        H = jnp.concatenate([s[None], H[:-1]], axis=0)
        arrivals = H[net["delay"], net["pre"]] * valid
        i_new = i_dec + jax.ops.segment_sum(arrivals * w_ste, net["post"], num_segments=N)
        i_new = i_new + sg(new["i_syn"].astype(jnp.float32) - i_new)
        return (new, v_new, i_new, H), s

    _, spikes = jax.lax.scan(step, carry0, (ext, ext_int))
    return spikes
