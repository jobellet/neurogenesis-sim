"""Tests for F6: refine_by_activity correctness, Dale's principle, and cell death index alignment."""
import numpy as np
import pytest

from neurogenesis.stages.base import Stage, run_schedule
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.params import Const


def test_two_neurons_pre_before_post_potentiates():
    """Two neurons with pre-before-post spiking must potentiate (weight increases)."""
    tissue = Tissue.empty()
    tissue.add_cells(2, positions=np.array([[0, 0, 0], [0.1, 0, 0]], dtype=np.float64))
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0], dtype=np.int32),
        post=np.array([1], dtype=np.int32),
        weight=np.array([100], dtype=np.int32),
        delay=np.array([1], dtype=np.int32)
    )

    # Spike raster: T=20, 2 neurons
    # Pre spikes at t=5 -> arrival at post at t=6 (delay=1)
    # Post spikes at t=7 -> dt = 7 - 6 = +1 > 0 (potentiation)
    spikes = np.zeros((20, 2), dtype=np.uint8)
    spikes[5, 0] = 1
    spikes[7, 1] = 1

    stage = Stage(
        name="refine",
        operator="refine_by_activity",
        params={
            "ticks": Const(20),
            "rule": Const("stdp"),
            "A_plus": Const(10.0),
            "A_minus": Const(10.0),
            "tau_plus": Const(20.0),
            "tau_minus": Const(20.0),
            "w_min": Const(0.0),
            "w_max": Const(1000.0),
            "spikes": Const(spikes.tolist())
        }
    )

    t_out = stage.run(tissue, {}, {}, np.random.default_rng(42))
    assert t_out.connectivity.weight[0] > 100, f"Expected weight > 100, got {t_out.connectivity.weight[0]}"


def test_two_neurons_post_before_pre_depotentiates():
    """Two neurons with post-before-pre spiking must depotentiate (weight decreases)."""
    tissue = Tissue.empty()
    tissue.add_cells(2, positions=np.array([[0, 0, 0], [0.1, 0, 0]], dtype=np.float64))
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0], dtype=np.int32),
        post=np.array([1], dtype=np.int32),
        weight=np.array([100], dtype=np.int32),
        delay=np.array([1], dtype=np.int32)
    )

    # Spike raster: T=20, 2 neurons
    # Post spikes at t=5
    # Pre spikes at t=6 -> arrival at post at t=7 (delay=1)
    # dt = 5 - 7 = -2 < 0 (post before pre arrival -> depotentiation)
    spikes = np.zeros((20, 2), dtype=np.uint8)
    spikes[5, 1] = 1
    spikes[6, 0] = 1

    stage = Stage(
        name="refine",
        operator="refine_by_activity",
        params={
            "ticks": Const(20),
            "rule": Const("stdp"),
            "A_plus": Const(10.0),
            "A_minus": Const(10.0),
            "tau_plus": Const(20.0),
            "tau_minus": Const(20.0),
            "w_min": Const(0.0),
            "w_max": Const(1000.0),
            "spikes": Const(spikes.tolist())
        }
    )

    t_out = stage.run(tissue, {}, {}, np.random.default_rng(42))
    assert t_out.connectivity.weight[0] < 100, f"Expected weight < 100, got {t_out.connectivity.weight[0]}"


def test_inhibitory_synapse_preserves_negative_sign():
    """Inhibitory synapse must preserve its negative sign under STDP (Dale's principle)."""
    tissue = Tissue.empty()
    # Presynaptic neuron is inhibitory (sign = -1)
    tissue.add_cells(
        2,
        positions=np.array([[0, 0, 0], [0.1, 0, 0]], dtype=np.float64),
        sign=np.array([-1, 1], dtype=np.int8)
    )
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0], dtype=np.int32),
        post=np.array([1], dtype=np.int32),
        weight=np.array([-100], dtype=np.int32),
        delay=np.array([1], dtype=np.int32)
    )

    spikes_pot = np.zeros((20, 2), dtype=np.uint8)
    spikes_pot[5, 0] = 1
    spikes_pot[7, 1] = 1

    stage_pot = Stage(
        name="refine_pot",
        operator="refine_by_activity",
        params={
            "ticks": Const(20),
            "rule": Const("stdp"),
            "A_plus": Const(10.0),
            "A_minus": Const(10.0),
            "w_min": Const(0.0),
            "w_max": Const(1000.0),
            "spikes": Const(spikes_pot.tolist())
        }
    )
    t_pot = stage_pot.run(tissue, {}, {}, np.random.default_rng(42))
    assert t_pot.connectivity.weight[0] < 0, "Inhibitory synapse must stay negative"
    assert t_pot.connectivity.weight[0] < -100, f"Expected potentiation (more negative than -100), got {t_pot.connectivity.weight[0]}"

    spikes_dep = np.zeros((20, 2), dtype=np.uint8)
    spikes_dep[5, 1] = 1
    spikes_dep[6, 0] = 1

    stage_dep = Stage(
        name="refine_dep",
        operator="refine_by_activity",
        params={
            "ticks": Const(20),
            "rule": Const("stdp"),
            "A_plus": Const(10.0),
            "A_minus": Const(10.0),
            "w_min": Const(0.0),
            "w_max": Const(1000.0),
            "spikes": Const(spikes_dep.tolist())
        }
    )
    # Re-initialize to -100
    tissue.connectivity.weight = np.array([-100], dtype=np.int32)
    t_dep = stage_dep.run(tissue, {}, {}, np.random.default_rng(42))
    assert t_dep.connectivity.weight[0] <= 0, "Inhibitory synapse must not become positive"
    assert t_dep.connectivity.weight[0] > -100, f"Expected depotentiation (less negative than -100), got {t_dep.connectivity.weight[0]}"


