import pytest
import numpy as np
import warnings
import copy

from neurogenesis.neuromodulation import (
    VolumeModulator,
    apply_modulated_plasticity,
    NeuromodulateStage,
)
from neurogenesis.dendritic import apply_dendritic_attenuation, DendriticAttenuateStage
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.spiking.plasticity import ThreeFactorRule


def test_volume_modulator_no_op():
    spikes = np.zeros((10, 10))
    mod = VolumeModulator(source_cells=[])
    trace = mod.modulator_trace(spikes)
    assert trace.shape == (10,)
    assert np.all(trace == 0.0)


def test_volume_modulator_global():
    spikes = np.zeros((10, 5))
    spikes[0, 1] = 1.0  # source cell spiked at t=0
    mod = VolumeModulator(source_cells=[1], tau_ms=10.0, gain=2.0)
    trace = mod.modulator_trace(spikes)

    assert trace[0] == 2.0  # spike * gain
    decay = np.exp(-1.0 / 10.0)
    np.testing.assert_almost_equal(trace[1], 2.0 * decay)


def test_volume_modulator_spatial():
    spikes = np.zeros((10, 5))
    spikes[0, 1] = 1.0

    positions = np.array(
        [
            [0, 0, 0],
            [0, 0, 0],  # Source
            [10, 0, 0],  # Target 1 (near)
            [100, 0, 0],  # Target 2 (far)
        ]
    )

    mod = VolumeModulator(source_cells=[1], space_constant=50.0, tau_ms=10.0)
    target_cells = np.array([2, 3])
    trace = mod.modulator_trace(
        spikes, positions=positions, target_cells=target_cells
    )

    assert trace.shape == (10, 2)
    expected_near = np.exp(-10.0 / 50.0)
    expected_far = np.exp(-100.0 / 50.0)
    np.testing.assert_almost_equal(trace[0, 0], expected_near)
    np.testing.assert_almost_equal(trace[0, 1], expected_far)


def test_neuromodulate_stage_cost():
    params = {"modulator_cells": [1], "ticks": 100}
    b, o = NeuromodulateStage.cost(2, 1, params)
    assert b > 0 and o > 0
    b_neutral, o_neutral = NeuromodulateStage.cost(2, 1, {})
    assert b_neutral == 0 and o_neutral == 0


def test_dendritic_attenuate_stage_cost():
    b, o = DendriticAttenuateStage.cost(2, 1, {"length_constant": 100.0})
    assert b > 0 and o > 0
    b_neutral, o_neutral = DendriticAttenuateStage.cost(2, 1, {})
    assert b_neutral == 0 and o_neutral == 0


def test_neuromodulate_reward_gating():
    t = Tissue.empty()
    t.positions = np.zeros((3, 3))
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]), 
        post=np.array([1, 1]), 
        weight=np.array([10.0, -10.0]), 
        delay=np.array([1, 1])
    )
    t.alive = np.ones(3, dtype=bool)

    spikes = np.zeros((10, 3))
    spikes[0, 0] = 1.0
    spikes[1, 1] = 1.0
    spikes[2, 2] = 1.0
    
    t_pos = apply_modulated_plasticity(
        tissue=t,
        spikes=spikes,
        source_cells=np.array([2]),
        eta=0.5,
        w_min=0.0,
        w_max=100.0,
        tau_e=5.0
    )
    
    # Positive reward means dw is positive for excitatory, negative for inhibitory
    assert t_pos[0] > 10.0
    
    # Wait, if dw is positive, weight 10 + dw > 10.
    # What about inhibitory? The original rule:
    # dw = eta * elig * mod_post
    # w_new = w + dw
    # If the original weight was -10, and dw is positive, w_new = -10 + dw = -9.0 for example.
    # Then `w_new = jnp.where(is_exc, jnp.maximum(w_new, 0), jnp.minimum(w_new, 0))`
    # Which makes it -9.0.
    # This means its MAGNITUDE DECREASES.
    # So if dw > 0, an inhibitory synapse's magnitude decreases (it gets closer to 0).
    # We should just test for Dale's sign preservation and change in appropriate direction.
    assert t_pos[1] > -10.0
    assert t_pos[1] <= 0.0

    # 2. Negative reward
    t.connectivity.weight = np.array([10.0, -10.0]) # reset
    mod_neg = VolumeModulator(source_cells=np.array([2]), gain=-1.0)
    trace_neg = mod_neg.modulator_trace(spikes, positions=t.positions, target_cells=t.connectivity.post)
    
    rule = ThreeFactorRule(eta=0.5, tau_e=5.0)
    import jax.numpy as jnp
    
    w_neg = rule.apply(
        weights=jnp.array([10.0, -10.0]),
        pre=jnp.array([0, 0]),
        post=jnp.array([1, 1]),
        delays=jnp.array([1, 1]),
        spikes=jnp.array(spikes),
        modulator=jnp.array(trace_neg),
        original_weights=jnp.array([10.0, -10.0])
    )
    
    w_neg = np.array(w_neg)
    w_min_mag = 0.0
    w_max_mag = 100.0
    mags = np.abs(w_neg)
    mags = np.clip(mags, w_min_mag, w_max_mag)
    is_exc = np.array([True, False])
    w_neg_clipped = np.where(is_exc, mags, -mags)

    assert w_neg_clipped[0] < 10.0
    # Negative reward -> dw < 0. For inhibitory: -10 + (-dw) = more negative
    assert w_neg_clipped[1] < -10.0 


