"""Compute cost of a simulation before running it: memory, operations and wall time, per neuron model, on this machine.

Memory is counted array by array as the kernels allocate it (neuron parameters, model state, synapse arrays, temporary
arrivals, recorded counts). Time per tick is t = a + N x substeps x b + E x c, with a (fixed overhead per tick), b (seconds per neuron-substep)
and c (seconds per synapse-tick) measured once per model and device by a short benchmark (calibrate) and cached in
~/.cache/neurogenesis/throughput.json. Estimates for networks far larger than the benchmark extrapolate linearly and
ignore effects such as cache misses or multi-device communication: treat them as optimistic lower bounds.

    python -m neurogenesis estimate --neurons 3e8 --synapses-per-neuron 5000 --seconds 1
"""
from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path

import numpy as np

PARAM_BYTES = 40               # per neuron: mode, shift_v, shift_s, burst period and duty, refractory, role, threshold,
                               # sign, Poisson threshold (int32 each)
SYNAPSE_BYTES = 17             # pre, post, weight, delay (int32) and valid (bool)
SYNAPSE_WORK_BYTES = 8         # per synapse and tick: arrivals and the scatter-add buffer
CACHE = Path(os.environ.get("NEUROGENESIS_CACHE", Path.home() / ".cache" / "neurogenesis")) / "throughput.json"


class CostError(RuntimeError):
    """The simulation does not fit in this machine's memory (pass force=True to try anyway)."""


def _device():
    import jax
    d = jax.devices()[0]
    return f"{d.platform}:{d.device_kind}:jax{jax.__version__}"


def available_memory():
    """Bytes available to the simulation: free GPU memory if JAX runs on a GPU, else physical RAM."""
    import jax
    d = jax.devices()[0]
    if d.platform != "cpu":
        try:
            st = d.memory_stats()
            return int(st["bytes_limit"] - st.get("bytes_in_use", 0))
        except Exception:                                   # memory statistics not available on this backend
            pass
    try:
        return int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError, AttributeError):
        return None


def memory_bytes(model, n_neurons, n_synapses, n_records=1, max_delay=31):
    """Bytes needed: parameters and state of every neuron, synapse arrays and their per-tick buffers, recorded counts."""
    from .spiking.models import get_model
    m = get_model(model)
    W = max(1, (max_delay + 32) // 32)
    history_overhead = (W - 1) * 4
    return int(n_neurons * (PARAM_BYTES + m.state_bytes + history_overhead + 4 * n_records) + n_synapses * (SYNAPSE_BYTES + SYNAPSE_WORK_BYTES))


def _load():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _random_network(n, e, seed=0):
    from .spiking.network import NeuronData, SNNNetwork, SynapseData
    rng = np.random.default_rng(seed)
    neurons = [NeuronData(id=i, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, shift_v=5, shift_s=4,
                          base_weight=1, conn_radius=0.0, conn_prob=0.0, refractory=3) for i in range(n)]
    pre, post = rng.integers(0, n, e), rng.integers(0, n, e)
    syn = [SynapseData(pre=int(a), post=int(b), weight=int(w), delay=int(d))
           for a, b, w, d in zip(pre, post, rng.integers(-60, 120, e), rng.integers(1, 20, e))]
    return SNNNetwork(neurons=neurons, synapses=syn)


def _time_run(model, net, ticks):
    from .spiking.batch import simulate_counts
    ext = np.random.default_rng(1).integers(0, 40, size=(1, net.num_neurons)).astype(np.int32)
    simulate_counts([net], [ext], ticks=ticks, model=model, check_cost=False)          # compile
    t0 = time.perf_counter()
    simulate_counts([net], [ext], ticks=ticks, model=model, check_cost=False)
    return (time.perf_counter() - t0) / ticks


def calibrate(model, refresh=False):
    """Fixed seconds per tick (a), seconds per neuron-substep (b) and per synapse-tick (c) for a model on this device,
    fitted on three benchmark networks, measured once and cached."""
    from .spiking.models import get_model
    key = f"{model}@{_device()}"
    cache = _load()
    if key in cache and not refresh:
        return cache[key]
    m = get_model(model)
    configs = [(512, 512), (8192, 4096), (2048, 262144)]          # overhead, neuron-dominated, synapse-dominated
    t = [_time_run(model, _random_network(n, e), 50) for n, e in configs]
    A = np.asarray([[1.0, n * m.substeps, e] for n, e in configs])
    a, b, c = np.linalg.solve(A, np.asarray(t))
    a = float(max(a, 0.0))
    b = float(max(b, 0.05 * t[1] / (configs[1][0] * m.substeps)))
    c = float(max(c, 0.05 * t[2] / configs[2][1]))
    cache[key] = dict(a=a, b=b, c=c, measured=time.strftime("%Y-%m-%d %H:%M"))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1))
    return cache[key]