def test_cell_indices_survive_preceding_cell_death():
    """Refine must correctly handle tissues with prior cell death / apoptosis where cell index != cell id."""
    tissue = Tissue.empty()
    # 4 cells created with IDs 0, 1, 2, 3
    tissue.add_cells(4, positions=np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], dtype=np.float64))
    # Synapse 0 connects cell 0 -> cell 2
    # Synapse 1 connects cell 1 -> cell 3
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0, 1], dtype=np.int32),
        post=np.array([2, 3], dtype=np.int32),
        weight=np.array([100, 200], dtype=np.int32),
        delay=np.array([1, 1], dtype=np.int32)
    )

    # Cells 1 and 3 are killed (e.g. by Apoptosis)
    tissue.kill(np.array([False, True, False, True]))
    assert not tissue.alive.all()

    # Pre-before-post for surviving synapse (cell 0 -> cell 2)
    # In surviving tissue, cell 0 is at index 0 (ID 0) and cell 2 is at index 1 (ID 2)
    spikes = np.zeros((20, 2), dtype=np.uint8)
    spikes[5, 0] = 1
    spikes[7, 1] = 1

    stage = Stage(
        name="refine",
        operator="refine_by_activity",
        params={
            "ticks": Const(20),
            "rule": Const("stdp"),
            "A_plus": Const(15.0),
            "A_minus": Const(10.0),
            "w_min": Const(0.0),
            "w_max": Const(1000.0),
            "spikes": Const(spikes.tolist())
        }
    )

    t_out = stage.run(tissue, {}, {}, np.random.default_rng(0))

    # Dead cells and their synapses must be purged
    assert len(t_out.alive) == 2
    assert t_out.alive.all()
    # Surviving cell IDs must be 0 and 2
    assert list(t_out.cell_id) == [0, 2]
    # Connectivity must have exactly 1 valid synapse pointing to valid indices
    assert len(t_out.connectivity.pre) == 1
    assert len(t_out.connectivity.post) == 1
    assert len(t_out.connectivity.weight) == 1
    assert t_out.connectivity.pre[0] == 0
    assert t_out.connectivity.post[0] == 1  # Index of surviving cell 2
    # Synapse weight must have potentiated
    assert t_out.connectivity.weight[0] > 100


def test_end_to_end_refine_by_activity_in_schedule():
    """End-to-end multi-stage pipeline: seed_cells -> connect_by_hand -> refine_by_activity -> prune."""
    project = {
        "version": "1.0.0",
        "geometry": {
            "box": {"type": "box", "center": [0, 0, 0], "size": [1, 1, 1]}
        },
        "fields": {},
        "schedule": [
            {
                "name": "seed",
                "operator": "seed_cells",
                "params": {"N": 10, "geometry": "box"}
            },
            {
                "name": "connect",
                "operator": "connect_by_hand",
                "params": {
                    "pre": [0, 2, 4],
                    "post": [1, 3, 5],
                    "weight": 150,
                    "delay": 2
                }
            },
            {
                "name": "refine",
                "operator": "refine_by_activity",
                "params": {
                    "ticks": 20,
                    "rule": "stdp",
                    "sources": [0, 2],
                    "poisson_hz": 500.0,
                    "A_plus": 5.0,
                    "A_minus": 5.0
                }
            },
            {
                "name": "prune_weak",
                "operator": "prune",
                "params": {
                    "min_weight": 50
                }
            }
        ]
    }

    tissue = run_schedule(project, {}, seed=42)
    assert len(tissue.alive) == 10
    assert tissue.connectivity is not None
    assert len(tissue.connectivity.pre) > 0
    assert len(tissue.connectivity.weight) == len(tissue.connectivity.pre)
    assert np.all(tissue.connectivity.weight >= 50)


