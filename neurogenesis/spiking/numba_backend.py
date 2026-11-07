"""Event-driven CPU kernel for `lif_int` networks (Numba; optional dependency: pip install "neurogenesis-sim[fast]").

Same integer arithmetic and the same spikes as `reference.IntegerSNNSimulator` and `jax_backend.tick` (tested
per neuron and tick): sign-symmetric bit-shift leak of v and i_syn, v += i_syn >> 2, clamp at +-2048, Poisson drivers
(mode 1, one xorshift32 draw per Poisson neuron per tick in index order, from `seed`), bursters (mode 2), threshold,
refractory period, reset to -256, axonal delays 1-255 ticks. Instead of a spike-history bit field it keeps a ring
buffer of future synaptic input per neuron, so the cost per tick is O(N + spikes x out-degree), not O(E): fast for
sparse activity on a CPU. Single-channel synapses only (no `channel` / `e_rev`), external current not supported.

Optional extensions, off by default (with them off the kernel is exact; they have no counterpart in the other kernels):

- forced spikes: the membrane is set to 2048 before the tick (as a clamped input; it still leaks and must reach the
  threshold), either at random (`forced_p` per neuron and tick, from its own generator `forced_seed`) or at given
  (tick, neuron) events;
- short-term depression per presynaptic neuron (Tsodyks & Markram 1997, PNAS): resources x recover to 1 with
  `tau_rec`, a spike uses U x and its synapses carry w (1 - strength (1 - x)), applied when the spike is emitted;
- threshold homeostasis per neuron (intrinsic plasticity): offset += rate (spike - target_hz / 1000), clipped;
- `excitatory_gain`: every positive weight multiplied at birth (a perturbation).

Spikes caused by forced inputs are counted apart from recurrent spikes.
"""
from __future__ import annotations

import numpy as np

try:
    from numba import njit
    HAVE_NUMBA = True
except ImportError:                                           # pragma: no cover - exercised only without numba
    HAVE_NUMBA = False

    def njit(*a, **k):
        def wrap(f):
            def missing(*args, **kwargs):
                raise ImportError('neurogenesis.spiking.numba_backend needs numba: pip install "neurogenesis-sim[fast]"')
            return missing
        return wrap

RING = 256                                                    # > the largest delay (255 ticks)


def arrays(network) -> dict:
    """Kernel arrays of an SNNNetwork: outgoing synapses grouped by presynaptic neuron (CSR) and neuron parameters."""
    n = network.num_neurons
    sa = network.synapse_arrays
    if sa is not None:
        if "channel" in sa or "e_rev" in sa:
            raise ValueError("numba_backend: multi-channel or conductance synapses are not supported")
        pre, post = np.asarray(sa["pre"], np.int64), np.asarray(sa["post"], np.int64)
        w, d = np.asarray(sa["weight"], np.float64), np.asarray(sa["delay"], np.int64)
    else:
        syn = network.synapses
        pre = np.asarray([s.pre for s in syn], np.int64)
        post = np.asarray([s.post for s in syn], np.int64)
        w = np.asarray([s.weight for s in syn], np.float64)
        d = np.asarray([s.delay for s in syn], np.int64)
    keep = (pre < n) & (post < n)
    pre, post, w, d = pre[keep], post[keep], w[keep], d[keep]
    if len(d) and (d.min() < 1 or d.max() > 255):
        raise ValueError("numba_backend: delays must be in [1, 255] ticks")
    o = np.argsort(pre, kind="stable")
    row = np.zeros(n + 1, np.int64)
    np.add.at(row, pre[o] + 1, 1)
    nu = lambda a, dt=np.int64: np.asarray([getattr(x, a) for x in network.neurons], dt)
    return dict(n=n, row=np.cumsum(row), post=post[o], weight=w[o], delay=d[o], mode=nu("mode"),
                shift_v=nu("shift_v"), shift_s=nu("shift_s"), threshold=nu("threshold"), refractory=nu("refractory"),
                burst_period=nu("burst_period"), burst_duty=nu("burst_duty"),
                poisson_thresh=np.asarray([min(4294967295, int((x.poisson_hz / 1000.0) * 4294967296))
                                           for x in network.neurons], np.int64))