def test_dendritic_attenuate_no_op():
    t = Tissue.empty()
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]),
        post=np.array([1, 1]),
        weight=np.array([10.0, 10.0]),
        delay=np.array([1, 1]),
        dendritic_distance=np.array([0.0, 100.0]),
    )

    stage = DendriticAttenuateStage()
    t2 = stage.run(t, {}, {}, {}, np.random.default_rng(0))
    np.testing.assert_array_equal(t2.connectivity.weight, [10.0, 10.0])


def test_dendritic_attenuate_decay():
    t = Tissue.empty()
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]),
        post=np.array([1, 1]),
        weight=np.array([10.0, -10.0]),
        delay=np.array([1, 1]),
        dendritic_distance=np.array([0.0, 100.0]),
    )

    t2 = apply_dendritic_attenuation(t, length_constant=100.0)

    # Proximal should be unattenuated (d=0)
    assert t2.connectivity.weight[0] == 10.0
    # Distal should be attenuated (d=100)
    expected_distal = -10.0 * np.exp(-1.0)
    np.testing.assert_almost_equal(t2.connectivity.weight[1], expected_distal)


def test_dendritic_attenuate_delay():
    t = Tissue.empty()
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]),
        post=np.array([1, 1]),
        weight=np.array([10.0, 10.0]),
        delay=np.array([1, 1]),
        dendritic_distance=np.array([0.0, 100.0]),
    )

    with warnings.catch_warnings(record=True) as w:
        t2 = apply_dendritic_attenuation(
            t, length_constant=100.0, dendrite_velocity=5.0
        )
        assert len(w) == 0

    assert t2.connectivity.delay[0] == 1
    # distance 100 / velocity 5 = 20. Total delay = 1 + 20 = 21
    assert t2.connectivity.delay[1] == 21


def test_dendritic_attenuate_delay_clipping():
    t = Tissue.empty()
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]),
        post=np.array([1, 1]),
        weight=np.array([10.0, 10.0]),
        delay=np.array([1, 1]),
        dendritic_distance=np.array([0.0, 400.0]),
    )

    with pytest.warns(UserWarning, match="Dendritic delay exceeds 255 ticks"):
        t2 = apply_dendritic_attenuation(
            t, length_constant=100.0, dendrite_velocity=1.0
        )

    assert t2.connectivity.delay[0] == 1
    # distance 400 / velocity 1 = 400. Expected delay 401. Clipped to 255.
    assert t2.connectivity.delay[1] == 255


def test_integration_run_schedule():
    from neurogenesis.stages.base import Stage

    stage1 = Stage(
        "n1", "neuromodulate", params={"modulator_cells": [], "ticks": 100}
    )
    stage2 = Stage(
        "n2", "dendritic_attenuate", params={"length_constant": 100.0}
    )

    t = Tissue.empty()
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]),
        post=np.array([1, 1]),
        weight=np.array([10.0, 10.0]),
        delay=np.array([1, 1]),
        dendritic_distance=np.array([0.0, 100.0]),
    )
    t.alive = np.ones(2, dtype=bool)

    rng = np.random.default_rng(0)
    t = stage1.run(t, {}, {}, rng)
    t = stage2.run(t, {}, {}, rng)

    assert t.connectivity.weight[0] == 10.0
    expected_distal = 10.0 * np.exp(-1.0)
    np.testing.assert_almost_equal(t.connectivity.weight[1], expected_distal)



def test_k6_neuromodulate_keeps_non_plastic_synapses():
    from neurogenesis.neuromodulation import NeuromodulateStage
    t = Tissue.empty()
    t.add_cells(3)
    t.connectivity = SparseConnectivity(np.array([0, 0], np.int32), np.array([1, 1], np.int32),
                                        np.array([10, -10], np.int32), np.array([1, 1], np.int32))
    spikes = np.zeros((10, 3))
    spikes[0, 0] = spikes[1, 1] = spikes[2, 2] = 1.0
    params = {"modulator_cells": [2], "spikes": spikes, "eta": 0.5, "tau_e": 5.0}
    free = NeuromodulateStage().run(copy.deepcopy(t), params, {}, {}, np.random.default_rng(0))
    assert free.connectivity.weight[0] != 10
    t.connectivity.plastic = np.array([False, True])
    out = NeuromodulateStage().run(t, params, {}, {}, np.random.default_rng(0))
    assert out.connectivity.weight[0] == 10 and out.connectivity.weight[1] == free.connectivity.weight[1]
