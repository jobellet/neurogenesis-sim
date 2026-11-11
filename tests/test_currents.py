"""neurogenesis.spiking.currents: low-threshold (burst) current and linear recovery current, known properties."""
import numpy as np

import jax
import jax.numpy as jnp
from neurogenesis.spiking import currents as C
from neurogenesis.spiking import jax_backend as K
from neurogenesis.spiking.network import NeuronData, SNNNetwork


def _one_neuron():
    net = SNNNetwork.from_arrays("1.0.0", "t", [NeuronData(0, 0, 0, 0, 0, 0, 0, 0, refractory=2)],
                                 dict(pre=np.zeros(0, np.int32), post=np.zeros(0, np.int32), weight=np.zeros(0, np.int32),
                                      delay=np.zeros(0, np.int32)))
    return K.pack(net, 1, 1, 1)


def _run(ext, g=0.0, kappa=0.0, d=0.0, tau=100.0):
    net = _one_neuron()
    dm, dp = C.t_decays(20.0, 100.0)
    dec = np.float32(np.exp(-1.0 / tau))

    def step(c, e):
        st, h, u, spk = c
        h, it = C.t_current(h, st["v"], g, -400.0, dm, dp, hold=st["refr"] > 0)
        u, iu = C.recovery_current(u, st["v"], spk, kappa, dec, d)
        st, spk, _ = K.tick(net, st, jnp.rint(e + it + iu).astype(jnp.int32))
        return (st, h, u, spk.astype(jnp.float32)), (spk[0], st["v"][0], h[0])
    c0 = (K.init_state(net, 1), jnp.zeros(1, jnp.float32), jnp.zeros(1, jnp.float32), jnp.zeros(1, jnp.float32))
    _, (s, v, h) = jax.lax.scan(step, c0, jnp.asarray(ext, jnp.float32))
    return np.asarray(s).astype(int), np.asarray(v).astype(int), np.asarray(h)


def test_neutral_parameters_change_nothing():
    ext = np.r_[np.zeros(50), np.full(200, 12.0), np.full(100, -40.0), np.zeros(100)]
    a = _run(ext)
    b = _run(ext, g=0.0, kappa=0.0, d=0.0)
    assert np.array_equal(a[0], b[0]) and a[0].sum() > 0


def test_rebound_burst_after_hyperpolarisation_only():
    """Released from 300 ms of hyperpolarisation, the neuron fires a burst with no depolarising input; without the current
    it does not; a short hyperpolarisation (20 ms) gives a smaller h and fewer spikes."""
    long = np.r_[np.zeros(100), np.full(300, -60.0), np.zeros(400)]
    s, v, h = _run(long, g=100.0)
    assert v[350] < -400 and h[399] > 0.9
    assert s[:400].sum() == 0 and 3 <= s[400:600].sum() <= 8 and s[620:].sum() == 0     # a burst, then silence again
    assert _run(long, g=0.0)[0].sum() == 0
    short = np.r_[np.zeros(100), np.full(20, -60.0), np.zeros(300)]
    s2, _, h2 = _run(short, g=100.0)
    assert h2.max() < h.max() - 0.2 and s2.sum() < s.sum()


def test_tonic_mode_has_no_low_threshold_current():
    """A neuron firing under a steady drive keeps h = 0: the same spikes with and without the current."""
    ext = np.full(600, 14.0)
    a, _, _ = _run(ext, g=0.0)
    b, _, h = _run(ext, g=100.0)
    assert a.sum() > 10 and np.array_equal(a, b) and h.max() == 0.0


def test_recovery_current_adapts_and_sags():
    ext = np.full(1000, 14.0)
    plain = _run(ext)[0]
    adapt = _run(ext, d=3.0, tau=200.0)[0]
    assert adapt[:200].sum() >= adapt[800:].sum() + 2 and adapt.sum() < plain.sum()          # the rate falls with time
    step = np.r_[np.zeros(100), np.full(600, -6.0)]
    v0 = _run(step)[1]
    v1 = _run(step, kappa=0.01, tau=100.0)[1]
    assert v1[150:260].min() < v1[690] - 20                     # sag: a trough, then a partial return
    assert abs(v0[150:260].min() - v0[690]) < 20                # none without the current
    assert v1[690] > v0[690] + 50                               # the restorative current opposes the hyperpolarisation
