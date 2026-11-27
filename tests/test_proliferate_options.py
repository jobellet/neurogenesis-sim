"""Crowding, resting stem cells and division budgets in `proliferate`: neutral defaults, behaviour, determinism."""
import numpy as np
import pytest

from neurogenesis.stages.population import Proliferate
from neurogenesis.tissue import Tissue


def _tissue(N=1, names=("rest", "count"), positions=None):
    t = Tissue.empty(K=len(names))
    t.add_cells(N, positions=np.zeros((N, 3)) if positions is None else positions, K=len(names))
    t.expression_names = list(names)
    return t


def _state(t):
    return (t.positions.tobytes(), t.cell_type.tobytes(), t.cycling.tobytes(), t.expression.tobytes(),
            t.parent_id.tobytes(), t.generation.tobytes())


def _grow(params, calls, seed=0, t=None):
    t = _tissue() if t is None else t
    rng = np.random.default_rng(seed)
    sizes = []
    for _ in range(calls):
        t = Proliferate().run(t, params, {}, {}, rng)
        sizes.append(int(t.alive.sum()))
    return t, sizes


def test_neutral_options_change_nothing_and_draw_no_random_numbers():
    base = {"prob": 0.7, "jitter": 0.5}
    a, _ = _grow(base, 6, seed=3)
    b, _ = _grow({**base, "crowding_radius": 0.0, "budget_channel": "count"}, 6, seed=3)
    assert a.positions.tobytes() == b.positions.tobytes() and a.parent_id.tobytes() == b.parent_id.tobytes()


def test_crowding_slows_growth_from_exponential_to_a_border_front():
    free, free_sizes = _grow({"prob": 1.0, "jitter": 1.0}, 8)
    crowded, sizes = _grow({"prob": 1.0, "jitter": 1.0, "crowding_radius": 1.5, "crowding_k": 4,
                            "crowding_min": 0.0}, 8)
    assert free_sizes[-1] == 2 ** 8
    assert sizes[-1] < free_sizes[-1] // 4
    growth = np.diff(sizes[-4:]) / np.asarray(sizes[-4:-1])
    assert np.all(growth < 0.9)                      # relative growth per call well below doubling


def test_crowding_min_one_is_neutral():
    a, _ = _grow({"prob": 0.6, "jitter": 1.0}, 5, seed=1)
    b, _ = _grow({"prob": 0.6, "jitter": 1.0, "crowding_radius": 2.0, "crowding_min": 1.0}, 5, seed=1)
    assert a.positions.tobytes() == b.positions.tobytes()


def test_resting_cells_wake_after_min_rest_and_may_return_to_rest():
    t = _tissue()
    t.expression[0, 0] = 1.0                         # resting
    params = {"prob": 1.0, "rest_channel": "rest", "activation_prob": 1.0, "min_rest": 2}
    t, sizes = _grow(params, 3, t=t)
    assert sizes == [1, 1, 2]                        # rests two calls, wakes and divides on the third
    assert np.all(t.expression[:, 0] == 0.0)

    t = _tissue()
    t, sizes = _grow({"prob": 1.0, "rest_channel": "rest", "rest_after_division": 1.0,
                      "activation_prob": 0.0}, 4, t=t)
    assert sizes == [2, 3, 4, 5]                     # every mother rests after dividing; only the newest divides
    assert np.all(t.expression[:-1, 0] >= 1.0) and t.expression[-1, 0] == 0.0


def test_division_budget_stops_cycling_and_resets_on_asymmetric_division():
    t, sizes = _grow({"prob": 1.0, "budget": 3, "budget_channel": "count"}, 6)
    assert sizes[-1] == 8 and not np.any(t.cycling)

    # A stem cell (type 0) exempt from the budget makes progenitors (type 1) that divide twice each.
    t, sizes = _grow({"prob": 1.0, "asymmetric_prob": 1.0, "daughter_type": 1, "budget": 2,
                      "budget_channel": "count", "budget_types": [1]}, 1)
    stem_only = {"prob": 1.0, "budget": 2, "budget_channel": "count", "budget_types": [1]}
    t, sizes = _grow(stem_only, 4, t=t)
    assert t.cycling[0] and t.cell_type[0] == 0
    progenitors = t.cell_type == 1
    assert np.all(t.expression[progenitors & ~t.cycling, 1] >= 2)
    assert np.all(t.expression[progenitors & t.cycling, 1] < 2)


def test_options_are_deterministic_and_validated():
    params = {"prob": 0.8, "jitter": 1.0, "crowding_radius": 1.2, "rest_channel": "rest",
              "activation_prob": 0.5, "rest_after_division": 0.3, "budget": 4, "budget_channel": "count"}
    a, _ = _grow(params, 6, seed=11)
    b, _ = _grow(params, 6, seed=11)
    assert _state(a) == _state(b)
    with pytest.raises(ValueError):
        Proliferate().run(_tissue(), {"prob": 1.0, "budget": 2}, {}, {}, np.random.default_rng(0))
    with pytest.raises(ValueError):
        Proliferate().run(_tissue(), {"prob": 1.0, "rest_channel": "missing"}, {}, {}, np.random.default_rng(0))
