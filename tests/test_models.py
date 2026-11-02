"""Neuron models: every model runs grown networks, is deterministic and batch-consistent, keeps the drivers' spike times,
and reproduces the properties it claims."""
import numpy as np
import pytest

from neurogenesis.analysis import fi_curve
from neurogenesis.development import grow
from neurogenesis.spiking.batch import simulate_counts
from neurogenesis.spiking.models import MODELS, get_model, hh, register_model, two_compartment
from neurogenesis.spiking.morphology import MorphogeneticEngine

from test_development import sheet_plan, toy_genome

ALL = sorted(MODELS)


def test_registry_and_interface():
    assert {"lif_int", "two_compartment", "hh"} <= set(MODELS)
    for m in MODELS.values():
        assert m.substeps >= 1 and m.state_bytes > 0 and m.flops > 0 and m.description
    with pytest.raises(KeyError):
        get_model("no_such_model")


def test_lif_int_through_the_model_switch_is_the_integer_kernel():
    net = MorphogeneticEngine.generate_cortical_column(80, seed=1, weight_scale=0.25, refractory=3)
    ext = np.random.default_rng(0).integers(0, 50, (3, 80)).astype(np.int32)
    assert np.array_equal(simulate_counts([net], [ext], ticks=30), simulate_counts([net], [ext], ticks=30, model="lif_int"))


@pytest.mark.parametrize("model", ALL)
def test_drivers_fire_identically_in_every_model(model):
    net = MorphogeneticEngine.generate_cortical_column(60, seed=4, weight_scale=0.25, refractory=3)
    net.synapses = []                                                   # isolate the drivers
    drv = [i for i, n in enumerate(net.neurons) if n.mode in (1, 2)]
    assert drv
    ext = np.zeros((2, 60), np.int32)
    ref = simulate_counts([net], [ext], ticks=200)[0][:, drv]
    assert np.array_equal(simulate_counts([net], [ext], ticks=200, model=model)[0][:, drv], ref)


@pytest.mark.parametrize("model", ALL)
def test_deterministic_and_batch_consistent(model):
    p, g = sheet_plan(), toy_genome()
    nets = [grow(p, g, s) for s in (0, 1)]
    rng = np.random.default_rng(2)
    exts = [rng.integers(0, 60, (2, n.num_neurons)).astype(np.int32) for n in nets]
    both = simulate_counts(nets, exts, ticks=40, model=model)
    assert np.array_equal(both, simulate_counts(nets, exts, ticks=40, model=model))
    one = simulate_counts(nets[:1], exts[:1], ticks=40, model=model)
    assert np.array_equal(both[0], one[0])
    assert both.sum() > 0, f"{model}: no spike in a driven grown network"


def test_hodgkin_huxley_known_properties():
    """Rest near -65 mV; repetitive firing from rest starts abruptly (type II) near 6.3 uA/cm2 at about 50-60 Hz, and is
    about 65-70 Hz at 10 uA/cm2 (Hodgkin & Huxley 1952 parameters)."""
    from neurogenesis.spiking.jax_backend import pack
    net = MorphogeneticEngine.generate_microcircuit(1, seed=0)
    net.neurons[0].mode = 0
    st = hh.init_state(pack(net))
    assert abs(float(st["v"][0]) + 65.0) < 1e-3
    units = np.arange(6.0, 11.01, 0.2) / hh.SCALE
    f = fi_curve(np.round(units).astype(int), model="hh") * 1000
    ua = np.round(units) * hh.SCALE
    onset = ua[np.argmax(f > 20)]
    assert 5.8 <= onset <= 7.0 and 40 <= f[f > 20][0] <= 65
    assert 60 <= f[np.argmin(np.abs(ua - 10.0))] <= 75


def test_two_compartment_matches_the_integer_rheobase_and_refractoriness():
    f = fi_curve([0, 7, 8, 9, 10, 20, 400], model="two_compartment")
    assert f[0] == f[1] == 0 and f[3] > 0 and np.all(np.diff(f) >= 0) and f[-1] <= 1 / 4 + 1e-9
    f5 = fi_curve([400], refractory=5, model="two_compartment")
    assert f5[0] * 1000 <= np.ceil(1000 / 6)                                  # at most one spike every refractory + 1 ticks