def estimate(model, n_neurons, n_synapses, ticks, n_records=1, calibrated=True, max_delay=31):
    """dict: memory (bytes), available memory, fits (bool), operations per tick, seconds per tick and in total (None if
    not calibrated and calibrated=False), and a one-line verdict."""
    from .spiking.models import get_model
    m = get_model(model)
    mem = memory_bytes(model, n_neurons, n_synapses, n_records, max_delay=max_delay)
    avail = available_memory()
    ops = n_neurons * m.substeps * m.flops + n_synapses * 6
    out = dict(model=model, neurons=int(n_neurons), synapses=int(n_synapses), ticks=int(ticks), memory_bytes=mem,
               available_bytes=avail, fits=avail is None or mem <= 0.8 * avail, ops_per_tick=float(ops))
    cal = calibrate(model) if calibrated else _load().get(f"{model}@{_device()}")
    if cal:
        spt = cal.get("a", 0.0) + n_neurons * m.substeps * cal["b"] + n_synapses * cal["c"]
        out.update(seconds_per_tick=spt, seconds_total=spt * ticks, seconds_per_simulated_second=spt * 1000)
    out["verdict"] = verdict(out)
    return out


def _human(x, unit):
    for p, s in ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if x >= p:
            return f"{x / p:.1f} {s}{unit}"
    return f"{x:.0f} {unit}"


def _duration(s):
    for d, u in ((86400 * 365, "years"), (86400, "days"), (3600, "h"), (60, "min")):
        if s >= d:
            return f"{s / d:.1f} {u}"
    return f"{s:.2f} s"


def verdict(e):
    mem = f"memory {_human(e['memory_bytes'], 'B')}"
    if e["available_bytes"]:
        mem += f" of {_human(e['available_bytes'], 'B')} available"
    if not e["fits"]:
        t = f"; and about {_duration(e['seconds_per_simulated_second'])} per simulated second" if "seconds_total" in e else ""
        return f"DOES NOT FIT: {mem}{t} (linear extrapolation)"
    if "seconds_total" in e:
        return f"fits ({mem}); about {_duration(e['seconds_total'])} for {e['ticks']} ticks ({_duration(e['seconds_per_simulated_second'])} per simulated second)"
    return f"fits ({mem}); time not calibrated on this device yet"


def check(model, n_neurons, n_synapses, ticks, force=False, warn_seconds=3600, max_delay=31):
    """Called before every batched simulation: refuses networks that do not fit in memory (CostError, unless force), and
    warns when a calibrated time estimate exceeds warn_seconds. Never runs a benchmark itself."""
    e = estimate(model, n_neurons, n_synapses, ticks, calibrated=False, max_delay=max_delay)
    if not e["fits"] and not force:
        raise CostError(e["verdict"] + " (pass force=True to try anyway)")
    if e.get("seconds_total", 0) > warn_seconds:
        warnings.warn(f"{model}: {e['verdict']}", RuntimeWarning, stacklevel=3)
    return e
