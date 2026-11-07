"""The Numba event-driven kernel gives the spikes of the JAX kernel and of the reference, per neuron and tick."""
import numpy as np
import pytest

pytest.importorskip("numba")

from neurogenesis.spiking import jax_backend as K  # noqa: E402
from neurogenesis.spiking import numba_backend as NB  # noqa: E402
from neurogenesis.spiking.network import NeuronData, SNNNetwork  # noqa: E402
from neurogenesis.spiking.reference import IntegerSNNSimulator  # noqa: E402


def _net(seed, n=120, deg=12, max_delay=255):
    """Random network with LIF, Poisson (mode 1) and burster (mode 2) neurons, inhibition, refractory periods and
    delays up to max_delay (several words of spike history)."""
    rng = np.random.default_rng(seed)
    mode = np.where(rng.random(n) < 0.08, 1, np.where(rng.random(n) < 0.04, 2, 0))
    neurons = [NeuronData(id=i, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=int(mode[i]),
                          shift_v=int(rng.integers(3, 7)), shift_s=int(rng.integers(2, 6)), base_weight=1,
                          conn_radius=0.0, conn_prob=0.0, poisson_hz=float(rng.uniform(5, 60)),
                          refractory=int(rng.integers(0, 4)), threshold=int(rng.integers(600, 1400)),
                          burst_period=int(rng.choice([0, 150])), burst_duty=int(rng.choice([0, 30])))
               for i in range(n)]
    E = n * deg
    pre, post = rng.integers(0, n, E), rng.integers(0, n, E)
    w = np.where(rng.random(E) < 0.2, -1, 1) * rng.integers(50, 700, E)
    d = rng.integers(1, max_delay + 1, E)
    return SNNNetwork.from_arrays("1.0.0", "test", neurons, dict(pre=pre.astype(np.int32), post=post.astype(np.int32),
                                                                 weight=w.astype(np.int32), delay=d.astype(np.int32)))


def _jax_raster(net, T, seed):
    arr = K.pack(net)
    _, spk = K.run(arr, K.init_state(arr, seed), T)
    return np.asarray(spk).astype(bool)[:, :net.num_neurons]


@pytest.mark.parametrize("seed,max_delay", [(1, 31), (2, 255), (3, 100)])
def test_same_spikes_as_jax_kernel(seed, max_delay):
    net, T = _net(seed, max_delay=max_delay), 2000
    ref = _jax_raster(net, T, 777)
    out = NB.simulate(net, T, seed=777, bin_ticks=1)
    assert ref.sum() > 500                                    # the test exercises real activity
    assert np.array_equal(out["cells"].astype(bool), ref)
    assert np.array_equal(out["spikes"], ref.sum(1)) and np.array_equal(out["recurrent"], out["spikes"])


def test_same_spikes_as_reference_simulator():
    net, T = _net(4, n=40, deg=6, max_delay=60), 600
    sim = IntegerSNNSimulator(net, seed=99)
    per_tick = [sim.step() for _ in range(T)]
    assert np.array_equal(NB.simulate(net, T, seed=99)["spikes"], per_tick)


def test_forced_spikes_are_counted_apart_and_extensions_are_neutral_when_off():
    net, T = _net(5), 1500
    base = NB.simulate(net, T, seed=1)
    same = NB.simulate(net, T, seed=1, depression=dict(strength=0.0), homeostasis=dict(rate=0.0), excitatory_gain=1.0)
    assert np.array_equal(base["spikes"], same["spikes"])
    ev = (np.arange(0, T, 10), np.full(T // 10, 7))
    f = NB.simulate(net, T, seed=1, forced_events=ev)
    assert f["spikes"].sum() - f["recurrent"].sum() > 0
    assert (f["spikes"] >= f["recurrent"]).all()


def test_homeostasis_and_depression_act():
    net, T = _net(6), 20000
    off = NB.simulate(net, T, seed=1)["spikes"][10000:].mean() * 1000 / net.num_neurons
    on = NB.simulate(net, T, seed=1, homeostasis=dict(rate=1.0, target_hz=2.0))["spikes"][10000:].mean() * 1000 / net.num_neurons
    assert abs(on - 2.0) < abs(off - 2.0)
    dep = NB.simulate(net, T, seed=1, depression=dict(strength=1.0, U=0.5, tau_rec=500.0))
    assert dep["resources"].min() < 1.0


def test_rejects_what_it_cannot_simulate():
    net = _net(7)
    net.synapse_arrays["delay"][0] = 0
    with pytest.raises(ValueError):
        NB.arrays(net)
