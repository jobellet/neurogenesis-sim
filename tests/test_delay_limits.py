"""Tests for F5: Kernel delay limits (delay in [1, 31]), clipping warnings, and index validation."""
import warnings
import numpy as np
import pytest

from neurogenesis.stages.base import Stage
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.params import Const


def test_grow_axons_clips_delays_to_31_and_warns():
    """grow_axons on distant populations must clip delay to 31 and warn with count."""
    tissue = Tissue.empty()
    # Source at origin (x=0), Target far away (x=100)
    tissue.add_cells(5, positions=np.array([[0, 0, 0]] * 5), region=np.zeros(5, dtype=int))
    tissue.add_cells(5, positions=np.array([[100, 0, 0]] * 5), region=np.ones(5, dtype=int))

    guidance = {
        "0->1": {
            "B": np.eye(3).tolist(),
            "c": [0, 0, 0],
            "sigma": 0.5,
            "p0": 1.0,
            "w": 50
        }
    }

    stage = Stage(
        name="grow",
        operator="grow_axons",
        params={
            "projections": Const(["0->1"]),
            "guidance": Const(guidance),
            "conduction_velocity": Const(1.0)  # Distance 100 / cv 1.0 = raw delay 100 > 31
        }
    )

    with pytest.warns(UserWarning, match="clipped to maximum delay 31 ticks") as record:
        t_out = stage.run(tissue, {}, {}, np.random.default_rng(42))

    assert len(record) == 1
    assert len(t_out.connectivity.delay) > 0
    # Every delay must be clipped to <= 31
    assert np.all(t_out.connectivity.delay <= 31)
    assert np.all(t_out.connectivity.delay >= 1)
    assert np.all(t_out.connectivity.delay == 31)


def test_myelinate_clips_delays_and_warns_if_exceeding_31():
    """myelinate clips delays to [1, 31] and warns if any unclipped delay > 31."""
    tissue = Tissue.empty()
    tissue.add_cells(4)
    # Delays of 20 ticks
    tissue.connectivity = SparseConnectivity(
        pre=np.array([0, 1], dtype=np.int32),
        post=np.array([2, 3], dtype=np.int32),
        weight=np.array([100, 100], dtype=np.int32),
        delay=np.array([20, 25], dtype=np.int32)
    )

    # Factor 2.0 scales 20 -> 40 and 25 -> 50 (both > 31)
    stage = Stage(name="myelinate_up", operator="myelinate", params={"factor": Const(2.0)})
    with pytest.warns(UserWarning, match="myelinate: 2 synapses clipped to maximum delay 31"):
        t_out = stage.run(tissue, {}, {}, np.random.default_rng(0))

    assert np.all(t_out.connectivity.delay == 31)

    # Factor 0.05 scales 31 -> 1.55 -> rounds to 2 >= 1
    stage_down = Stage(name="myelinate_down", operator="myelinate", params={"factor": Const(0.01)})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        t_down = stage_down.run(t_out, {}, {}, np.random.default_rng(0))
    assert np.all(t_down.connectivity.delay >= 1)


def test_connect_by_hand_validates_indices_and_delays():
    """connect_by_hand must reject pre/post >= N or < 0 and delay outside [1, 31]."""
    tissue = Tissue.empty()
    tissue.add_cells(10)  # N = 10, valid indices [0, 9]

    # Valid connection works
    stage_valid = Stage(
        name="valid",
        operator="connect_by_hand",
        params={"pre": Const([0, 5]), "post": Const([1, 9]), "delay": Const(15), "weight": Const(50)}
    )
    t = stage_valid.run(tissue, {}, {}, np.random.default_rng(0))
    assert len(t.connectivity.pre) == 2

    # Reject out-of-bounds pre >= N
    stage_bad_pre = Stage(name="bad_pre", operator="connect_by_hand", params={"pre": Const([10]), "post": Const([1])})
    with pytest.raises(ValueError, match="pre index out of range"):
        stage_bad_pre.run(t, {}, {}, np.random.default_rng(0))

    # Reject negative pre
    stage_neg_pre = Stage(name="neg_pre", operator="connect_by_hand", params={"pre": Const([-1]), "post": Const([1])})
    with pytest.raises(ValueError, match="pre index out of range"):
        stage_neg_pre.run(t, {}, {}, np.random.default_rng(0))

    # Reject out-of-bounds post >= N
    stage_bad_post = Stage(name="bad_post", operator="connect_by_hand", params={"pre": Const([0]), "post": Const([15])})
    with pytest.raises(ValueError, match="post index out of range"):
        stage_bad_post.run(t, {}, {}, np.random.default_rng(0))

    # Reject delay > 31
    stage_delay_high = Stage(
        name="delay_high",
        operator="connect_by_hand",
        params={"pre": Const([0]), "post": Const([1]), "delay": Const(32)}
    )
    with pytest.raises(ValueError, match="delay out of kernel limit"):
        stage_delay_high.run(t, {}, {}, np.random.default_rng(0))

    # Reject delay < 1 (e.g. 0)
    stage_delay_zero = Stage(
        name="delay_zero",
        operator="connect_by_hand",
        params={"pre": Const([0]), "post": Const([1]), "delay": Const(0)}
    )
    with pytest.raises(ValueError, match="delay out of kernel limit"):
        stage_delay_zero.run(t, {}, {}, np.random.default_rng(0))
