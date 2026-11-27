"""Simulation state files (format `neurogenesis-simstate`, version 1): pause and resume a simulation exactly.

A state is the dict a neuron model's `init_state` returns and its `tick` updates (membrane variables, synaptic
currents, the spike history that carries spikes along delayed axons, refractory counters, burst phases and the
drivers' random state). `save_state` writes it as an `.npz` (no pickle) with a format version, the model name, the
tick count and the fingerprint of the network it belongs to; `load_state` refuses a state of another network or model.
Running T ticks in one go and running t ticks, saving, loading and running T - t more give the same spikes, bit for
bit (tested for `lif_int`).

`extend_state` gives a state to a network that grew at the end (new cells and synapses appended, old indices kept):
old cells keep their state, new cells start from the model's rest values. This is the state side of the develop /
simulate loop planned for adult neurogenesis (roadmap C26).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

FORMAT = "neurogenesis-simstate"
VERSION = 1


def network_fingerprint(net) -> str:
    """SHA-256 of the packed kernel arrays of a network (neurons, synapses, delays): equal for equal networks."""
    from .jax_backend import pack
    arrays = pack(net) if not isinstance(net, dict) else net
    h = hashlib.sha256()
    for key in sorted(arrays):
        a = np.ascontiguousarray(np.asarray(arrays[key]))
        h.update(key.encode())
        h.update(str(a.dtype).encode() + str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def save_state(path, state: Dict[str, Any], net, model: str = "lif_int", tick: int = 0) -> None:
    """Writes `state` (a model state dict) with its metadata to `path` (.npz)."""
    meta = dict(format=FORMAT, version=VERSION, model=model, tick=int(tick), fingerprint=network_fingerprint(net),
                keys=sorted(state))
    arrays = {f"state__{k}": np.asarray(v) for k, v in state.items()}
    np.savez(Path(path), __meta__=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8), **arrays)


def load_state(path, net, model: str = "lif_int") -> Tuple[Dict[str, Any], int]:
    """Reads a state saved by `save_state` for this network and model. Returns (state, tick)."""
    import jax.numpy as jnp
    with np.load(Path(path), allow_pickle=False) as f:
        meta = json.loads(bytes(f["__meta__"]).decode())
        if meta.get("format") != FORMAT:
            raise ValueError(f"{path}: not a {FORMAT} file")
        if int(meta.get("version", 0)) > VERSION:
            raise ValueError(f"{path}: state format version {meta['version']} is newer than {VERSION}")
        if meta["model"] != model:
            raise ValueError(f"{path}: state of model {meta['model']!r}, not {model!r}")
        if meta["fingerprint"] != network_fingerprint(net):
            raise ValueError(f"{path}: the state belongs to another network (fingerprint mismatch)")
        state = {k: jnp.asarray(f[f"state__{k}"]) for k in meta["keys"]}
    return state, int(meta["tick"])


def extend_state(state: Dict[str, Any], net, model: str = "lif_int", n_old: int = None, seed: int = 12345) -> Dict[str, Any]:
    """State for `net`, a network whose first `n_old` cells are the cells of `state` with the same indices.

    Per-cell arrays (the axis whose length is the cell count) keep the old values for the first `n_old` cells, and the model's
    rest values for the new ones; extra history words (longer delays) start empty. Scalars (the drivers' random
    state) are kept. `n_old` defaults to the old cell count, read from the membrane variable.
    """
    import jax.numpy as jnp
    from .jax_backend import pack
    from .models import get_model
    fresh = get_model(model).init_state(pack(net), seed)
    v_key = "v" if "v" in state else "vs"
    n_old = int(np.shape(state[v_key])[-1]) if n_old is None else int(n_old)
    n_new = int(np.shape(fresh[v_key])[-1])
    if n_new < n_old:
        raise ValueError("extend_state: the new network has fewer cells; cells must only be appended")
    out = {}
    for key, new in fresh.items():
        new = np.array(new)
        old = state.get(key)
        if old is None:
            out[key] = jnp.asarray(new)
            continue
        old = np.asarray(old)
        if old.ndim == 0:
            out[key] = jnp.asarray(old)
            continue
        if old.ndim != new.ndim:
            raise ValueError(f"extend_state: state array {key!r} changed rank")
        axes = [ax for ax in range(new.ndim) if new.shape[ax] == n_new and old.shape[ax] >= n_old]
        if not axes:
            raise ValueError(f"extend_state: state array {key!r} has no cell axis")
        cell = axes[-1]
        idx = tuple(slice(0, n_old) if ax == cell else slice(0, min(new.shape[ax], old.shape[ax]))
                    for ax in range(new.ndim))
        new[idx] = old[idx]
        out[key] = jnp.asarray(new)
    return out
