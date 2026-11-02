import copy
import json
import time
import tracemalloc
from pathlib import Path

import numpy as np

from neurogenesis.stages.critical_period import CriticalPeriodGate, inhibitory_maturity
from neurogenesis.stages.refinement import RefineByActivityStage
from neurogenesis.tissue import Tissue, SparseConnectivity

PROFILE_PATH = Path(__file__).resolve().parents[1] / "examples" / "profiles" / "critical_period_gate.json"
REFINE = {"ticks": 30, "rule": "stdp", "A_plus": 1.2, "A_minus": 1.0, "w_max": 10000.0}
GATE = {"source_type": 1, "open_threshold": 20.0, "close_after": 2}


def _tissue(inh=-5):
    """Three firing excitatory cells (type 0) in a ring and one inhibitory cell (type 1) onto two of them."""
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3)), cell_type=np.array([0, 0, 0, 1], np.int32),
                sign=np.array([1, 1, 1, -1], np.int8), mode=np.ones(4, np.int32), poisson_hz=np.full(4, 1000.0))
    t.connectivity = SparseConnectivity(np.array([0, 1, 2, 3, 3], np.int32), np.array([1, 2, 0, 0, 1], np.int32),
                                        np.array([10, 10, 10, inh, inh], np.int32), np.ones(5, np.int32))
    return t


def _step(t, gate, seed):
    """One gate call followed by refine_by_activity; True if the weights changed."""
    t = CriticalPeriodGate().run(t, gate, {}, {}, np.random.default_rng(0))
    before = t.connectivity.weight.copy()
    t = RefineByActivityStage().run(t, REFINE, {}, {}, np.random.default_rng(seed))
    return t, not np.array_equal(before, t.connectivity.weight)


def test_neutral_is_noop():
    t = _tissue()
    out = CriticalPeriodGate().run(copy.deepcopy(t), {}, {}, {}, np.random.default_rng(0))
    assert out.connectivity.plastic is None and getattr(out, "_critical_period", None) is None
    assert np.array_equal(out.connectivity.weight, t.connectivity.weight)
    assert CriticalPeriodGate.cost(100, 1000, {}) == (0, 0)


def test_inhibitory_maturity_measures():
    t = _tissue(inh=-6)
    allc = np.ones(4, dtype=bool)
    assert inhibitory_maturity(t, 1, allc, "mean") == 6.0
    assert inhibitory_maturity(t, 1, allc, "sum") == 3.0      # 12 over 4 targets
    assert inhibitory_maturity(t, 0, allc) == 0.0             # excitatory source: no inhibitory weight


def test_window_opens_on_inhibitory_maturity_and_closes():
    t = _tissue(inh=-5)
    # Before opening (inhibition below threshold): no plasticity changes weights.
    t, changed = _step(t, GATE, 1)
    assert not changed and t._critical_period["phase"] == "pre" and not t.connectivity.plastic.any()
    # Inhibition matures past the threshold: the window opens and refine_by_activity changes weights.
    t.connectivity.weight[3:] = -30
    t, changed = _step(t, GATE, 2)
    assert changed and t._critical_period["phase"] == "open"
    t, changed = _step(t, GATE, 3)
    assert changed and t._critical_period["age"] == 1
    # close_after = 2 gate calls since opening: closed, weights frozen from now on.
    t, changed = _step(t, GATE, 4)
    assert not changed and t._critical_period["phase"] == "closed"
    t, changed = _step(t, GATE, 5)
    assert not changed
    # Reopening (as chondroitinase ABC treatment) restores plasticity.
    t, changed = _step(t, {**GATE, "reopen": True}, 6)
    assert changed and t._critical_period["phase"] == "open"


def test_close_threshold_explicit_actions_and_targets():
    t = _tissue(inh=-30)
    gate = {"source_type": 1, "open_threshold": 20.0, "close_threshold": 40.0}
    t, changed = _step(t, gate, 1)
    assert changed
    t.connectivity.weight[3:] = -50                            # maturity past the closing threshold
    t, changed = _step(t, gate, 2)
    assert not changed and t._critical_period["phase"] == "closed"
    # After reopening, the maturity criterion no longer closes the window; an explicit close does.
    t, changed = _step(t, {**gate, "reopen": True}, 3)
    t, changed = _step(t, gate, 4)
    assert changed
    t, changed = _step(t, {"close": True}, 5)
    assert not changed
    # Explicit opening, gating only synapses onto type-1 cells: the others keep their mask.
    t2 = CriticalPeriodGate().run(_tissue(), {"close": True, "target_type": 1}, {}, {}, np.random.default_rng(0))
    assert t2.connectivity.plastic.all()                         # no synapse targets cell type 1
    t3 = CriticalPeriodGate().run(_tissue(), {"open": True}, {}, {}, np.random.default_rng(0))
    assert t3.connectivity.plastic.all() and t3._critical_period["phase"] == "open"
    t4 = CriticalPeriodGate().run(_tissue(), {"maturity": 3.0, "open_threshold": 2.0}, {}, {}, np.random.default_rng(0))
    assert t4._critical_period["phase"] == "open"


def test_determinism():
    def grow():
        t = _tissue(inh=-30)
        for s in range(4):
            t, _ = _step(t, GATE, s)
        return t
    a, b = grow(), grow()
    assert np.array_equal(a.connectivity.weight, b.connectivity.weight)
    assert np.array_equal(a.connectivity.plastic, b.connectivity.plastic)
    assert a._critical_period == b._critical_period


def test_profile_has_sources():
    prof = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert prof["citations"] and prof["windows"]


def test_cost_within_factor_3():
    params = {"source_type": 1, "open_threshold": 10.0}

    def run(N, E):
        rng = np.random.default_rng(0)
        t = Tissue.empty()
        t.add_cells(N, cell_type=(np.arange(N) % 5 == 0).astype(np.int32))
        t.connectivity = SparseConnectivity(rng.integers(0, N, E).astype(np.int32), rng.integers(0, N, E).astype(np.int32),
                                            rng.integers(-50, 50, E).astype(np.int32), np.ones(E, np.int32))
        tracemalloc.start()
        t0 = time.perf_counter()
        CriticalPeriodGate().run(t, params, {}, {}, rng)
        dt = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        return peak, dt

    peak, _ = run(20000, 200000)
    declared = CriticalPeriodGate.cost(20000, 200000, params)[0]
    assert declared / 3 <= peak <= declared * 3
    small = min(run(20000, 200000)[1] for _ in range(3))
    big = min(run(80000, 800000)[1] for _ in range(3))
    ratio = CriticalPeriodGate.cost(80000, 800000, params)[1] / CriticalPeriodGate.cost(20000, 200000, params)[1]
    assert ratio / 3 <= big / small <= ratio * 3
