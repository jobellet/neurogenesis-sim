"""JAX port of the integer spiking kernel (neurogenesis/spiking/reference.py, src/sim/sim.worker.ts), bit for bit.

Same integer arithmetic (bit-shift leak and synaptic decay, clamp to +-2048, per-neuron threshold (default 1024), reset -256, optional absolute
refractory period), same 32-bit spike shift register for axonal delays, same xorshift32 generator drawn once per Poisson
neuron per tick in neuron-index order. Synapses are a padded edge list, so that networks of different sizes can be
stacked and run together under jax.vmap (pad neurons with mode 0 and no synapses, edges with weight 0).

    net = pack(SNNNetwork, n_pad=None, e_pad=None)       # arrays (numpy) of one network
    state = init_state(net, seed)
    state, spikes = run(net, state, ticks)                # spikes: (ticks, N) uint8
    tick(net, state, ext_current) -> (state, spikes, arrivals)   # one tick; arrivals: (E,) spikes reaching each synapse
"""
from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np

from .network import SNNNetwork

U32 = jnp.uint32


def pack(network: SNNNetwork, n_pad: int | None = None, e_pad: int | None = None, p_pad: int | None = None) -> dict:
    """Numpy arrays of a network, padded to n_pad neurons, e_pad synapses and p_pad Poisson neurons (the Poisson list is
    scanned sequentially at every tick, so it is kept short: by default the number of Poisson neurons, at least 1)."""
    n = network.num_neurons
    if network.synapse_arrays is not None:
        sa = network.synapse_arrays
        mask = (sa["pre"] < n) & (sa["post"] < n)
        s_pre = sa["pre"][mask].astype(np.uint32)
        s_post = sa["post"][mask].astype(np.uint32)
        s_w = sa["weight"][mask].astype(np.int32)
        s_d = sa["delay"][mask].astype(np.int32)
        n_syn = len(s_pre)
    else:
        syn = [s for s in network.synapses if s.pre < n and s.post < n]
        s_pre = np.asarray([s.pre for s in syn], np.uint32)
        s_post = np.asarray([s.post for s in syn], np.uint32)
        s_w = np.asarray([s.weight for s in syn], np.int32)
        s_d = np.asarray([s.delay for s in syn], np.int32)
        n_syn = len(syn)
    N = n_pad or n
    E = e_pad or max(n_syn, 1)
    assert N >= n and E >= n_syn
    f = lambda attr, dt, fill=0: np.asarray([getattr(x, attr) for x in network.neurons] + [fill] * (N - n), dt)
    mode = f("mode", np.int32)
    pois = np.nonzero(mode[:n] == 1)[0]
    pad_e = E - n_syn
    out = dict(
        n=np.int32(n),
        mode=mode, shift_v=f("shift_v", np.int32, 5), shift_s=f("shift_s", np.int32, 4),
        burst_period=f("burst_period", np.int32, 200), burst_duty=f("burst_duty", np.int32, 24),
        refractory=f("refractory", np.int32, 0), role=f("role", np.int32, 0), threshold=f("threshold", np.int32, 1024),
        base_weight=f("base_weight", np.int32, 0),
        poisson_thresh=np.asarray([min(4294967295, int((x.poisson_hz / 1000.0) * 4294967296)) for x in network.neurons] + [0] * (N - n), np.uint32),
        pois_idx=np.concatenate([pois, np.full((p_pad or max(len(pois), 1)) - len(pois), -1)]).astype(np.int32),  # in index order
        n_pois=np.int32(len(pois)),
        pre=np.concatenate([s_pre, np.zeros(pad_e, np.uint32)]) if pad_e else s_pre,
        post=np.concatenate([s_post, np.zeros(pad_e, np.uint32)]) if pad_e else s_post,
        weight=np.concatenate([s_w, np.zeros(pad_e, np.int32)]) if pad_e else s_w,
        delay=np.concatenate([s_d, np.ones(pad_e, np.int32)]) if pad_e else s_d,
        valid=np.concatenate([np.ones(n_syn, bool), np.zeros(pad_e, bool)]) if pad_e else np.ones(n_syn, bool),
    )
    out["mode"][n:] = 0
    return out


