"""SONATA network files: writer and reader (roadmap task J2).

SONATA (Dai et al. 2020, PLoS Comput Biol 16:e1007696) stores nodes and edges in HDF5 with CSV type tables and a JSON
circuit config; BMTK, NEST (via BMTK PointNet), NEURON and libsonata read it. Layout written here, checked against the
SONATA developer guide and BMTK's example circuits::

    <dir>/circuit_config.json
    <dir>/network/nodes.h5        /nodes/<pop>/{node_id, node_type_id, node_group_id, node_group_index}
                                  /nodes/<pop>/0/{x, y, z, ngs_*}, /nodes/<pop>/0/dynamics_params/<NEST iaf_psc_exp>
    <dir>/network/edges.h5        /edges/<pop>_to_<pop>/{source_node_id, target_node_id, edge_type_id, ...}
                                  /edges/<pop>_to_<pop>/0/{syn_weight (pA), delay (ms), ngs_weight, ngs_delay}
                                  /edges/<pop>_to_<pop>/indices/{source_to_target, target_to_source}/...
    <dir>/network/node_types.csv, edge_types.csv
    <dir>/components/point_neuron_models/*.json, synaptic_models/static_synapse.json

One population, one attribute group "0" (libsonata reads only that). Simulator-facing values (positions, NEST
`iaf_psc_exp` parameters, weights in pA, delays in ms) follow `neurogenesis.interop.dynamics`; every toolbox field is
also stored raw (`ngs_*`), so that reading a file written here gives back the same network exactly. Files from other
tools are read through their positions, NEST-style dynamics parameters, weights and delays.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..spiking.network import NeuronData, SNNNetwork, SynapseData
from .core import ExportReport, register_format, require
from .dynamics import (APPROXIMATION, DEFAULT_C_M, DEFAULT_E_L, DEFAULT_MV_PER_UNIT, delay_ms, delay_ticks, lif_params,
                       shift_from_tau)

MAGIC = 0x0A7A
VERSION = (0, 1)
_INT_FIELDS = ("mode", "shift_v", "shift_s", "base_weight", "burst_period", "burst_duty", "refractory", "role",
               "compartment", "threshold")
_FLOAT_FIELDS = ("poisson_hz", "conn_radius", "conn_prob")
_MODE_NAMES = {0: "lif", 1: "poisson_driver", 2: "burster"}


def _root_attrs(f):
    f.attrs["magic"] = np.uint32(MAGIC)
    f.attrs["version"] = np.asarray(VERSION, np.uint32)


def _write_indices(group, ids, n_nodes):
    """SONATA indices: node_id_to_ranges[n] -> rows of range_to_edge_id, each an edge-id range [start, end)."""
    order = np.argsort(ids, kind="stable")
    sorted_ids = ids[order]
    edge_ids = order                      # a range = consecutive edge ids of the same node
    new_range = np.ones(len(ids), bool)
    if len(ids):
        new_range[1:] = (sorted_ids[1:] != sorted_ids[:-1]) | (edge_ids[1:] != edge_ids[:-1] + 1)
    starts = np.flatnonzero(new_range)
    ends = np.concatenate([starts[1:], [len(ids)]]).astype(np.int64)
    range_to_edge = np.stack([edge_ids[starts], edge_ids[ends - 1] + 1], axis=1).astype(np.uint64) if len(ids) \
        else np.zeros((0, 2), np.uint64)
    node_to_ranges = np.zeros((n_nodes, 2), np.uint64)
    if len(ids):
        range_node = sorted_ids[starts]
        first = np.searchsorted(range_node, np.arange(n_nodes), side="left")
        last = np.searchsorted(range_node, np.arange(n_nodes), side="right")
        node_to_ranges[:, 0], node_to_ranges[:, 1] = first, last
    group.create_dataset("node_id_to_ranges", data=node_to_ranges)
    group.create_dataset("range_to_edge_id", data=range_to_edge.reshape(-1, 2))


def export_sonata(net: SNNNetwork, path: Path, population: str = "ngs", mV_per_unit: float = DEFAULT_MV_PER_UNIT,
                  E_L: float = DEFAULT_E_L, C_m: float = DEFAULT_C_M) -> ExportReport:
    """Write `net` as a SONATA circuit in directory `path`; returns the export report."""
    h5py = require("h5py", "sonata")
    path = Path(path)
    (path / "network").mkdir(parents=True, exist_ok=True)
    models = path / "components" / "point_neuron_models"
    models.mkdir(parents=True, exist_ok=True)
    (path / "components" / "synaptic_models").mkdir(parents=True, exist_ok=True)

    neurons = net.neurons
    n = len(neurons)
    params = [lif_params(nd, mV_per_unit, E_L, C_m) for nd in neurons]
    mode = np.asarray([nd.mode for nd in neurons], np.int64)
    pre = np.asarray([s.pre for s in net.synapses], np.int64)
    post = np.asarray([s.post for s in net.synapses], np.int64)
    w = np.asarray([s.weight for s in net.synapses], np.int64)
    d = np.asarray([s.delay for s in net.synapses], np.int64)
    mapping = dict(mV_per_unit=mV_per_unit, E_L=E_L, C_m=C_m, space_unit="toolbox space units", tick_ms=1.0)

    with h5py.File(path / "network" / "nodes.h5", "w") as f:
        _root_attrs(f)
        f.attrs["neurogenesis_mapping"] = json.dumps(mapping)
        g = f.create_group(f"nodes/{population}")
        g.create_dataset("node_id", data=np.arange(n, dtype=np.uint64))
        g.create_dataset("node_type_id", data=(100 + mode).astype(np.uint64))
        g.create_dataset("node_group_id", data=np.zeros(n, np.uint32))
        g.create_dataset("node_group_index", data=np.arange(n, dtype=np.uint64))
        g0 = g.create_group("0")
        for k in ("x", "y", "z", "dir_x", "dir_y", "dir_z"):
            g0.create_dataset(k if k in ("x", "y", "z") else f"ngs_{k}",
                              data=np.asarray([getattr(nd, k) for nd in neurons], np.float64))
        for k in _INT_FIELDS:
            g0.create_dataset(f"ngs_{k}", data=np.asarray([getattr(nd, k) for nd in neurons], np.int64))
        for k in _FLOAT_FIELDS:
            g0.create_dataset(f"ngs_{k}", data=np.asarray([getattr(nd, k) for nd in neurons], np.float64))
        dyn = g0.create_group("dynamics_params")
        nest = [p.nest() for p in params]
        for k in (nest[0] if nest else {}):
            dyn.create_dataset(k, data=np.asarray([p[k] for p in nest], np.float64))

    edge_pop = f"{population}_to_{population}"
    with h5py.File(path / "network" / "edges.h5", "w") as f:
        _root_attrs(f)
        g = f.create_group(f"edges/{edge_pop}")
        g.create_dataset("source_node_id", data=pre.astype(np.uint64)).attrs["node_population"] = population
        g.create_dataset("target_node_id", data=post.astype(np.uint64)).attrs["node_population"] = population
        g.create_dataset("edge_type_id", data=np.full(len(w), 100, np.uint32))
        g.create_dataset("edge_group_id", data=np.zeros(len(w), np.uint16))
        g.create_dataset("edge_group_index", data=np.arange(len(w), dtype=np.uint64))
        g0 = g.create_group("0")
        g0.create_dataset("syn_weight", data=np.asarray([params[t].psc_amplitude(x) for t, x in zip(post, w)], np.float64))
        g0.create_dataset("delay", data=np.asarray([delay_ms(x) for x in d], np.float64))
        g0.create_dataset("ngs_weight", data=w)
        g0.create_dataset("ngs_delay", data=d)
        _write_indices(g.create_group("indices/source_to_target"), pre, n)
        _write_indices(g.create_group("indices/target_to_source"), post, n)

    rows = ["node_type_id model_type model_template dynamics_params pop_name"]
    for m in sorted(set(mode.tolist())):
        first = int(np.flatnonzero(mode == m)[0])
        (models / f"ngs_{_MODE_NAMES[m]}.json").write_text(json.dumps(params[first].nest(), indent=1))
        rows.append(f"{100 + m} point_neuron nest:iaf_psc_exp ngs_{_MODE_NAMES[m]}.json {_MODE_NAMES[m]}")
    (path / "network" / "node_types.csv").write_text("\n".join(rows) + "\n")
    (path / "network" / "edge_types.csv").write_text(
        "edge_type_id model_template dynamics_params\n100 static_synapse static_synapse.json\n")
    (path / "components" / "synaptic_models" / "static_synapse.json").write_text("{}\n")
    config = {"manifest": {"$BASE_DIR": ".", "$NETWORK_DIR": "$BASE_DIR/network", "$MODELS_DIR": "$BASE_DIR/components"},
              "components": {"point_neuron_models_dir": "$MODELS_DIR/point_neuron_models",
                             "synaptic_models_dir": "$MODELS_DIR/synaptic_models"},
              "networks": {"nodes": [{"nodes_file": "$NETWORK_DIR/nodes.h5", "node_types_file": "$NETWORK_DIR/node_types.csv"}],
                           "edges": [{"edges_file": "$NETWORK_DIR/edges.h5", "edge_types_file": "$NETWORK_DIR/edge_types.csv"}]},
              "neurogenesis": {"population": population, "morphology": net.morphology, "version": net.version, **mapping}}
    (path / "circuit_config.json").write_text(json.dumps(config, indent=1) + "\n")

    report = ExportReport("sonata", str(path), counts=dict(nodes=n, edges=len(w)),
                          exact=["neuron and synapse fields (ngs_* attributes, read back exactly by this toolbox)",
                                 "positions x, y, z", "connectivity", "sign of weights"])
    report.approximated["neuron dynamics, syn_weight, delay"] = APPROXIMATION
    if (mode != 0).any():
        report.approximated["drivers"] = (f"{int((mode == 1).sum())} Poisson and {int((mode == 2).sum())} burster "
                                          "neurons are written as iaf_psc_exp nodes (node types poisson_driver / "
                                          "burster, rates in ngs_poisson_hz); their spontaneous spikes are not "
                                          "generated by other simulators")
    report.dropped["integer arithmetic"] = "rounding, minimum decrement and the +-2048 clamp exist only in this toolbox"
    return report


def _resolve(config_dir: Path, value: str, manifest: dict) -> Path:
    for _ in range(4):
        for k, v in manifest.items():
            value = value.replace(k, v)
    return (config_dir / value).resolve()


def import_sonata(path: Path, population: str | None = None, mV_per_unit: float = DEFAULT_MV_PER_UNIT) -> SNNNetwork:
    """Read a SONATA circuit (a directory holding circuit_config.json, or the config file itself).

    Files written by `export_sonata` give back the original network exactly. For other files, each neuron gets the
    shifts closest to its tau_m / tau_syn, threshold 1024 (the voltage scale is set per neuron from V_th - E_L), its
    refractory period in ticks, and weights and delays through the inverse of the shared mapping; missing dynamics
    parameters keep the toolbox defaults."""
    h5py = require("h5py", "sonata")
    path = Path(path)
    cfg_path = path / "circuit_config.json" if path.is_dir() else path
    cfg = json.loads(cfg_path.read_text())
    manifest = cfg.get("manifest", {})
    nodes_file = _resolve(cfg_path.parent, cfg["networks"]["nodes"][0]["nodes_file"], manifest)
    edges_files = [_resolve(cfg_path.parent, e["edges_file"], manifest) for e in cfg["networks"].get("edges", [])]

    with h5py.File(nodes_file, "r") as f:
        pop = population or sorted(f["nodes"].keys())[0]
        g = f[f"nodes/{pop}"]
        n = len(g["node_type_id"])
        if "node_group_id" in g and np.any(g["node_group_id"][()] != 0):
            raise ValueError("only single-group SONATA populations (group '0') are supported, as in libsonata")
        g0 = g["0"]
        col = {k: g0[k][()] for k in g0.keys() if isinstance(g0[k], h5py.Dataset)}
        dyn = {k: g0["dynamics_params"][k][()] for k in g0["dynamics_params"].keys()} if "dynamics_params" in g0 else {}
    exact = "ngs_mode" in col

    def column(k, default):
        return col[k] if k in col else np.full(n, default)

    neurons = []
    scale = np.full(n, mV_per_unit)
    for i in range(n):
        kw = dict(id=i, x=float(column("x", 0.0)[i]), y=float(column("y", 0.0)[i]), z=float(column("z", 0.0)[i]))
        if exact:
            kw.update(dir_x=float(col["ngs_dir_x"][i]), dir_y=float(col["ngs_dir_y"][i]), dir_z=float(col["ngs_dir_z"][i]))
            kw.update({k: int(col[f"ngs_{k}"][i]) for k in _INT_FIELDS})
            kw.update({k: float(col[f"ngs_{k}"][i]) for k in _FLOAT_FIELDS})
        else:
            kw.update(dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0)
            if "tau_m" in dyn:
                kw["shift_v"] = shift_from_tau(float(dyn["tau_m"][i]))
            if "tau_syn_ex" in dyn:
                kw["shift_s"] = shift_from_tau(float(dyn["tau_syn_ex"][i]))
            if "t_ref" in dyn:
                kw["refractory"] = int(round(float(dyn["t_ref"][i])))
            if "V_th" in dyn and "E_L" in dyn:
                scale[i] = (float(dyn["V_th"][i]) - float(dyn["E_L"][i])) / 1024.0
        neurons.append(NeuronData(**kw))

    synapses = []
    for ef in edges_files:
        with h5py.File(ef, "r") as f:
            for name, g in f["edges"].items():
                if g["source_node_id"].attrs.get("node_population", pop) != pop or \
                   g["target_node_id"].attrs.get("node_population", pop) != pop:
                    continue
                src, tgt = g["source_node_id"][()].astype(np.int64), g["target_node_id"][()].astype(np.int64)
                g0 = g["0"]
                if exact and "ngs_weight" in g0:
                    w, d = g0["ngs_weight"][()], g0["ngs_delay"][()]
                else:
                    amp = g0["syn_weight"][()] if "syn_weight" in g0 else np.ones(len(src))
                    dl = g0["delay"][()] if "delay" in g0 else np.ones(len(src))
                    C = dyn.get("C_m", np.full(n, DEFAULT_C_M))
                    w, d = [], []
                    for a_, t, x in zip(amp, tgt, dl):
                        p = lif_params(neurons[t], scale[t], 0.0, float(C[t]))
                        w.append(int(round(p.weight_units(float(a_)))))
                        d.append(delay_ticks(float(x)))
                synapses += [SynapseData(pre=int(a), post=int(b), weight=int(c), delay=int(e))
                             for a, b, c, e in zip(src, tgt, w, d)]
    meta = cfg.get("neurogenesis", {})
    return SNNNetwork(version=meta.get("version", "1.0.0"), morphology=meta.get("morphology", f"SONATA {pop}"),
                      neurons=neurons, synapses=synapses)


register_format("sonata", export=export_sonata, import_=import_sonata, extra="sonata",
                description="SONATA nodes/edges HDF5 + CSV + circuit config (BMTK, NEST, NEURON, libsonata)")
