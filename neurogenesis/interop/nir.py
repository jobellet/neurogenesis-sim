"""NIR (Neuromorphic Intermediate Representation) exporter and importer (roadmap task J3).

NIR (Pedersen et al. 2024, Nat Commun 15:8122; `pip install nir`) defines a standard graph representation
for neuromorphic hardware and simulators (snnTorch, Norse, Lava-DL, SpiNNaker2, etc.).

This module maps the integer LIF neuron into NIR CubaLIF nodes with dense Linear recurrent weights.
Because NIR has no native refractory period, no per-synapse delays, and no sparse connectivity primitive,
delays and refractoriness are reported as approximated in ExportReport, driver neurons (Poisson / burster)
are reported as dropped or handled via drivers parameter, and the integration time step dt is recorded
explicitly in graph metadata.

Dense weight matrices scale as O(N^2), suitable for small circuits and shareable modules (N <= 2048).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np

from ..spiking.network import NeuronData, SNNNetwork, SynapseData
from .core import ExportReport, register_format, require
from .dynamics import (
    APPROXIMATION,
    DEFAULT_C_M,
    DEFAULT_E_L,
    DEFAULT_MV_PER_UNIT,
    lif_params,
    shift_from_tau,
)

_INT_FIELDS = (
    "mode",
    "shift_v",
    "shift_s",
    "base_weight",
    "burst_period",
    "burst_duty",
    "refractory",
    "role",
    "compartment",
    "threshold",
)
_FLOAT_FIELDS = ("poisson_hz", "conn_radius", "conn_prob")


def export_nir(
    net: SNNNetwork,
    path: Union[str, Path],
    population: str = "ngs",
    mV_per_unit: float = DEFAULT_MV_PER_UNIT,
    E_L: float = DEFAULT_E_L,
    C_m: float = DEFAULT_C_M,
    dt: float = 1e-3,
    drivers: str = "keep",
    input_weights: Optional[np.ndarray] = None,
    **opts,
) -> ExportReport:
    """Write an SNNNetwork as an NIR graph file (CubaLIF + dense Linear weights).

    Parameters
    ----------
    net : SNNNetwork
        The spiking neural network to export.
    path : Union[str, Path]
        Output path of the .nir (HDF5) file.
    population : str
        Name of the neuron population (default: 'ngs').
    mV_per_unit : float
        Millivolts per integer voltage unit (default: 15/1024).
    E_L : float
        Resting / leak potential in mV (default: -65.0).
    C_m : float
        Membrane capacitance in pF (default: 250.0).
    dt : float
        Simulation time step in seconds (default: 1e-3, i.e. 1 ms).
    drivers : str
        How to handle driver neurons (mode != 0):
        - 'keep': keep in CubaLIF node, report spontaneous spikes dropped (default).
        - 'drop': omit driver neurons and their synapses from the graph.
        - 'input': convert driver efferent projections to external inputs.
    input_weights : Optional[np.ndarray]
        Optional feedforward input weight matrix connecting input channels to LIF neurons.
    """
    nir = require("nir", "nir")

    if dt <= 0 or not np.isfinite(dt):
        raise ValueError(f"dt must be positive (> 0) and finite, got {dt}")

    if net.num_neurons == 0:
        raise ValueError("cannot export an empty network (0 neurons)")

    if drivers not in ("keep", "drop", "input"):
        raise ValueError(f"unknown drivers mode {drivers!r}; choose 'keep', 'drop', or 'input'")

    lif_neurons = [nd for nd in net.neurons if nd.mode == 0]
    driver_neurons = [nd for nd in net.neurons if nd.mode != 0]
    has_drivers = len(driver_neurons) > 0

    if drivers == "drop":
        neurons = lif_neurons
        if len(neurons) == 0:
            raise ValueError("cannot export an empty network (no LIF neurons present after dropping drivers)")
        driver_ids = {nd.id for nd in driver_neurons}
        candidate_synapses = [
            s for s in net.synapses
            if s.pre not in driver_ids and s.post not in driver_ids
        ]
    elif drivers == "input":
        if has_drivers:
            neurons = lif_neurons
            if len(neurons) == 0:
                raise ValueError("cannot export network: no LIF neurons present when drivers='input'")
            if input_weights is not None:
                raise ValueError(
                    "cannot pass input_weights when drivers='input' and driver neurons are present; "
                    "driver efferents provide input weights"
                )
        else:
            neurons = list(net.neurons)
        candidate_synapses = list(net.synapses)
    else:  # drivers == "keep"
        neurons = list(net.neurons)
        candidate_synapses = list(net.synapses)

    n = len(neurons)
    if n > 2048:
        raise ValueError(f"dense NIR Linear connectivity exceeds low-compute limit (N={n} > 2048)")

    params = [lif_params(nd, mV_per_unit=mV_per_unit, E_L=E_L, C_m=C_m) for nd in neurons]

    # Convert continuous dynamics to SI units (seconds, Volts, V/pA resistance)
    tau_mem = np.asarray([p.tau_m * 1e-3 for p in params], dtype=np.float64)
    tau_syn = np.asarray([p.tau_syn * 1e-3 for p in params], dtype=np.float64)
    r = np.asarray([p.tau_m / (p.C_m * 1e3) for p in params], dtype=np.float64)
    v_leak = np.asarray([p.E_L * 1e-3 for p in params], dtype=np.float64)
    v_threshold = np.asarray([p.V_th * 1e-3 for p in params], dtype=np.float64)
    v_reset = np.asarray([p.V_reset * 1e-3 for p in params], dtype=np.float64)
    w_in = np.ones(n, dtype=np.float64)

    # Store exact toolbox metadata for lossless round trip
    lif_meta = {
        "dt": float(dt),
        "ngs_id": np.asarray([nd.id for nd in neurons], dtype=np.int64),
        "ngs_x": np.asarray([nd.x for nd in neurons], dtype=np.float64),
        "ngs_y": np.asarray([nd.y for nd in neurons], dtype=np.float64),
        "ngs_z": np.asarray([nd.z for nd in neurons], dtype=np.float64),
        "ngs_dir_x": np.asarray([nd.dir_x for nd in neurons], dtype=np.float64),
        "ngs_dir_y": np.asarray([nd.dir_y for nd in neurons], dtype=np.float64),
        "ngs_dir_z": np.asarray([nd.dir_z for nd in neurons], dtype=np.float64),
    }
    for k in _INT_FIELDS:
        lif_meta[f"ngs_{k}"] = np.asarray([getattr(nd, k) for nd in neurons], dtype=np.int64)
    for k in _FLOAT_FIELDS:
        lif_meta[f"ngs_{k}"] = np.asarray([getattr(nd, k) for nd in neurons], dtype=np.float64)

    cuba_node = nir.CubaLIF(
        tau_mem=tau_mem,
        tau_syn=tau_syn,
        r=r,
        v_leak=v_leak,
        v_threshold=v_threshold,
        v_reset=v_reset,
        w_in=w_in,
        metadata=lif_meta,
    )

    lif_id_to_idx = {nd.id: i for i, nd in enumerate(neurons)}
    nodes = {}
    edges = []

    # Segregate synapses into recurrent, driver efferents, dropped driver afferents, and dangling
    driver_efferent_synapses = []
    dropped_driver_afferents = []
    dangling_synapses = []
    rec_synapses = []

    if drivers == "input" and has_drivers:
        driver_id_to_idx = {nd.id: k for k, nd in enumerate(driver_neurons)}
        for s in candidate_synapses:
            pre_in_lif = s.pre in lif_id_to_idx
            post_in_lif = s.post in lif_id_to_idx
            pre_in_driver = s.pre in driver_id_to_idx
            post_in_driver = s.post in driver_id_to_idx

            if pre_in_lif and post_in_lif:
                rec_synapses.append(s)
            elif pre_in_driver and post_in_lif:
                driver_efferent_synapses.append(s)
            elif post_in_driver:
                dropped_driver_afferents.append(s)
            else:
                dangling_synapses.append(s)

        K = len(driver_neurons)
        W_in = np.zeros((n, K), dtype=np.float64)
        for s in driver_efferent_synapses:
            post_idx = lif_id_to_idx[s.post]
            driver_idx = driver_id_to_idx[s.pre]
            amp = params[post_idx].psc_amplitude(s.weight)
            W_in[post_idx, driver_idx] += amp

        in_meta = {
            "ngs_driver_id": np.asarray([nd.id for nd in driver_neurons], dtype=np.int64),
            "ngs_pre": np.asarray([s.pre for s in driver_efferent_synapses], dtype=np.int64),
            "ngs_post": np.asarray([s.post for s in driver_efferent_synapses], dtype=np.int64),
            "ngs_weight": np.asarray([s.weight for s in driver_efferent_synapses], dtype=np.int64),
            "ngs_delay": np.asarray([s.delay for s in driver_efferent_synapses], dtype=np.int64),
        }
        nodes["input"] = nir.Input(input_type=np.array([K]))
        nodes["input_linear"] = nir.Linear(weight=W_in, metadata=in_meta)
        edges.append(("input", "input_linear"))
        edges.append(("input_linear", "lif"))
    else:
        for s in candidate_synapses:
            if s.pre in lif_id_to_idx and s.post in lif_id_to_idx:
                rec_synapses.append(s)
            else:
                dangling_synapses.append(s)

        if input_weights is not None:
            w_in_arr = np.asarray(input_weights, dtype=np.float64)
            if w_in_arr.ndim == 1:
                if len(w_in_arr) == n:
                    W_in = w_in_arr.reshape(n, 1)
                elif n == 1:
                    W_in = w_in_arr.reshape(1, -1)
                else:
                    raise ValueError(
                        f"1D input_weights length ({len(w_in_arr)}) does not match neuron count ({n})"
                    )
            elif w_in_arr.ndim == 2:
                if w_in_arr.shape[0] != n:
                    raise ValueError(
                        f"input_weights rows ({w_in_arr.shape[0]}) must match neuron count ({n})"
                    )
                W_in = w_in_arr
            else:
                raise ValueError(
                    f"input_weights must be 1D or 2D, got shape {w_in_arr.shape}"
                )

            input_dim = int(W_in.shape[1])
            nodes["input"] = nir.Input(input_type=np.array([input_dim]))
            nodes["input_linear"] = nir.Linear(weight=W_in)
            edges.append(("input", "input_linear"))
            edges.append(("input_linear", "lif"))
        else:
            nodes["input"] = nir.Input(input_type=np.array([n]))
            edges.append(("input", "lif"))

    nodes["lif"] = cuba_node
    nodes["output"] = nir.Output(output_type=np.array([n]))
    edges.append(("lif", "output"))

    if len(rec_synapses) > 0:
        W_rec = np.zeros((n, n), dtype=np.float64)
        for s in rec_synapses:
            pre_idx = lif_id_to_idx[s.pre]
            post_idx = lif_id_to_idx[s.post]
            amp = params[post_idx].psc_amplitude(s.weight)
            W_rec[post_idx, pre_idx] += amp

        rec_meta = {
            "ngs_pre": np.asarray([s.pre for s in rec_synapses], dtype=np.int64),
            "ngs_post": np.asarray([s.post for s in rec_synapses], dtype=np.int64),
            "ngs_weight": np.asarray([s.weight for s in rec_synapses], dtype=np.int64),
            "ngs_delay": np.asarray([s.delay for s in rec_synapses], dtype=np.int64),
        }
        nodes["recurrent"] = nir.Linear(weight=W_rec, metadata=rec_meta)
        edges.append(("lif", "recurrent"))
        edges.append(("recurrent", "lif"))

    graph_meta = {
        "dt": float(dt),
        "tick_ms": 1.0,
        "space_unit": "toolbox space units",
        "population": population,
        "mV_per_unit": float(mV_per_unit),
        "E_L": float(E_L),
        "C_m": float(C_m),
        "version": net.version,
        "morphology": net.morphology,
    }

    graph = nir.NIRGraph(nodes=nodes, edges=edges, metadata=graph_meta)

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nir.write(out_path, graph)

    total_exported_edges = len(rec_synapses) + len(driver_efferent_synapses)

    exact = ["neurons"]
    if total_exported_edges > 0 and len(dangling_synapses) == 0 and len(dropped_driver_afferents) == 0 and drivers != "drop":
        exact.append("synapses")

    approximated = {
        "neuron dynamics, syn_weight, delay": APPROXIMATION,
    }

    all_exported_synapses = rec_synapses + driver_efferent_synapses
    if len(all_exported_synapses) > 0:
        if any(s.delay > 0 for s in all_exported_synapses):
            approximated["delays"] = (
                "per-synapse delays are not supported in NIR; delays are not represented in the weight graph"
            )
        else:
            approximated["delays"] = (
                "synaptic transmission latency (1 tick in integer kernel) is not represented in NIR Linear edges"
            )

    if any(nd.refractory > 0 for nd in net.neurons if nd.mode == 0):
        approximated["refractory"] = (
            "refractory period is not supported in NIR CubaLIF and is not simulated"
        )

    dropped = {
        "integer arithmetic": (
            "discrete bitshift updates, minimum decrements, and [-2048, 2048] voltage clamping are not simulated in continuous CubaLIF ODE"
        ),
    }

    if has_drivers:
        if drivers == "drop":
            dropped["drivers"] = (
                f"{len(driver_neurons)} Poisson and burster driver neurons and their synapses were dropped from the graph"
            )
        elif drivers == "input":
            approximated["drivers"] = (
                f"{len(driver_neurons)} driver neurons converted to external input channels; "
                "spontaneous spike generation must be driven externally"
            )
        else:  # drivers == "keep"
            dropped["drivers"] = (
                "Poisson and burster neurons have no NIR equivalent and their spontaneous spikes are dropped"
            )

    if len(dropped_driver_afferents) > 0:
        dropped["driver_afferents"] = (
            f"{len(dropped_driver_afferents)} synapses ending on driver neurons dropped; "
            "external input channels cannot receive synaptic feedback"
        )

    if len(dangling_synapses) > 0:
        dropped["dangling_synapses"] = (
            f"{len(dangling_synapses)} synapses referenced nonexistent neuron IDs and were dropped"
        )

    report = ExportReport(
        format="nir",
        path=str(out_path),
        exact=exact,
        approximated=approximated,
        dropped=dropped,
        counts={"nodes": len(neurons), "edges": total_exported_edges},
    )
    return report


def import_nir(
    path: Union[str, Path],
    population: str = "ngs",
    mV_per_unit: Optional[float] = None,
    **opts,
) -> SNNNetwork:
    """Read a network written in NIR format (exact if metadata present, generic inverse mapping otherwise)."""
    nir = require("nir", "nir")
    path = Path(path)
    graph = nir.read(path)

    cuba = graph.nodes.get("lif")
    if cuba is None:
        for node in graph.nodes.values():
            if isinstance(node, nir.CubaLIF):
                cuba = node
                break
    if cuba is None:
        raise ValueError("no CubaLIF node found in NIR graph")

    n = len(cuba.v_threshold)
    meta = cuba.metadata or {}
    graph_meta = graph.metadata or {}
    exact = "ngs_mode" in meta

    neurons = []
    if exact:
        for i in range(n):
            kw = dict(
                id=int(meta["ngs_id"][i]) if "ngs_id" in meta else i,
                x=float(meta["ngs_x"][i]) if "ngs_x" in meta else 0.0,
                y=float(meta["ngs_y"][i]) if "ngs_y" in meta else 0.0,
                z=float(meta["ngs_z"][i]) if "ngs_z" in meta else 0.0,
                dir_x=float(meta["ngs_dir_x"][i]) if "ngs_dir_x" in meta else 1.0,
                dir_y=float(meta["ngs_dir_y"][i]) if "ngs_dir_y" in meta else 0.0,
                dir_z=float(meta["ngs_dir_z"][i]) if "ngs_dir_z" in meta else 0.0,
            )
            for k in _INT_FIELDS:
                if f"ngs_{k}" in meta:
                    kw[k] = int(meta[f"ngs_{k}"][i])
            for k in _FLOAT_FIELDS:
                if f"ngs_{k}" in meta:
                    kw[k] = float(meta[f"ngs_{k}"][i])
            neurons.append(NeuronData(**kw))
    else:
        for i in range(n):
            tau_m = float(cuba.tau_mem[i]) * 1e3
            tau_syn = float(cuba.tau_syn[i]) * 1e3
            shift_v = shift_from_tau(tau_m)
            shift_s = shift_from_tau(tau_syn)
            neurons.append(NeuronData(
                id=i,
                x=0.0,
                y=0.0,
                z=0.0,
                dir_x=1.0,
                dir_y=0.0,
                dir_z=0.0,
                mode=0,
                shift_v=shift_v,
                shift_s=shift_s,
                threshold=1024,
                refractory=0,
            ))

    synapses = []
    rec = graph.nodes.get("recurrent")
    if rec is None:
        for k, v in graph.nodes.items():
            if isinstance(v, (nir.Linear, nir.Affine)) and k != "input_linear":
                rec = v
                break

    if rec is not None:
        rec_meta = rec.metadata or {}
        if exact and "ngs_pre" in rec_meta:
            pre = rec_meta["ngs_pre"]
            post = rec_meta["ngs_post"]
            weight = rec_meta["ngs_weight"]
            delay = rec_meta["ngs_delay"]
            synapses = [
                SynapseData(pre=int(p), post=int(q), weight=int(w), delay=int(d))
                for p, q, w, d in zip(pre, post, weight, delay)
            ]
        elif hasattr(rec, "weight"):
            W = rec.weight
            C_m = float(graph_meta.get("C_m", DEFAULT_C_M))
            E_L = float(graph_meta.get("E_L", DEFAULT_E_L))
            eff_mV = (
                float(mV_per_unit)
                if mV_per_unit is not None
                else float(graph_meta.get("mV_per_unit", DEFAULT_MV_PER_UNIT))
            )
            id_map = [nd.id for nd in neurons]
            post_indices, pre_indices = np.nonzero(W)
            for post_idx, pre_idx in zip(post_indices, pre_indices):
                w_val = float(W[post_idx, pre_idx])
                p = lif_params(neurons[post_idx], mV_per_unit=eff_mV, E_L=E_L, C_m=C_m)
                w_units = int(round(p.weight_units(w_val)))
                synapses.append(SynapseData(
                    pre=id_map[pre_idx],
                    post=id_map[post_idx],
                    weight=w_units,
                    delay=0,
                ))

    version = str(graph_meta.get("version", "1.0.0"))
    morphology = str(graph_meta.get("morphology", f"NIR {population}"))
    return SNNNetwork(
        version=version,
        morphology=morphology,
        neurons=neurons,
        synapses=synapses,
    )


register_format(
    "nir",
    export=export_nir,
    import_=import_nir,
    extra="nir",
    description="NIR (Neuromorphic Intermediate Representation) CubaLIF + dense Linear graph",
)
