"""SONATA writer and reader (J2): exact round trip, reading by the reference library, generic import."""
import json

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

from neurogenesis.interop import export_network, import_network, lif_params  # noqa: E402
from neurogenesis.spiking.morphology import MorphogeneticEngine  # noqa: E402


@pytest.fixture(scope="module")
def net():
    return MorphogeneticEngine.generate_cortical_column(300, seed=3, refractory=2)


def test_round_trip_is_exact(net, tmp_path):
    report = export_network(net, "sonata", tmp_path / "c")
    back = import_network("sonata", tmp_path / "c")
    assert back.to_dict() == net.to_dict()
    assert report.counts == {"nodes": net.num_neurons, "edges": net.num_synapses} and not report.lossless
    assert "drivers" in report.approximated                         # the column has Poisson drivers and bursters


def test_layout_and_simulator_values(net, tmp_path):
    export_network(net, "sonata", tmp_path / "c")
    with h5py.File(tmp_path / "c/network/nodes.h5") as f:
        assert f.attrs["magic"] == 0x0A7A and list(f.attrs["version"]) == [0, 1]
        g = f["nodes/ngs"]
        assert g["0/x"].shape == (net.num_neurons,) and set(g["node_group_id"][()]) == {0}
        tau_m = g["0/dynamics_params/tau_m"][()]
    with h5py.File(tmp_path / "c/network/edges.h5") as f:
        g = f["edges/ngs_to_ngs"]
        assert g["source_node_id"].attrs["node_population"] == "ngs"
        delay, amp, w = g["0/delay"][()], g["0/syn_weight"][()], g["0/ngs_weight"][()]
    s0 = net.synapses[0]
    p = lif_params(net.neurons[s0.post])
    assert delay[0] == s0.delay + 1 and np.isclose(amp[0], p.psc_amplitude(s0.weight))
    assert np.array_equal(np.sign(amp), np.sign(w)) and np.isclose(tau_m[0], p.tau_m)
    cfg = json.loads((tmp_path / "c/circuit_config.json").read_text())
    assert cfg["networks"]["nodes"][0]["nodes_file"] == "$NETWORK_DIR/nodes.h5"


def test_reference_reader_libsonata(net, tmp_path):
    libsonata = pytest.importorskip("libsonata")
    export_network(net, "sonata", tmp_path / "c")
    nodes = libsonata.NodeStorage(str(tmp_path / "c/network/nodes.h5")).open_population("ngs")
    assert nodes.size == net.num_neurons
    x = nodes.get_attribute("x", libsonata.Selection([[0, nodes.size]]))
    assert np.allclose(x, [nd.x for nd in net.neurons])
    edges = libsonata.EdgeStorage(str(tmp_path / "c/network/edges.h5")).open_population("ngs_to_ngs")
    assert edges.size == net.num_synapses
    # the written indices agree with the edge list
    for node in (0, 7, net.num_neurons - 1):
        out = edges.efferent_edges([node]).flatten()
        assert sorted(out.tolist()) == [k for k, s in enumerate(net.synapses) if s.pre == node]
        inc = edges.afferent_edges([node]).flatten()
        assert sorted(inc.tolist()) == [k for k, s in enumerate(net.synapses) if s.post == node]
    libsonata.CircuitConfig.from_file(str(tmp_path / "c/circuit_config.json"))


def test_generic_import_from_simulator_values(net, tmp_path):
    """Without the ngs_* attributes, the shared mapping is inverted: shifts, refractory, weights and delays."""
    export_network(net, "sonata", tmp_path / "c")
    with h5py.File(tmp_path / "c/network/nodes.h5", "a") as f:
        for k in [k for k in f["nodes/ngs/0"].keys() if k.startswith("ngs_")]:
            del f[f"nodes/ngs/0/{k}"]
    with h5py.File(tmp_path / "c/network/edges.h5", "a") as f:
        del f["edges/ngs_to_ngs/0/ngs_weight"], f["edges/ngs_to_ngs/0/ngs_delay"]
    back = import_network("sonata", tmp_path / "c")
    assert back.num_neurons == net.num_neurons and back.num_synapses == net.num_synapses
    assert [n.shift_v for n in back.neurons] == [n.shift_v for n in net.neurons]
    assert [n.refractory for n in back.neurons] == [n.refractory for n in net.neurons]
    assert [s.delay for s in back.synapses] == [s.delay for s in net.synapses]
    # weights come back on the target's threshold scale (threshold 1024 after import)
    expected = np.asarray([s.weight for s in net.synapses]) * 1024 / np.asarray(
        [net.neurons[s.post].threshold for s in net.synapses])
    assert np.allclose([b.weight for b in back.synapses], expected, atol=1)


def test_missing_dependency_message():
    from neurogenesis.interop.core import require
    with pytest.raises(ImportError, match=r"neurogenesis-sim\[sonata\]"):
        require("a_package_that_does_not_exist", "sonata")