def test_spontaneous_wave_driver_potentiates_along_propagation():
    """Spontaneous waves with defined sources and speed potentiate feedforward connections."""
    tissue = Tissue.empty()
    # 3 neurons along a line: 0 at origin, 1 at x=10, 2 at x=20
    tissue.add_cells(3, positions=np.array([[0, 0, 0], [10, 0, 0], [20, 0, 0]], dtype=float))
    tissue.threshold[:] = 512
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0, 1], dtype=np.int32),
        post=np.array([1, 2], dtype=np.int32),
        weight=np.array([200, 200], dtype=np.int32),
        delay=np.array([1, 1], dtype=np.int32)
    )

    stage_wave = Stage(
        name="wave_refine",
        operator="refine_by_activity",
        params={
            "ticks": Const(40),
            "rule": Const("stdp"),
            "A_plus": Const(5.0),
            "A_minus": Const(1.0),
            "waves": {
                "sources": [0],
                "speed": 1.0,
                "interval": 50,
                "duration": 3,
                "amplitude": 3000
            }
        }
    )
    t_wave = stage_wave.run(tissue, {}, {}, np.random.default_rng(42))
    assert t_wave.connectivity.weight[0] > 200, f"Expected weight > 200, got {t_wave.connectivity.weight[0]}"


def test_motor_twitches_with_sensory_feedback_potentiates_loop():
    """Motor twitches triggering sensory feedback potentiate motor-to-sensory pathway."""
    tissue = Tissue.empty()
    # neuron 0: motor, neuron 1: sensory
    tissue.add_cells(2, positions=np.zeros((2, 3), dtype=float))
    tissue.threshold[:] = 512
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0, 1], dtype=np.int32),
        post=np.array([1, 0], dtype=np.int32),
        weight=np.array([100, 100], dtype=np.int32),
        delay=np.array([1, 1], dtype=np.int32)
    )

    stage_twitch = Stage(
        name="twitch_refine",
        operator="refine_by_activity",
        params={
            "ticks": Const(30),
            "rule": Const("stdp"),
            "A_plus": Const(5.0),
            "A_minus": Const(1.0),
            "twitches": {
                "motor_cells": [0],
                "sensory_cells": [1],
                "delay": 2,
                "gain": 3000,
                "interval": 30,
                "duration": 2,
                "amplitude": 3000
            }
        }
    )
    t_twitch = stage_twitch.run(tissue, {}, {}, np.random.default_rng(42))
    assert t_twitch.connectivity.weight[0] > 100, f"Expected weight > 100, got {t_twitch.connectivity.weight[0]}"



def _line_project(drive):
    """Three cells in a chain refined with STDP under one driver config, through run_schedule (dict params)."""
    return {"schedule": [
        {"name": "cells", "operator": "place_by_hand", "params": {
            "positions": [[0, 0, 0], [10, 0, 0], [20, 0, 0]], "threshold": 512}},
        {"name": "wire", "operator": "connect_by_hand", "params": {"pre": [0, 1], "post": [1, 2], "weight": 200}},
        {"name": "refine", "operator": "refine_by_activity", "params": {
            "ticks": 40, "rule": "stdp", "A_plus": 5.0, "A_minus": 1.0, **drive}}]}


def test_waves_and_twitches_settings_reach_the_stage_from_a_schedule():
    """Regression: dict params arrive wrapped in Const; their settings must be read, not replaced by defaults."""
    from neurogenesis.stages.base import run_schedule
    wave = {"sources": [0], "speed": 1.0, "interval": 50, "duration": 3}
    on = run_schedule(_line_project({"waves": dict(wave, amplitude=3000)}), {}, 0).connectivity.weight
    off = run_schedule(_line_project({"waves": dict(wave, amplitude=0)}), {}, 0).connectivity.weight
    assert on[0] > 200 and off.tolist() == [200, 200]
    tw = {"motor_cells": [0], "sensory_cells": [1], "delay": 2, "gain": 3000, "interval": 30, "duration": 2}
    on = run_schedule(_line_project({"twitches": dict(tw, amplitude=3000)}), {}, 0).connectivity.weight
    off = run_schedule(_line_project({"twitches": dict(tw, amplitude=0, gain=0)}), {}, 0).connectivity.weight
    assert on[0] > 200 and off.tolist() == [200, 200]
