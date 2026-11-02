"""Arbor growth (N2) and synapses on arbors with path-length conduction delays (N3)."""
from __future__ import annotations

import warnings
from typing import Any, Dict, Tuple

import numpy as np

from neurogenesis.arbors import NODE_BYTES, SOMA, ArborStore, compartment_id
from neurogenesis.params import resolve, worst_case
from neurogenesis.spatial import CellList
from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue

MAX_DELAY = 31
_MEAN_CONTACTS = 27          # mean candidate nodes per axon node within the contact distance, for the N3 cost


def _per_cell(value, n: int, dtype=float) -> np.ndarray:
    v = np.asarray(value, dtype=dtype)
    return np.broadcast_to(v, (n,)).copy() if v.ndim == 0 else v.reshape(n)


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(n < 1e-12, 1.0, n)


def _rotate(d: np.ndarray, angle: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Each unit vector d turned by `angle` (radians) towards a random perpendicular direction."""
    r = rng.standard_normal(d.shape)
    perp = _unit(r - np.sum(r * d, axis=1, keepdims=True) * d)
    return _unit(np.cos(angle)[:, None] * d + np.sin(angle)[:, None] * perp)


def _select(tissue: Tissue, sel) -> np.ndarray:
    mask = tissue.alive.copy()
    if isinstance(sel, dict):
        for key in ("region", "cell_type"):
            if key in sel:
                mask &= np.isin(getattr(tissue, key), np.asarray(sel[key]).ravel())
    return np.flatnonzero(mask)


@register_stage("grow_arbors")
class GrowArbors:
    """Stochastic growth of neurites from each selected cell's soma (an `ArborStore` in `tissue.morphology`).

    Each cell starts `n_neurites` tips at its soma (a soma node is added if the cell has none). For `steps` steps every
    active tip stops with probability `stop_prob`, otherwise turns by Gaussian `angle_noise` (radians), is pulled
    towards increasing values of `attractor_field` with gain `attraction` (a negative gain repels), and elongates by
    `step_length` (space units); with probability `branch_prob` it also starts a branch at `branch_angle`. A step
    that leaves the geometry `boundary` or lands where `stop_field` > 0 stops the tip. At the end each terminal node
    retracts with probability `retraction_prob`. The new nodes get compartment `compartment` ("axon", "dendrite",
    "neurite" or an integer user label). Every value may be a `Param`; per-cell values (e.g. a `Field`) are read at
    the soma. Randomness only from the stage stream; `max_nodes` bounds the number of new nodes (a safety bound).
    Branching growth models of dendrites: van Pelt & Uylings 2002, Network: Comput Neural Syst. No `steps` (or
    steps <= 0) is the no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        steps = int(worst_case(params.get("steps"), 0))
        n = float(worst_case(params.get("n_neurites"), 1))
        b = float(worst_case(params.get("branch_prob"), 0.0))
        tips = N * n * sum((1 + b) ** k for k in range(max(steps, 0)))
        nodes = int(min(tips, float(worst_case(params.get("max_nodes"), 1_000_000))) + N)
        return int(nodes * NODE_BYTES * 4 + N * 64), int(nodes * 80 + N * 20)

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        steps = int(resolve(params.get("steps", 0), genome, fields))
        cells = _select(tissue, params.get("cells"))
        if steps <= 0 or len(cells) == 0:
            return tissue
        pos = tissue.positions[cells]
        val = lambda k, d, dt=float: _per_cell(resolve(params.get(k, d), genome, fields, positions=pos), len(cells), dt)
        n_neur = val("n_neurites", 1, int)
        step_len, branch_p, branch_a = val("step_length", 1.0), val("branch_prob", 0.0), val("branch_angle", 0.5)
        noise, stop_p, retract_p = val("angle_noise", 0.2), val("stop_prob", 0.0), val("retraction_prob", 0.0)
        attraction = val("attraction", 0.0)
        comp = compartment_id(resolve(params.get("compartment", "dendrite"), genome, fields))
        max_nodes = int(resolve(params.get("max_nodes", 1_000_000), genome, fields))
        soma_r = float(resolve(params.get("soma_radius", 0.0), genome, fields))
        field_name = params.get("attractor_field")
        field_name = resolve(field_name, genome, fields) if field_name is not None else None
        stop_name = params.get("stop_field")
        stop_name = resolve(stop_name, genome, fields) if stop_name is not None else None
        boundary = params.get("boundary")
        boundary = resolve(boundary, genome, fields) if boundary is not None else None
        geom = fields.get(boundary) if isinstance(boundary, str) else boundary

        store = tissue.morphology if tissue.morphology is not None else ArborStore()
        base = store.n_nodes
        # soma nodes for cells that have none
        has_soma = np.zeros(len(tissue.alive), bool)
        has_soma[store.cell[store.compartment == SOMA]] = True
        soma_node = np.full(len(tissue.alive), -1, np.int64)
        soma_idx = np.flatnonzero(store.compartment == SOMA)
        soma_node[store.cell[soma_idx]] = soma_idx
        need = cells[~has_soma[cells]]
        xyz = [tissue.positions[need].astype(np.float32)]
        parent = [np.full(len(need), -1, np.int64)]
        cell_of = [need.astype(np.int64)]
        compart = [np.full(len(need), SOMA, np.int64)]
        soma_node[need] = base + np.arange(len(need))
        count = base + len(need)

        tip_cell_local = np.repeat(np.arange(len(cells)), n_neur)
        tip_node = soma_node[cells][tip_cell_local]
        tip_pos = pos[tip_cell_local].astype(np.float64)
        d0 = params.get("direction")
        if d0 is None:
            tip_dir = _unit(rng.standard_normal((len(tip_node), 3)))
        else:
            dv = np.asarray(resolve(d0, genome, fields, positions=pos), dtype=np.float64)
            tip_dir = _unit(np.broadcast_to(dv, (len(cells), 3))[tip_cell_local].copy())
        h = 1e-3
        for _ in range(steps):
            if len(tip_node) == 0 or count - base >= max_nodes:
                break
            c = tip_cell_local
            alive_tip = rng.random(len(c)) >= stop_p[c]
            tip_node, tip_pos, tip_dir, c = tip_node[alive_tip], tip_pos[alive_tip], tip_dir[alive_tip], c[alive_tip]
            tip_dir = _unit(tip_dir + rng.standard_normal(tip_dir.shape) * noise[c][:, None])
            if field_name is not None and np.any(attraction[c] != 0):
                from neurogenesis.stages.migration import _field_gradient
                g = _unit(_field_gradient(fields[field_name], tip_pos, h))
                tip_dir = _unit(tip_dir + attraction[c][:, None] * g)
            new_pos = tip_pos + step_len[c][:, None] * tip_dir
            ok = np.ones(len(c), bool)
            if hasattr(geom, "contains"):
                ok &= geom.contains(new_pos)
            if stop_name is not None:
                sv = np.asarray(fields[stop_name].values(new_pos), dtype=float)
                ok &= ~((sv[:, 0] if sv.ndim == 2 else sv) > 0)
            ok[max(0, max_nodes - (count - base)):] = False
            tip_node, new_pos, tip_dir, c = tip_node[ok], new_pos[ok], tip_dir[ok], c[ok]
            new_idx = count + np.arange(len(c))
            xyz.append(new_pos.astype(np.float32))
            parent.append(tip_node)
            cell_of.append(cells[c])
            compart.append(np.full(len(c), comp, np.int64))
            count += len(c)
            br = rng.random(len(c)) < branch_p[c]
            br_dir = _rotate(tip_dir[br], branch_a[c[br]], rng)
            tip_node = np.concatenate([new_idx, new_idx[br]])
            tip_pos = np.concatenate([new_pos, new_pos[br]])
            tip_dir = np.concatenate([tip_dir, br_dir])
            tip_cell_local = np.concatenate([c, c[br]])

        # parents of the new nodes are global indices (soma nodes and new nodes are numbered from `base`)
        merged = ArborStore(np.concatenate([store.xyz] + xyz),
                            np.concatenate([store.radius, np.full(count - base, soma_r, np.float32)]),
                            np.concatenate([store.parent] + parent), np.concatenate([store.compartment] + compart),
                            np.concatenate([store.cell] + cell_of), dict(store.labels))
        if np.any(retract_p > 0):
            nc = merged.children_count()
            idx = np.arange(merged.n_nodes)
            local = np.full(len(tissue.alive), -1)
            local[cells] = np.arange(len(cells))
            terminal = (idx >= base) & (nc == 0) & (merged.compartment == comp)
            rp = np.where(local[merged.cell] >= 0, retract_p[np.maximum(local[merged.cell], 0)], 0.0)
            drop = terminal & (rng.random(merged.n_nodes) < rp)
            merged = merged.take(~drop)
        tissue.morphology = merged
        return tissue


@register_stage("arbor_synapses")
class ArborSynapses:
    """Synapses where axonal nodes of one cell come within `contact_distance` of dendritic nodes of another
    (Peters' rule: potential synapses from geometric proximity; Peters & Feldman 1976, J Neurocytol).

    Candidate (pre node, post node) pairs come from the cell list over arbor nodes (O(nodes)); each becomes a synapse
    with probability `p_contact`, keeping at most `max_per_pair` (closest first) per (pre cell, post cell). Pre nodes
    have a compartment in `pre_compartments` (default axon, neurite), post nodes one in `post_compartments` (default
    dendrite, neurite, soma). Delay = round(axonal path length from the pre soma / `axon_velocity` + dendritic path
    length to the post soma / `dendrite_velocity` (ignored if absent)), clipped to [1, 31] ticks with a counted
    warning. Weight `weight` with the presynaptic sign (`dale`, default True). Synapses record `pre_node`, `post_node`,
    `path_length` (axonal) and `dendritic_distance`. No arbors or no `contact_distance` is the no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        nodes = int(worst_case(params.get("expected_nodes"), N * 50))
        cl_bytes, cl_ops = CellList.declared_cost(nodes, nodes, _MEAN_CONTACTS)
        return int(cl_bytes + nodes * _MEAN_CONTACTS * 40 + nodes * 40), int(cl_ops + nodes * _MEAN_CONTACTS * 20)

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        m = tissue.morphology
        if m is None or m.n_nodes == 0 or params.get("contact_distance") is None:
            return tissue
        r = float(resolve(params["contact_distance"], genome, fields))
        if r <= 0:
            return tissue
        comps = lambda k, d: [compartment_id(c) for c in resolve(params.get(k, d), genome, fields)]
        alive_node = tissue.alive[m.cell]
        pre_nodes = np.flatnonzero(np.isin(m.compartment, comps("pre_compartments", ["axon", "neurite"])) & alive_node)
        post_nodes = np.flatnonzero(np.isin(m.compartment, comps("post_compartments", ["dendrite", "neurite", "soma"])) & alive_node)
        if len(pre_nodes) == 0 or len(post_nodes) == 0:
            return tissue
        q, k, dist = CellList(m.xyz[post_nodes].astype(np.float64), r).query_radius(m.xyz[pre_nodes].astype(np.float64), r,
                                                                                     return_distances=True)
        a, b = pre_nodes[q], post_nodes[k]
        pre_c, post_c = m.cell[a], m.cell[b]
        keep = (pre_c != post_c) if not bool(resolve(params.get("allow_autapse", False), genome, fields)) else np.ones(len(a), bool)
        keep &= rng.random(len(a)) < float(resolve(params.get("p_contact", 1.0), genome, fields))
        a, b, dist, pre_c, post_c = a[keep], b[keep], dist[keep], pre_c[keep], post_c[keep]
        max_pp = int(resolve(params.get("max_per_pair", 1), genome, fields))
        N = len(tissue.alive)
        pair = pre_c.astype(np.int64) * N + post_c
        o = np.lexsort((dist, pair))
        a, b, dist, pre_c, post_c, pair = a[o], b[o], dist[o], pre_c[o], post_c[o], pair[o]
        first = np.r_[True, pair[1:] != pair[:-1]]
        start = np.maximum.accumulate(np.where(first, np.arange(len(pair)), 0))
        rank = np.arange(len(pair)) - start
        sel = rank < max_pp
        a, b, pre_c, post_c = a[sel], b[sel], pre_c[sel], post_c[sel]
        plen = m.path_length_to_root()
        axon_len, dend_len = plen[a], plen[b]
        v_ax = float(resolve(params.get("axon_velocity", 1.0), genome, fields))
        t = axon_len / v_ax
        if params.get("dendrite_velocity") is not None:
            t = t + dend_len / float(resolve(params["dendrite_velocity"], genome, fields))
        delay = np.round(t).astype(np.int64)
        n_clip = int(np.sum(delay > MAX_DELAY))
        if n_clip:
            warnings.warn(f"arbor_synapses: {n_clip} synapses clipped to maximum delay {MAX_DELAY} ticks (kernel limit)",
                          UserWarning, stacklevel=3)
        delay = np.clip(delay, 1, MAX_DELAY)
        w = np.full(len(a), int(resolve(params.get("weight", 1), genome, fields)), np.int32)
        if bool(resolve(params.get("dale", True), genome, fields)):
            w = np.abs(w) * np.where(tissue.sign[pre_c] < 0, -1, 1).astype(np.int32)
        tissue.connectivity = tissue.connectivity.append(
            pre_c, post_c, w, delay, pre_node=a.astype(np.int32), post_node=b.astype(np.int32),
            path_length=axon_len.astype(np.float32), dendritic_distance=dend_len.astype(np.float32))
        return tissue
