"""C28: random sparse convergence (`random_projection`), BTSPRule, ConsolidationRule."""
import tracemalloc

import jax.numpy as jnp
import numpy as np

import neurogenesis.stages  # noqa: F401
from neurogenesis.spiking.plasticity import BTSPRule, ConsolidationRule
from neurogenesis.stages.base import STAGE_REGISTRY, run_schedule
from neurogenesis.tissue import Tissue


def _tissue(n_src=50, n_tgt=200):
    t = Tissue.empty()
    t.add_cells(n_src, positions=np.zeros((n_src, 3)), cell_type=np.zeros(n_src, np.int32))
    t.add_cells(n_tgt, positions=np.ones((n_tgt, 3)), cell_type=np.ones(n_tgt, np.int32))
    return t


def _run(t, params, seed=0):
    return STAGE_REGISTRY["random_projection"]().run(t, params, {}, {}, np.random.default_rng(seed))


def test_random_projection_fan_in_distinct_neutral_and_deterministic():
    p = {"sources": {"cell_type": [0]}, "targets": {"cell_type": [1]}, "fan_in": 6, "weight": 300, "delay": 2}
    t = _run(_tissue(), p)
    c = t.connectivity
    assert len(c.pre) == 200 * 6 and set(np.unique(c.post)) == set(range(50, 250))
    for j in range(50, 250):
        s = c.pre[c.post == j]
        assert len(set(s.tolist())) == 6 and np.all(s < 50)
    assert np.all(c.weight == 300) and np.all(c.delay == 2)
    t2 = _run(_tissue(), p)
    np.testing.assert_array_equal(t2.connectivity.pre, c.pre)
    assert len(_run(_tissue(), dict(p, fan_in=0)).connectivity.pre) == 0
    few = _run(_tissue(3, 10), dict(p, fan_in=6)).connectivity                 # fewer sources than fan_in: all of them
    assert len(few.pre) == 30
    t3 = _tissue(20, 0)
    own = _run(t3, {"sources": {"cell_type": [0]}, "targets": {"cell_type": [0]}, "fan_in": 5}).connectivity
    assert np.all(own.pre != own.post) and len(own.pre) == 100


def test_random_projection_through_run_schedule():
    pts = [[0.0, float(i), 0.0] for i in range(10)]
    proj = {"fields": {}, "schedule": [
        {"name": "a", "operator": "seed_cells", "params": {"points": pts, "region": 1, "cell_type": 1}},
        {"name": "b", "operator": "seed_cells", "params": {"points": pts, "region": 2, "cell_type": 2}},
        {"name": "p", "operator": "random_projection",
         "params": {"sources": {"region": [1]}, "targets": {"region": [2]}, "fan_in": 3, "weight": 100}}]}
    t = run_schedule(proj, {}, 0)
    reg = np.asarray(t.region)
    assert len(t.connectivity.pre) == 30 and np.all(reg[t.connectivity.pre] == 1) and np.all(reg[t.connectivity.post] == 2)


def test_random_projection_declared_memory_within_factor_three():
    t = _tissue(1000, 1000)
    p = {"sources": {"cell_type": [0]}, "targets": {"cell_type": [1]}, "fan_in": 6}
    tracemalloc.start()
    _run(t, p)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared = STAGE_REGISTRY["random_projection"].cost(1000, 0, p)[0]
    assert declared / 3 <= peak <= declared * 3


def _btsp_run(rule, w0, pre_times, plateau_t, T=6000):
    """One synapse onto one cell; pre spikes at pre_times (ms), one plateau at plateau_t."""
    w = jnp.asarray([w0], jnp.float32)
    et, is_ = rule.init_state(1, 1)
    post = jnp.asarray([0])
    for t in range(T):
        w, et, is_ = rule.step(w, post, jnp.asarray([1.0 if t in pre_times else 0.0]),
                               jnp.asarray([1.0 if t == plateau_t else 0.0]), et, is_)
    return float(w[0])


def test_btsp_one_shot_window_before_and_after_bidirectional():
    r = BTSPRule(eta=5e-4, tau_et=1000.0, tau_is=1000.0, w_max=1000.0)
    w_before = _btsp_run(r, 100.0, {2000}, 3000)          # input 1 s before the plateau
    w_after = _btsp_run(r, 100.0, {4000}, 3000)           # input 1 s after
    w_far = _btsp_run(r, 100.0, {0}, 5900, T=6000)        # input ~6 s before
    w_none = _btsp_run(r, 100.0, set(), 3000)
    assert w_before > 150 and w_after > 150 and w_none == 100.0
    assert w_far - 100 < 0.2 * (w_before - 100)
    w_strong = _btsp_run(r, 950.0, {2900}, 3000)          # strong input near the plateau: depressed
    assert w_strong < 950.0
    assert abs(r.fixed_point() - 1000 / 1.5) < 1e-6
    assert _btsp_run(BTSPRule(eta=0.0), 100.0, {2900}, 3000) == 100.0


def test_btsp_keeps_inhibitory_sign():
    r = BTSPRule(eta=2e-4)
    w = jnp.asarray([-100.0], jnp.float32)
    et, is_ = r.init_state(1, 1)
    w, et, is_ = r.step(w, jnp.asarray([0]), jnp.asarray([1.0]), jnp.asarray([1.0]), et, is_)
    assert float(w[0]) < -100.0


def test_consolidation_off_fast_decay_and_capture():
    off = ConsolidationRule()
    s, u = off.init_state(jnp.asarray([100.0]))
    s, u = off.step(s, u, jnp.asarray([10.0]))
    assert float(s[0]) == 110.0 and float(u[0]) == 0.0
    no_capture = ConsolidationRule(tau_fast=100.0, rate=0.0)
    s, u = no_capture.init_state(jnp.asarray([100.0]))
    s, u = no_capture.step(s, u, jnp.asarray([50.0]))
    for _ in range(1000):
        s, u = no_capture.step(s, u, jnp.asarray([0.0]))
    assert abs(float(no_capture.weight(s, u)[0]) - 100.0) < 0.01           # labile change gone
    capture = ConsolidationRule(tau_fast=100.0, rate=0.01)
    s, u = capture.init_state(jnp.asarray([100.0]))
    s, u = capture.step(s, u, jnp.asarray([50.0]))
    for _ in range(1000):
        s, u = capture.step(s, u, jnp.asarray([0.0]))
    kept = float(capture.weight(s, u)[0]) - 100.0
    assert 10.0 < kept < 50.0                                                # part of it consolidated
    gated = ConsolidationRule(tau_fast=100.0, rate=0.01)
    s, u = gated.init_state(jnp.asarray([100.0]))
    s, u = gated.step(s, u, jnp.asarray([50.0]), gate=0.0)
    for _ in range(1000):
        s, u = gated.step(s, u, jnp.asarray([0.0]), gate=0.0)
    assert abs(float(gated.weight(s, u)[0]) - 100.0) < 0.01                 # no capture signal: nothing kept


def test_random_projection_plastic_mask():
    p = {"sources": {"cell_type": [0]}, "targets": {"cell_type": [1]}, "fan_in": 3, "plastic": False}
    t = _tissue(10, 5)
    t.connectivity = t.connectivity.append([0], [10], [7], [1])              # an earlier synapse (no mask)
    c = _run(t, p).connectivity
    assert c.plastic is not None and bool(c.plastic[0]) and not c.plastic[1:].any() and len(c.pre) == 1 + 15
    assert _run(_tissue(10, 5), dict(p, plastic=None)).connectivity.plastic is None