def simulate(net, ticks: int, seed: int = 12345, forced_p=None, forced_events=None, forced_seed: int = 0,
             depression=None, homeostasis=None, excitatory_gain: float = 1.0, bin_ticks: int = 0,
             threshold_offset=None) -> dict:
    """Simulate `ticks` ticks of an SNNNetwork (or the dict of `arrays`).

    forced_p: probability per tick of a forced spike, scalar or (N,); forced_events: (ticks_array, neurons_array) of
    forced spikes; depression: dict(strength, U, tau_rec); homeostasis: dict(rate, target_hz, lo=-900, hi=4000);
    threshold_offset: (N,) starting offsets (float); bin_ticks > 0 also returns recurrent spike counts per neuron in
    bins of that many ticks. Returns dict(spikes (T,) all spikes per tick, recurrent (T,) spikes not caused by a
    forced input, cells (T // bin_ticks, N) int16 if binned, threshold_offset (N,), resources (N,))."""
    a = net if isinstance(net, dict) else arrays(net)
    n = a["n"]
    fp = np.zeros(n) if forced_p is None else np.broadcast_to(np.asarray(forced_p, np.float64), (n,)).copy()
    if forced_events is None:
        ev_t, ev_n = np.zeros(0, np.int64), np.zeros(0, np.int64)
    else:
        ev_t, ev_n = (np.asarray(x, np.int64) for x in forced_events)
        o = np.argsort(ev_t, kind="stable")
        ev_t, ev_n = ev_t[o], ev_n[o]
    dep = depression or {}
    hom = homeostasis or {}
    th0 = np.zeros(n) if threshold_offset is None else np.asarray(threshold_offset, np.float64).copy()
    out = _run(int(ticks), a["row"], a["post"], a["weight"], a["delay"], a["mode"], a["shift_v"], a["shift_s"],
               a["threshold"], a["refractory"], a["burst_period"], a["burst_duty"], a["poisson_thresh"],
               np.int64(seed) & 0xFFFFFFFF, fp, ev_t, ev_n, int(forced_seed),
               float(dep.get("strength", 0.0)), float(dep.get("U", 0.5)),
               float(np.exp(-1.0 / dep.get("tau_rec", 500.0))), float(hom.get("rate", 0.0)),
               float(hom.get("target_hz", 0.0)) / 1000.0, float(hom.get("lo", -900.0)), float(hom.get("hi", 4000.0)),
               th0, float(excitatory_gain), int(bin_ticks))
    res = dict(spikes=out[0], recurrent=out[1], threshold_offset=out[3], resources=out[4])
    if bin_ticks > 0:
        res["cells"] = out[2]
    return res


@njit(cache=True)
def _decay(x, k):
    if x > 0:
        return x - max(1, x >> k)
    if x < 0:
        return x - min(-1, x >> k)
    return x


@njit(cache=True)
def _xorshift(x):
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    return x


@njit(cache=True)
def _run(T, row, post, w, delay, mode, shift_v, shift_s, thr0, refractory, burst_period, burst_duty, pthresh, rng,
         fp, ev_t, ev_n, fseed, stp_s, stp_U, stp_dec, h_rate, h_target, h_lo, h_hi, thoff0, gain, bin_ticks):
    n = len(thr0)
    np.random.seed(fseed)
    v = np.zeros(n, np.int64)
    isyn = np.zeros(n, np.int64)
    refr = np.zeros(n, np.int64)
    phase = np.zeros(n, np.int64)
    ring = np.zeros((256, n), np.float64)
    thoff = thoff0.copy()
    x = np.ones(n, np.float64)
    last = np.zeros(n, np.int64)
    allc = np.zeros(T, np.int32)
    rec = np.zeros(T, np.int32)
    nb = T // bin_ticks if bin_ticks > 0 else 0
    cells = np.zeros((max(nb, 1), n), np.int16)
    spk = np.zeros(n, np.bool_)
    forced = np.zeros(n, np.bool_)
    any_fp = False
    for i in range(n):
        if fp[i] > 0.0:
            any_fp = True
    e = 0
    for t in range(T):
        for i in range(n):
            forced[i] = False
        if any_fp:
            for i in range(n):
                if fp[i] > 0.0 and np.random.random() < fp[i]:
                    forced[i] = True
        while e < len(ev_t) and ev_t[e] < t:
            e += 1
        while e < len(ev_t) and ev_t[e] == t:
            forced[ev_n[e]] = True
            e += 1
        for i in range(n):
            vi = 2048 if forced[i] else v[i]
            vi = _decay(vi, shift_v[i])
            si = _decay(isyn[i], shift_s[i])
            isyn[i] = si
            vi = vi + (si >> 2)
            if vi > 2048:
                vi = 2048
            elif vi < -2048:
                vi = -2048
            th = thr0[i] + int(np.rint(thoff[i]))
            m = mode[i]
            if m == 1:
                rng = _xorshift(rng)
                if rng < pthresh[i]:
                    vi = th
            elif m == 2:
                period = burst_period[i] if burst_period[i] != 0 else 200
                duty = burst_duty[i] if burst_duty[i] != 0 else 24
                ph = (phase[i] + 1) % period
                phase[i] = ph
                if ph < duty and (ph & 3) == 0:
                    vi = th
            s = vi >= th
            if refr[i] > 0:
                refr[i] -= 1
                s = False
                vi = -256
            if s:
                refr[i] = refractory[i]
                vi = -256
                allc[t] += 1
                if not forced[i]:
                    rec[t] += 1
                    if bin_ticks > 0 and t // bin_ticks < nb:
                        cells[t // bin_ticks, i] += 1
            v[i] = vi
            spk[i] = s
            if h_rate != 0.0:
                th2 = thoff[i] + h_rate * ((1.0 if s else 0.0) - h_target)
                thoff[i] = min(h_hi, max(h_lo, th2))
        for i in range(n):
            if not spk[i]:
                continue
            g = 1.0
            if stp_s > 0.0:
                xi = 1.0 - (1.0 - x[i]) * stp_dec ** (t - last[i])
                g = 1.0 - stp_s * (1.0 - xi)
                x[i] = xi - stp_U * xi
                last[i] = t
            exact = g == 1.0 and gain == 1.0
            for k in range(row[i], row[i + 1]):
                wv = w[k]
                if not exact:
                    if wv > 0.0:
                        wv *= gain
                    wv = np.rint(wv * g)
                ring[(t + delay[k]) % 256, post[k]] += wv
        slot = t % 256
        for i in range(n):
            isyn[i] += int(ring[slot, i])
            ring[slot, i] = 0.0
    return allc, rec, cells, thoff, x
