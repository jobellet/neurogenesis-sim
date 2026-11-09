"""E2 surrogate gradients: exact forward spikes, useful gradients with respect to weights."""
import jax
import jax.numpy as jnp
import numpy as np
import pytest

from neurogenesis.spiking import jax_backend
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.network import NeuronData, SNNNetwork
from neurogenesis.spiking.surrogate import run_differentiable


def _exact(net, ext, seed):
    st = jax_backend.init_state(net, seed)
    out = []
    for e in ext:
        st, spk, _ = jax_backend.tick(net, st, jnp.asarray(e))
        out.append(np.asarray(spk))
    return np.stack(out)


def test_forward_spikes_equal_the_kernel():
    net = MorphogeneticEngine.generate_cortical_column(80, seed=3, weight_scale=0.3, refractory=2)
    a = jax_backend.pack(net)
    rng = np.random.default_rng(0)
    ext = rng.integers(0, 120, size=(60, net.num_neurons)).astype(np.int32)
    s = np.asarray(run_differentiable(a, a["weight"].astype(np.float32), 60, ext, seed=7))
    exact = _exact(a, ext, 7)
    assert exact.sum() > 0
    np.testing.assert_array_equal(s.astype(np.uint8), exact)


def _pair(w=300, delay=2):
    neurons = [NeuronData(i, 0, 0, 0, 1, 0, 0, 0, refractory=2) for i in range(2)]
    arrays = dict(pre=np.array([0], np.int32), post=np.array([1], np.int32), weight=np.array([w], np.int32),
                  delay=np.array([delay], np.int32))
    return jax_backend.pack(SNNNetwork(neurons=neurons, synapse_arrays=arrays))


def test_gradient_of_the_post_rate_follows_the_weight():
    a = _pair()
    ext = np.zeros((200, 2), np.int32)
    ext[:, 0] = 200                       # neuron 0 fires regularly
    ext[:, 1] = 60                        # neuron 1 near threshold

    def post_count(w):
        return run_differentiable(a, w, 200, ext)[:, 1].sum()

    g = jax.grad(post_count)(jnp.array([300.0]))
    assert np.isfinite(g).all() and g[0] > 0
    gi = jax.grad(post_count)(jnp.array([-300.0]))
    assert gi[0] > 0                      # making an inhibitory weight less negative also raises the rate


def test_gradient_descent_reaches_a_target_rate():
    a = _pair(w=0)
    ext = np.zeros((300, 2), np.int32)
    ext[:, 0] = 200
    ext[:, 1] = 40
    target = 20.0

    def loss(w):
        return (run_differentiable(a, w, 300, ext)[:, 1].sum() - target) ** 2

    w = jnp.array([0.0])
    grad = jax.jit(jax.grad(loss))
    for _ in range(60):
        w = w - 2.0 * jnp.sign(grad(w))
    assert abs(float(run_differentiable(a, w, 300, ext)[:, 1].sum()) - target) <= 6


def test_rejects_multichannel():
    a = _pair()
    a["channel"] = np.zeros(1, np.int32)
    with pytest.raises(ValueError):
        run_differentiable(a, np.zeros(1, np.float32), 5)