def test_two_compartment_dendritic_inputs_are_attenuated():
    """The same excitatory charge reaches threshold less easily on the dendrite (synapses) than on the soma (current)."""
    from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData
    nd = lambda i, mode=0: NeuronData(id=i, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=mode, shift_v=5,
                                      shift_s=4, base_weight=1, conn_radius=0.0, conn_prob=0.0, refractory=3,
                                      poisson_hz=1000.0 if mode == 1 else 25.0)
    rate = []
    for w in (20, 60, 120, 240):
        net = SNNNetwork(neurons=[nd(0, mode=1), nd(1)], synapses=[SynapseData(pre=0, post=1, weight=w, delay=1)])
        lif = simulate_counts([net], [np.zeros((1, 2), np.int32)], ticks=500)[0][0, 1]
        tc = simulate_counts([net], [np.zeros((1, 2), np.int32)], ticks=500, model="two_compartment")[0][0, 1]
        rate.append((lif, tc))
    assert any(l > 0 for l, _ in rate) and all(t <= l for l, t in rate)


def test_register_a_new_model():
    import types
    m = types.SimpleNamespace(name="frozen", description="never fires", substeps=1, state_bytes=4, flops=1,
                              init_state=two_compartment.init_state,
                              tick=lambda net, st, ext: (st, np.zeros(np.shape(net["mode"])[-1], np.uint8), None))
    register_model(m)
    try:
        assert get_model("frozen") is m
    finally:
        MODELS.pop("frozen")


def test_conductance_based_synapses_reversal_potentials(tmp_path):
    from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData
    nd = lambda i: NeuronData(id=i, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, shift_v=5, shift_s=4,
                              base_weight=1, threshold=1024, refractory=0)
    net = SNNNetwork(neurons=[nd(0), nd(1), nd(2)],
                     synapses=[SynapseData(pre=0, post=1, weight=1000, delay=1),
                               SynapseData(pre=0, post=2, weight=1000, delay=1)])
    net.neurons[0].mode = 1
    net.neurons[0].poisson_hz = 500.0
    p = tmp_path / "cond.npz"
    net.save_npz(str(p))
    net2 = SNNNetwork.load_npz(str(p))
    net2.synapse_arrays["e_rev"] = np.array([0.0, -80.0], dtype=np.float32)
    net2.synapse_arrays["tau_decay"] = np.array([5.0, 10.0], dtype=np.float32)
    counts = simulate_counts([net2], [np.zeros((1, 3), np.int32)], ticks=100, model="two_compartment")[0]
    assert counts[0, 1] > 0 and counts[0, 2] == 0
    counts_hh = simulate_counts([net2], [np.zeros((1, 3), np.int32)], ticks=100, model="hh")[0]
    assert counts_hh[0, 1] > 0 and counts_hh[0, 2] == 0


def test_multi_channel_synaptic_currents(tmp_path):
    from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData
    nd = lambda i: NeuronData(id=i, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, shift_v=5, shift_s=4,
                              base_weight=1, threshold=1024, refractory=0)
    net = SNNNetwork(neurons=[nd(0), nd(1)], synapses=[SynapseData(pre=0, post=1, weight=500, delay=1)])
    net.neurons[0].mode = 1
    net.neurons[0].poisson_hz = 50.0
    p = tmp_path / "chan.npz"
    net.save_npz(str(p))
    net2 = SNNNetwork.load_npz(str(p))
    net2.synapse_arrays["channel"] = np.array([1], dtype=np.int32)
    net2.neurons[0].shift_s_channels = np.array([4, 6], dtype=np.int32)
    net2.neurons[1].shift_s_channels = np.array([4, 6], dtype=np.int32)
    counts_slow = simulate_counts([net2], [np.zeros((1, 2), np.int32)], ticks=100, model="lif_int")[0]
    net2.synapse_arrays["channel"] = np.array([0], dtype=np.int32)
    counts_fast = simulate_counts([net2], [np.zeros((1, 2), np.int32)], ticks=100, model="lif_int")[0]
    assert counts_slow[0, 1] >= counts_fast[0, 1]
