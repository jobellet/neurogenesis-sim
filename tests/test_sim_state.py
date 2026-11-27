"""Simulation state files: exact pause / resume, refusal of foreign states, extension to appended cells."""
import copy

import numpy as np
import pytest

from neurogenesis.spiking import jax_backend
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.network import NeuronData
from neurogenesis.spiking.state import extend_state, load_state, network_fingerprint, save_state


def _net(n=80, seed=1):
    return MorphogeneticEngine.generate_cortical_column(n, seed=seed, weight_scale=0.25, refractory=3)


def _run(arr, st, ticks, model="lif_int"):
    import jax
    from neurogenesis.spiking.models import get_model
    tick = get_model(model).tick

    def f(s, _):
        s, spk, _ = tick(arr, s, None) if model == "lif_int" else tick(arr, s, np.zeros(arr["mode"].shape, np.int32))
        return s, spk
    return jax.lax.scan(f, st, None, length=ticks)


@pytest.mark.parametrize("model", ["lif_int", "two_compartment"])
def test_pause_save_load_resume_is_bit_identical(tmp_path, model):
    from neurogenesis.spiking.models import get_model
    net = _net()
    arr = jax_backend.pack(net)
    st0 = get_model(model).init_state(arr, 7)
    _, full = _run(arr, st0, 300, model)
    st, first = _run(arr, st0, 120, model)
    save_state(tmp_path / "s.npz", st, net, model=model, tick=120)
    st2, t = load_state(tmp_path / "s.npz", net, model=model)
    _, second = _run(arr, st2, 180, model)
    assert t == 120
    assert np.array_equal(np.concatenate([np.asarray(first), np.asarray(second)]), np.asarray(full))
    assert np.asarray(full).sum() > 0


def test_foreign_states_are_refused(tmp_path):
    net = _net()
    st = jax_backend.init_state(jax_backend.pack(net), 1)
    save_state(tmp_path / "s.npz", st, net)
    with pytest.raises(ValueError, match="another network"):
        load_state(tmp_path / "s.npz", _net(seed=2))
    with pytest.raises(ValueError, match="model"):
        load_state(tmp_path / "s.npz", net, model="hh")
    assert network_fingerprint(net) == network_fingerprint(copy.deepcopy(net))


def test_extend_state_keeps_old_cells_when_cells_are_appended():
    net = _net()
    arr = jax_backend.pack(net)
    st, _ = _run(arr, jax_backend.init_state(arr, 5), 150)
    _, cont = _run(arr, st, 100)

    grown = copy.deepcopy(net)
    N = net.num_neurons
    grown.neurons = list(grown.neurons) + [NeuronData(id=N + k, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0)
                                           for k in range(5)]
    garr = jax_backend.pack(grown)
    st_g = extend_state(st, grown)
    assert np.asarray(st_g["v"]).shape[-1] == N + 5 and np.all(np.asarray(st_g["v"])[N:] == 0)
    _, cont_g = _run(garr, st_g, 100)
    assert np.array_equal(np.asarray(cont_g)[:, :N], np.asarray(cont))      # new silent cells change nothing
    with pytest.raises(ValueError):
        extend_state(st_g, net)