def init_state(net: dict, seed: int = 12345) -> dict:
    N = np.shape(net["mode"])[-1]
    z = jnp.zeros(N, jnp.int32)
    return dict(v=z, i_syn=z, bits=jnp.zeros(N, U32), phase=z, refr=z, rng=jnp.asarray(seed, U32))


def _xorshift(x):
    x = x ^ (x << U32(13))
    x = x ^ (x >> U32(17))
    return x ^ (x << U32(5))


def _decay(x, k):
    """x - max(1, x >> k) for x > 0, x - min(-1, x >> k) for x < 0 (arithmetic shift), as the reference."""
    sh = jnp.right_shift(x, k)
    return jnp.where(x > 0, x - jnp.maximum(1, sh), jnp.where(x < 0, x - jnp.minimum(-1, sh), x))


def tick(net: dict, st: dict, ext_current=None):
    """One tick. ext_current (N,) int32 is added to the synaptic current before the tick (0 for the reference)."""
    net = {k: jnp.asarray(x) for k, x in net.items()}
    i_syn = st["i_syn"] if ext_current is None else st["i_syn"] + ext_current
    v = _decay(st["v"], net["shift_v"])
    i_syn = _decay(i_syn, net["shift_s"])
    v = jnp.clip(v + jnp.right_shift(i_syn, 2), -2048, 2048)
    # Poisson drivers: one xorshift draw per Poisson neuron, in index order (padding does not advance the generator)
    P = net["pois_idx"].shape[-1]

    def draw(x, k):
        x2 = jnp.where(k < net["n_pois"], _xorshift(x), x)
        return x2, x2
    rng, draws = jax.lax.scan(draw, st["rng"], jnp.arange(P))
    fire_p = (net["pois_idx"] >= 0) & (draws < net["poisson_thresh"][jnp.maximum(net["pois_idx"], 0)])
    pois_fire = jnp.zeros_like(v, dtype=bool).at[jnp.maximum(net["pois_idx"], 0)].max(fire_p)
    v = jnp.where((net["mode"] == 1) & pois_fire, net["threshold"], v)
    # bursters
    period = jnp.where(net["burst_period"] == 0, 200, net["burst_period"])
    duty = jnp.where(net["burst_duty"] == 0, 24, net["burst_duty"])
    is_b = net["mode"] == 2
    phase = jnp.where(is_b, (st["phase"] + 1) % period, st["phase"])
    v = jnp.where(is_b & (phase < duty) & ((phase & 3) == 0), net["threshold"], v)
    # threshold, refractory period, reset
    spiked = v >= net["threshold"]
    in_refr = st["refr"] > 0
    spiked = spiked & ~in_refr
    refr = jnp.where(in_refr, st["refr"] - 1, jnp.where(spiked, net["refractory"], 0))
    v = jnp.where(spiked | in_refr, -256, v)
    bits = (st["bits"] << U32(1)) | spiked.astype(U32)
    # propagation through delays
    arrivals = ((bits[net["pre"]] >> net["delay"].astype(U32)) & U32(1)).astype(jnp.int32) * net["valid"]
    i_syn = i_syn.at[net["post"]].add(arrivals * net["weight"])
    return dict(v=v, i_syn=i_syn, bits=bits, phase=phase, refr=refr, rng=rng), spiked.astype(jnp.uint8), arrivals


def run(net: dict, st: dict, ticks: int):
    def f(s, _):
        s, spk, _ = tick(net, s)
        return s, spk
    return jax.lax.scan(f, st, None, length=ticks)


def firing_stats(spikes, mode, n, dt_ms=1.0):
    """Rates (Hz) of the n real neurons, and the coefficient of variation of their inter-spike intervals (numpy)."""
    spikes = np.asarray(spikes)[:, :n]
    T = spikes.shape[0]
    rate = spikes.sum(0) / (T * dt_ms / 1000.0)
    cv = np.full(n, np.nan)
    for i in range(n):
        t = np.nonzero(spikes[:, i])[0]
        if len(t) >= 3:
            isi = np.diff(t)
            cv[i] = isi.std() / isi.mean()
    lif = np.asarray(mode)[:n] == 0
    return dict(rate=rate, cv=cv, lif=lif)
