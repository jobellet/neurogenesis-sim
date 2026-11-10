"""NIR (Neuromorphic Intermediate Representation) exporter tests (roadmap task J3).

Covers:
- Export of single neuron, two neurons feedforward, recurrent circuits, inhibitory synapses.
- Approximations (delays, refractoriness) and dropped elements (drivers) in ExportReport.
- Graph round-trip reading and lossless network reconstruction via import_network.
- Error behavior when nir is not installed.
- Error behavior for degenerate networks (0 neurons).
- CLI integration: python -m neurogenesis export <net.json> --format nir --out <circuit.nir>.
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

nir = pytest.importorskip("nir")

from neurogenesis.interop import (
    ExportReport,
    export_network,
    formats,
    import_network,
    lif_params,
)
from neurogenesis.interop.nir import export_nir, import_nir
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData


def _make_neuron(i: int = 0, **kw) -> NeuronData:
    defaults = dict(
        id=i,
        x=0.0,
        y=0.0,
        z=0.0,
        dir_x=1.0,
        dir_y=0.0,
        dir_z=0.0,
        mode=0,
        shift_v=4,
        shift_s=2,
        threshold=1024,
        refractory=0,
    )
    defaults.update(kw)
    return NeuronData(**defaults)


def test_nir_registered_in_formats():
    """Verify nir is present in formats()."""
    assert "nir" in formats()


def test_single_neuron_export_nir(tmp_path):
    """Single isolated neuron exports valid CubaLIF node with matching continuous parameters."""
    net = SNNNetwork(neurons=[_make_neuron(0)])
    out_path = tmp_path / "single.nir"
    rep = export_network(net, "nir", out_path)

    assert rep.format == "nir"
    assert rep.counts == {"nodes": 1, "edges": 0}
    assert rep.exact == ["neurons"]
    assert rep.lossless is False
    assert out_path.exists()

    graph = nir.read(out_path)
    assert isinstance(graph, nir.NIRGraph)
    assert set(graph.nodes.keys()) == {"input", "lif", "output"}
    assert graph.edges == [("input", "lif"), ("lif", "output")]

    cuba = graph.nodes["lif"]
    assert isinstance(cuba, nir.CubaLIF)
    p = lif_params(net.neurons[0])
    assert np.isclose(cuba.tau_mem[0], p.tau_m * 1e-3)
    assert np.isclose(cuba.tau_syn[0], p.tau_syn * 1e-3)
    assert np.isclose(cuba.v_threshold[0], p.V_th * 1e-3)
    assert np.isclose(cuba.v_reset[0], p.V_reset * 1e-3)
    assert np.isclose(cuba.v_leak[0], p.E_L * 1e-3)


def test_two_neurons_feedforward_export_nir(tmp_path):
    """Two neurons with feedforward synapse export Linear weight node."""
    net = SNNNetwork(
        neurons=[_make_neuron(0), _make_neuron(1)],
        synapses=[SynapseData(pre=0, post=1, weight=400, delay=0)],
    )
    out_path = tmp_path / "feedforward.nir"
    rep = export_network(net, "nir", out_path)

    assert rep.counts == {"nodes": 2, "edges": 1}
    assert "neurons" in rep.exact
    assert "synapses" in rep.exact

    graph = nir.read(out_path)
    assert "recurrent" in graph.nodes
    lin = graph.nodes["recurrent"]
    assert isinstance(lin, (nir.Linear, nir.Affine))
    assert lin.weight.shape == (2, 2)

    # Post neuron is 1, Pre neuron is 0 -> weight matrix row 1, col 0
    p = lif_params(net.neurons[1])
    expected_amp = p.psc_amplitude(400)
    assert lin.weight[1, 0] > 0
    assert np.isclose(lin.weight[1, 0], expected_amp)
    assert lin.weight[0, 1] == 0.0
    assert lin.weight[0, 0] == 0.0
    assert lin.weight[1, 1] == 0.0


def test_recurrent_network_export_nir(tmp_path):
    """Recurrent network exports cyclic edges and correctly signed matrix elements."""
    net = SNNNetwork(
        neurons=[_make_neuron(0), _make_neuron(1)],
        synapses=[
            SynapseData(pre=0, post=1, weight=300, delay=0),
            SynapseData(pre=1, post=0, weight=-250, delay=0),
        ],
    )
    out_path = tmp_path / "recurrent.nir"
    rep = export_network(net, "nir", out_path)
    assert rep.counts == {"nodes": 2, "edges": 2}

    graph = nir.read(out_path)
    lin = graph.nodes["recurrent"]
    assert lin.weight[1, 0] > 0.0  # excitatory 0 -> 1
    assert lin.weight[0, 1] < 0.0  # inhibitory 1 -> 0

    edges = set(graph.edges)
    assert ("lif", "recurrent") in edges
    assert ("recurrent", "lif") in edges


def test_inhibitory_synapse_negative_weight(tmp_path):
    """Inhibitory synapse with negative integer weight yields negative weight in Linear."""
    net = SNNNetwork(
        neurons=[_make_neuron(0), _make_neuron(1)],
        synapses=[SynapseData(pre=0, post=1, weight=-500, delay=0)],
    )
    out_path = tmp_path / "inh.nir"
    export_network(net, "nir", out_path)
    graph = nir.read(out_path)
    assert graph.nodes["recurrent"].weight[1, 0] < 0.0


def test_network_with_drivers_reported_dropped(tmp_path):
    """Drivers (mode != 0) cannot run autonomously in CubaLIF and are reported dropped."""
    net = SNNNetwork(
        neurons=[_make_neuron(0, mode=0), _make_neuron(1, mode=1, poisson_hz=40.0)],
        synapses=[SynapseData(pre=1, post=0, weight=200, delay=0)],
    )
    rep = export_network(net, "nir", tmp_path / "drivers.nir")
    assert not rep.lossless
    assert "drivers" in rep.dropped


def test_network_with_delays_reported_approximated(tmp_path):
    """Synapses with delay > 0 are reported approximated."""
    net = SNNNetwork(
        neurons=[_make_neuron(0), _make_neuron(1)],
        synapses=[SynapseData(pre=0, post=1, weight=200, delay=5)],
    )
    rep = export_network(net, "nir", tmp_path / "delays.nir")
    assert not rep.lossless
    assert "delays" in rep.approximated


def test_network_with_refractory_reported_approximated(tmp_path):
    """Neurons with refractory period > 0 are reported approximated."""
    net = SNNNetwork(
        neurons=[_make_neuron(0, refractory=4), _make_neuron(1)],
    )
    rep = export_network(net, "nir", tmp_path / "refractory.nir")
    assert not rep.lossless
    assert "refractory" in rep.approximated


def test_time_step_dt_serialized(tmp_path):
    """Explicit dt is saved into graph/node metadata."""
    net = SNNNetwork(neurons=[_make_neuron(0)])
    out_path = tmp_path / "dt.nir"
    export_network(net, "nir", out_path, dt=2e-3)
    graph = nir.read(out_path)
    dt_val = graph.metadata.get("dt") or graph.nodes["lif"].metadata.get("dt")
    assert np.isclose(float(dt_val), 2e-3)


def test_empty_network_raises_value_error(tmp_path):
    """Networks with 0 neurons raise ValueError."""
    net = SNNNetwork(neurons=[])
    with pytest.raises(ValueError, match="0 neurons"):
        export_network(net, "nir", tmp_path / "empty.nir")


def test_missing_nir_dependency_error(tmp_path):
    """Verifies that require() and exporter fail with informative message when nir is absent."""
    from neurogenesis.interop.core import require
    with pytest.raises(ImportError, match=r"neurogenesis-sim\[nir\]"):
        require("a_package_that_does_not_exist", "nir")

    net = SNNNetwork(neurons=[_make_neuron(0)])
    with patch.dict(sys.modules, {"nir": None}):
        with pytest.raises(ImportError, match=r"neurogenesis-sim\[nir\]"):
            export_network(net, "nir", tmp_path / "missing.nir")


def test_cli_export_nir_subcommand(tmp_path):
    """CLI export: python -m neurogenesis export net.json --format nir --out circuit.nir."""
    net = SNNNetwork(
        neurons=[_make_neuron(0), _make_neuron(1)],
        synapses=[SynapseData(pre=0, post=1, weight=250, delay=0)],
    )
    net_path = tmp_path / "net.json"
    net.save_json(net_path)
    out_nir = tmp_path / "circuit.nir"

    cmd = [
        sys.executable,
        "-m",
        "neurogenesis",
        "export",
        str(net_path),
        "--format",
        "nir",
        "--out",
        str(out_nir),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"CLI error: {res.stderr}"
    assert out_nir.exists()

    report_dict = json.loads(res.stdout)
    assert report_dict["format"] == "nir"
    assert report_dict["counts"] == {"nodes": 2, "edges": 1}

    graph = nir.read(out_nir)
    assert isinstance(graph, nir.NIRGraph)
    assert len(graph.nodes) >= 3


def test_cortical_column_realistic_export(tmp_path):
    """Realistic cortical column network exports successfully with full report."""
    net = MorphogeneticEngine.generate_cortical_column(30, seed=42)
    out_path = tmp_path / "column.nir"
    rep = export_network(net, "nir", out_path)

    assert rep.counts["nodes"] == 30
    assert rep.counts["edges"] == net.num_synapses
    assert "delays" in rep.approximated
    assert "drivers" in rep.dropped

    graph = nir.read(out_path)
    assert graph.nodes["lif"].v_threshold.shape == (30,)


def test_lossless_round_trip(tmp_path):
    """Exporting to NIR and importing back reconstructs the original network exactly."""
    net = MorphogeneticEngine.generate_cortical_column(20, seed=123)
    out_path = tmp_path / "roundtrip.nir"
    export_network(net, "nir", out_path)

    back = import_network("nir", out_path)
    assert back.to_dict() == net.to_dict()


def test_non_contiguous_neuron_ids(tmp_path):
    """Networks with non-contiguous IDs (e.g. 10, 20) map correctly to dense matrix."""
    net = SNNNetwork(
        neurons=[_make_neuron(10), _make_neuron(20)],
        synapses=[SynapseData(pre=10, post=20, weight=300, delay=0)],
    )
    out_path = tmp_path / "non_contiguous.nir"
    export_network(net, "nir", out_path)

    graph = nir.read(out_path)
    lin = graph.nodes["recurrent"]
    assert lin.weight.shape == (2, 2)
    assert lin.weight[1, 0] > 0
    assert lin.weight[0, 1] == 0.0

    back = import_network("nir", out_path)
    assert [nd.id for nd in back.neurons] == [10, 20]
    assert back.synapses[0].pre == 10
    assert back.synapses[0].post == 20


def test_drivers_drop_mode(tmp_path):
    """Mode drivers='drop' removes driver neurons and their synapses from the graph."""
    net = SNNNetwork(
        neurons=[
            _make_neuron(0, mode=0),
            _make_neuron(1, mode=1, poisson_hz=50.0),
        ],
        synapses=[
            SynapseData(pre=1, post=0, weight=200, delay=0),
        ],
    )
    out_path = tmp_path / "dropped_drivers.nir"
    rep = export_nir(net, out_path, drivers="drop")
    assert rep.counts["nodes"] == 1
    assert rep.counts["edges"] == 0
    assert "drivers" in rep.dropped

    graph = nir.read(out_path)
    assert graph.nodes["lif"].v_threshold.shape == (1,)
    assert "recurrent" not in graph.nodes


def test_drivers_input_mode(tmp_path):
    """Mode drivers='input' converts driver efferent projections to external input linear node."""
    net = SNNNetwork(
        neurons=[
            _make_neuron(0, mode=0),
            _make_neuron(1, mode=1, poisson_hz=50.0),
        ],
        synapses=[
            SynapseData(pre=1, post=0, weight=200, delay=0),
        ],
    )
    out_path = tmp_path / "input_drivers.nir"
    rep = export_nir(net, out_path, drivers="input")
    assert rep.counts["nodes"] == 1
    assert rep.counts["edges"] == 1
    assert "drivers" in rep.approximated

    graph = nir.read(out_path)
    assert graph.nodes["lif"].v_threshold.shape == (1,)
    assert "input_linear" in graph.nodes
    lin_in = graph.nodes["input_linear"]
    assert lin_in.weight.shape == (1, 1)
    p = lif_params(net.neurons[0])
    assert np.isclose(lin_in.weight[0, 0], p.psc_amplitude(200))

    edges = set(graph.edges)
    assert ("input", "input_linear") in edges
    assert ("input_linear", "lif") in edges
    assert ("lif", "output") in edges
    assert "recurrent" not in graph.nodes


def test_drivers_input_with_recurrent(tmp_path):
    """Mode drivers='input' preserves recurrent LIF synapses alongside driver efferents."""
    net = SNNNetwork(
        neurons=[
            _make_neuron(0, mode=0),
            _make_neuron(1, mode=0),
            _make_neuron(2, mode=1, poisson_hz=50.0),
        ],
        synapses=[
            SynapseData(pre=2, post=0, weight=300, delay=0),
            SynapseData(pre=0, post=1, weight=150, delay=0),
        ],
    )
    out_path = tmp_path / "input_rec.nir"
    rep = export_nir(net, out_path, drivers="input")
    assert rep.counts["nodes"] == 2
    assert rep.counts["edges"] == 2
    assert "drivers" in rep.approximated

    graph = nir.read(out_path)
    assert graph.nodes["lif"].v_threshold.shape == (2,)
    assert "input_linear" in graph.nodes
    assert graph.nodes["input_linear"].weight.shape == (2, 1)
    assert "recurrent" in graph.nodes
    assert graph.nodes["recurrent"].weight.shape == (2, 2)


def test_drivers_all_drivers_raises_value_error(tmp_path):
    """Networks with no LIF neurons raise ValueError under drop or input mode."""
    net = SNNNetwork(
        neurons=[_make_neuron(0, mode=1), _make_neuron(1, mode=2)],
    )
    with pytest.raises(ValueError, match="no LIF neurons"):
        export_nir(net, tmp_path / "all_drop.nir", drivers="drop")
    with pytest.raises(ValueError, match="no LIF neurons"):
        export_nir(net, tmp_path / "all_input.nir", drivers="input")


def test_export_nir_1d_input_weights(tmp_path):
    """1D input_weights vector matching N neurons is reshaped to (N, 1)."""
    net = SNNNetwork(neurons=[_make_neuron(0), _make_neuron(1)])
    out_path = tmp_path / "input_1d.nir"
    rep = export_nir(net, out_path, input_weights=np.array([1.5, 2.5]))
    assert out_path.exists()
    graph = nir.read(out_path)
    assert "input_linear" in graph.nodes
    assert graph.nodes["input_linear"].weight.shape == (2, 1)


def test_export_nir_invalid_dt_raises(tmp_path):
    """dt <= 0 or non-finite values raise ValueError."""
    net = SNNNetwork(neurons=[_make_neuron(0)])
    with pytest.raises(ValueError, match="dt must be positive"):
        export_nir(net, tmp_path / "dt0.nir", dt=0.0)
    with pytest.raises(ValueError, match="dt must be positive"):
        export_nir(net, tmp_path / "dt_neg.nir", dt=-1e-3)
    with pytest.raises(ValueError, match="dt must be positive"):
        export_nir(net, tmp_path / "dt_nan.nir", dt=float("nan"))


def test_export_nir_dangling_synapses_reported(tmp_path):
    """Synapses referencing non-existent IDs are omitted and reported under dropped."""
    net = SNNNetwork(
        neurons=[_make_neuron(0)],
        synapses=[SynapseData(pre=99, post=0, weight=100, delay=0)],
    )
    out_path = tmp_path / "dangling.nir"
    rep = export_nir(net, out_path)
    assert rep.counts["edges"] == 0
    assert "dangling_synapses" in rep.dropped
    assert "synapses" not in rep.exact


def test_export_nir_exceeds_low_compute_limit(tmp_path):
    """Exporting > 2048 neurons raises ValueError per low-compute limits."""
    neurons = [_make_neuron(i) for i in range(2049)]
    net = SNNNetwork(neurons=neurons)
    with pytest.raises(ValueError, match="low-compute limit"):
        export_nir(net, tmp_path / "huge.nir")
