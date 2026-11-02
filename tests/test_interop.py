"""Interop core (J1): format registry, export reports and the shared dynamics mapping."""
import math

import numpy as np
import pytest

from neurogenesis.interop import (ExportReport, delay_ms, delay_ticks, export_network, formats, import_network, lif_params,
                                  register_format, shift_from_tau, tau_ms)
from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData
from neurogenesis.spiking.reference import IntegerSNNSimulator


def test_tau_matches_the_kernel_decay_factor():
    for s in range(1, 9):
        assert math.isclose(math.exp(-1.0 / tau_ms(s)), 1.0 - 2.0 ** -s, rel_tol=1e-12)
    with pytest.raises(ValueError):
        tau_ms(0)


def test_leak_of_the_integer_kernel_follows_tau_m():
    """A neuron charged once decays with the exported tau_m, up to integer rounding."""
    n = NeuronData(id=0, x=0, y=0, z=0, dir_x=1, dir_y=0, dir_z=0, mode=0, shift_v=4, shift_s=1, threshold=2048)
    sim = IntegerSNNSimulator(SNNNetwork(neurons=[n]), seed=0)
    sim.v_mem[0] = 2000
    trace = []
    for _ in range(30):
        sim.step()
        trace.append(int(sim.v_mem[0]))
    expected = 2000 * np.exp(-np.arange(1, 31) / tau_ms(4))
    assert np.max(np.abs(np.asarray(trace) - expected)) <= 30          # rounding error grows by < 1 unit per tick


def _neuron(i, **kw):
    return NeuronData(id=i, x=0, y=0, z=0, dir_x=1, dir_y=0, dir_z=0, mode=0, **kw)


def test_lif_params_units_and_inverses():
    p = lif_params(_neuron(0, shift_v=5, shift_s=4, threshold=1024, refractory=3))
    assert math.isclose(p.V_th, -50.0) and math.isclose(p.V_reset, -68.75) and p.t_ref == 3.0
    a = 2.0 ** -4
    # total charge: W * tau_syn / C_m (mV ms) equals s * w (1 - a) / (4 a), the sum of the kernel's v increments
    assert math.isclose(p.psc_amplitude(100) * p.tau_syn / p.C_m, p.mV_per_unit * 100 * (1 - a) / (4 * a))
    assert math.isclose(p.weight_units(p.psc_amplitude(-37)), -37)
    assert all(shift_from_tau(tau_ms(k)) == k for k in range(1, 12))
    assert all(delay_ticks(delay_ms(d)) == d for d in range(32))
    assert set(p.nest()) == {"C_m", "tau_m", "tau_syn_ex", "tau_syn_in", "t_ref", "E_L", "V_reset", "V_th", "I_e"}


def test_kernel_latency_is_delay_plus_one_tick():
    """A spike at tick t through a synapse of delay d first moves the target's v at tick t + d + 1."""
    for d in (0, 1, 5):
        net = SNNNetwork(neurons=[_neuron(0), _neuron(1, threshold=2048)],
                         synapses=[SynapseData(pre=0, post=1, weight=400, delay=d)])
        sim = IntegerSNNSimulator(net, seed=0)
        sim.v_mem[0] = 2000                                   # neuron 0 spikes at tick 0
        first = None
        for t in range(12):
            sim.step()
            if first is None and sim.v_mem[1] != 0:
                first = t
        assert first == d + 1 == delay_ms(d)


def test_registry_and_report(tmp_path):
    seen = {}

    def write(net, path, **opts):
        seen["n"] = net.num_neurons
        path.write_text("x")
        return ExportReport("toy", str(path), exact=["neurons"], dropped={"synapses": "toy format"})

    register_format("toy", export=write, description="test format")
    assert "toy" in formats() and "sonata" in formats()
    net = SNNNetwork(neurons=[NeuronData(id=0, x=0, y=0, z=0, dir_x=1, dir_y=0, dir_z=0, mode=0)])
    rep = export_network(net, "toy", tmp_path / "out.txt")
    assert seen["n"] == 1 and not rep.lossless and rep.to_dict()["dropped"] == {"synapses": "toy format"}
    with pytest.raises(ValueError, match="cannot be read"):
        import_network("toy", tmp_path / "out.txt")
    with pytest.raises(ValueError, match="unknown format"):
        export_network(net, "nope", tmp_path / "x")
