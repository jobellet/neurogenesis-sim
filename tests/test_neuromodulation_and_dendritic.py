import pytest
import numpy as np
import warnings

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
        dendritic_distance=np.array([0.0, 200.0]),
    )

    with pytest.warns(UserWarning, match="Dendritic delay exceeds 31ms"):
        t2 = apply_dendritic_attenuation(
            t, length_constant=100.0, dendrite_velocity=5.0
        )

    assert t2.connectivity.delay[0] == 1
    # distance 200 / velocity 5 = 40. Expected delay 41. Clipped to 31.
    assert t2.connectivity.delay[1] == 31


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



def _modulated_tissue(n=3):
    t = Tissue.empty()
    t.add_cells(n, positions=np.zeros((n, 3)))
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]), post=np.array([1, 1]), weight=np.array([10.0, -10.0]), delay=np.array([1, 1])
    )
    spikes = np.zeros((10, n))
    spikes[0, 0] = spikes[1, 1] = spikes[2, 2] = 1.0
    return t, spikes


def test_neuromodulate_gene_controlled_eta():
    from neurogenesis.stages.base import Stage

    params = {"modulator_cells": [2], "tau_e": 5.0, "w_max": 100.0, "eta": {"path": ["eta"], "lo": 0.0, "hi": 1.0}}
    weights = {}
    for eta in (0.0, 0.5, 1.0):
        t, spikes = _modulated_tissue()
        stage = Stage("n", "neuromodulate", params={**params, "spikes": spikes})
        weights[eta] = stage.run(t, {"eta": eta}, {}, np.random.default_rng(0)).connectivity.weight
    np.testing.assert_allclose(weights[0.0], [10.0, -10.0])  # eta = 0: no change
    assert 10.0 < weights[0.5][0] < weights[1.0][0]
    assert weights[1.0][1] < 0.0
    # Same result as the function with eta given directly
    t, spikes = _modulated_tissue()
    direct = apply_modulated_plasticity(t, spikes, np.array([2]), eta=0.5, tau_e=5.0, w_max=100.0)
    np.testing.assert_allclose(weights[0.5], direct)


def test_neuromodulate_trace_is_per_postsynaptic_cell():
    # Two synapses onto two cells at different distances from the modulator cell: each sees its own level
    t = Tissue.empty()
    t.add_cells(4, positions=np.array([[0.0, 0, 0], [10.0, 0, 0], [200.0, 0, 0], [0.0, 0, 0]]))
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0]), post=np.array([2, 1]), weight=np.array([10.0, 10.0]), delay=np.array([1, 1])
    )
    spikes = np.zeros((10, 4))
    spikes[0, 0] = spikes[1, 1] = spikes[1, 2] = spikes[2, 3] = 1.0
    w = apply_modulated_plasticity(t, spikes, np.array([3]), eta=1.0, tau_e=5.0, w_max=100.0)
    assert w[1] - 10.0 > 5 * (w[0] - 10.0) > 0  # cell 1 is near the modulator cell, cell 2 far


def test_neuromodulate_declared_memory_within_factor_three():
    import tracemalloc
    from neurogenesis.stages.base import STAGE_REGISTRY, Stage

    rng = np.random.default_rng(1)
    N, E, T = 1000, 4000, 2000
    t = Tissue.empty()
    t.add_cells(N, positions=rng.uniform(0, 200, (N, 3)))
    t.connectivity = SparseConnectivity(
        pre=rng.integers(0, N, E), post=rng.integers(0, N, E), weight=rng.uniform(1, 10, E), delay=np.ones(E, int)
    )
    spikes = (rng.random((T, N)) < 0.01).astype(np.float32)
    params = {"modulator_cells": list(range(20)), "ticks": T}
    stage = Stage("n", "neuromodulate", params={**params, "spikes": spikes})
    stage.run(t, {}, {}, rng)  # compile outside the measurement
    tracemalloc.start()
    stage.run(t, {}, {}, rng)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared = STAGE_REGISTRY["neuromodulate"].cost(N, E, params)[0]
    assert declared / 3 <= peak <= declared * 3, (declared, peak)
