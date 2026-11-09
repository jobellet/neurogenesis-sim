"""Development during simulation (C26): alternate simulation blocks and developmental stages on one tissue.

Neurogenesis and remodelling go on in a functioning network (e.g. adult neurogenesis in neurogenic niches; Ming & Song
2011, Neuron 70:687). The kernels keep a fixed network within a block; between blocks a list of stages (the same JSON
form as a Project schedule: proliferate in a niche, migrate, grow_arbors, connect, transporter_switch, apoptosis ...)
changes the tissue, the network is recompiled, and every neuron that still exists keeps its kernel state (membrane
potential, synaptic current, spike history, burst phase, refractory counter) through its `cell_id`; the kernel's
random generator continues. New cells start at rest. With no stages between blocks, `blocks` blocks of `ticks` give the
same spikes as one run of blocks x ticks.

Randomness: the stages of block b draw from np.random.default_rng([seed, name salt, repeat, b + 1]), one stream per
stage and block (roadmap 2.1), so adding a block or a stage does not change the others. Cost: per block, the cost of
its stages plus a recompilation O(N + E) and the simulation O(ticks (N + E)).
"""
from __future__ import annotations

import copy
import importlib
import zlib
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from ..params import param_from_dict
from ..stages.base import Stage, _instantiate_fields
from ..fields import Field
from ..tissue import Tissue

_STATE_KEYS = ("v", "i_syn", "phase", "refr")


def _carry_state(old: Optional[dict], old_ids: Optional[np.ndarray], new: dict, new_ids: np.ndarray) -> dict:
    """New kernel state with the entries of neurons present in both networks copied from the old one."""
    if old is None:
        return new
    import jax.numpy as jnp
    pos = {int(c): k for k, c in enumerate(old_ids)}
    src = np.asarray([pos.get(int(c), -1) for c in new_ids], np.int64)
    dst = np.flatnonzero(src >= 0)
    src = src[dst]
    out = dict(new)
    for key in _STATE_KEYS + ("i_syn_channels",):
        if key in old and key in new:
            a = np.asarray(new[key]).copy()
            b = np.asarray(old[key])
            if a.ndim > 1 and a.shape[1:] != b.shape[1:]:
                continue
            a[dst] = b[src]
            out[key] = jnp.asarray(a)
    a = np.asarray(new["bits"]).copy()
    b = np.asarray(old["bits"])
    if a.ndim == 1 and b.ndim == 1:
        a[dst] = b[src]
    else:
        a2 = a.reshape(len(a), -1)
        b2 = b.reshape(len(b), -1)
        w = min(a2.shape[1], b2.shape[1])
        a2[dst, :w] = b2[src, :w]
        a = a2.reshape(a.shape)
    out["bits"] = jnp.asarray(a)
    out["rng"] = old["rng"]
    return out


def _run_stages(tissue: Tissue, configs: Sequence[Dict[str, Any]], genome: Dict[str, Any], fields: Dict[str, Any],
                seed: int, block: int) -> Tissue:
    for idx, config in enumerate(configs):
        name = config.get("name", f"stage_{idx}")
        salt = zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF
        params = {k: (param_from_dict(v) if isinstance(v, dict) else v) for k, v in config.get("params", {}).items()}
        stage = Stage(name=name, operator=config["operator"], params=params, when=config.get("when"),
                      repeat=config.get("repeat", 1))
        for rep in range(stage.repeat):
            tissue = stage.run(tissue, genome, fields, np.random.default_rng([seed, salt, rep, block + 1]), rep=rep)
    return tissue


def develop_during_simulation(tissue: Tissue, between: Sequence[Dict[str, Any]], blocks: int, ticks: int,
                              genome: Optional[Dict[str, Any]] = None, project: Optional[Dict[str, Any]] = None,
                              seed: int = 0, kernel_seed: int = 1,
                              ext_current: Union[None, int, Callable[[Tissue, int], np.ndarray]] = None
                              ) -> Tuple[Tissue, List[Dict[str, Any]]]:
    """Simulates `blocks` blocks of `ticks` ticks with the JAX `lif_int` kernel, running the stages `between` (schedule
    entries: {operator, name, params, when, repeat}) on the tissue after every block but the last.

    tissue: the starting tissue (not modified; a copy is developed). project: geometry, fields and plugins for the
    stages (its schedule is ignored). ext_current: external current added every tick: an int, or a function
    (tissue, block) -> one int per live cell, in tissue order. kernel_seed: seed of the kernel's generator (mapped to
    [1, 2^32 - 1] as in `refine_by_activity`). Returns (developed tissue, history): one dict per block with `cell_id`
    (live cells in network order) and `spikes` (ticks, cells) uint8.
    """
    import jax
    import jax.numpy as jnp
    from ..spiking.jax_backend import init_state, pack, tick

    genome = genome or {}
    project = project or {}
    for plugin in project.get("plugins", []):
        importlib.import_module(plugin)
    fields = _instantiate_fields({**project.get("geometry", {}), **project.get("fields", {})})
    fields = {k: (v.bind(genome) if isinstance(v, Field) else v) for k, v in fields.items()}
    tissue = copy.deepcopy(tissue)
    state, ids, history = None, None, []
    k_seed = int(kernel_seed) % 0xFFFFFFFF + 1
    for b in range(int(blocks)):
        net = tissue.to_network()
        packed = pack(net)
        new_ids = tissue.cell_id[tissue.alive].astype(np.int64)
        st = _carry_state(state, ids, init_state(packed, seed=k_seed), new_ids)
        n = int(tissue.alive.sum())
        if ext_current is None:
            ext = jnp.zeros(n, jnp.int32)
        elif callable(ext_current):
            ext = jnp.asarray(np.asarray(ext_current(tissue, b), np.int32).reshape(n))
        else:
            ext = jnp.full(n, int(ext_current), jnp.int32)

        def f(s, _):
            s, spk, _ = tick(packed, s, ext_current=ext)
            return s, spk
        st, spikes = jax.lax.scan(f, st, None, length=int(ticks))
        history.append(dict(block=b, cell_id=new_ids, spikes=np.asarray(spikes)[:, :n]))
        state, ids = st, new_ids
        if b < blocks - 1 and between:
            tissue = _run_stages(tissue, between, genome, fields, seed, b)
    return tissue, history
