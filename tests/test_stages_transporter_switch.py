"""C21 transporter_switch: per-cell chloride reversal potential from maturation (Rivera et al. 1999, Nature;
Ben-Ari 2002, Nat Rev Neurosci)."""
import json
import time
import tracemalloc
from pathlib import Path

import numpy as np

import neurogenesis.stages  # noqa: F401
from neurogenesis.spiking.batch import simulate_counts
from neurogenesis.stages.pharmacology import TransporterSwitch
from neurogenesis.tissue import SparseConnectivity, Tissue

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "profiles" / "transporter_switch.json"
RECEPTORS = ROOT / "examples" / "profiles" / "example_receptors.json"
GABA_A = 4                                                  # receptor class of "gaba_a" in example_receptors.json


def _run(t, params, seed=0):
    return TransporterSwitch().run(t, params, {}, {}, np.random.default_rng(seed))


def _params(**kw):
    p = dict(e_immature=-45.0, e_mature=-75.0, midpoint=5.0, width=1.0, receptors=["gaba_a"], profile=str(RECEPTORS))
    p.update(kw)
    return p


def _circuit():
    """Cell 0 (GABAergic driver) -> cells 1 (born at 10: age 0, immature) and 2 (born at 0: age 10, mature) through
    GABA-A synapses; cell 3 is an unconnected control."""
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3)), birth_time=np.array([0, 10, 0, 0], np.float32),
                sign=np.array([-1, 1, 1, 1]))
    t.connectivity = SparseConnectivity(np.array([0, 0], np.int32), np.array([1, 2], np.int32),
                                        np.array([-300, -300], np.int32), np.array([1, 1], np.int32),
                                        receptor_class=np.array([GABA_A, GABA_A], np.uint8))
    return t


def test_reference_profile_lists_cited_defaults():
    prof = json.loads(PROFILE.read_text())
    assert any("Rivera" in c for c in prof["citations"]) and any("Ben-Ari" in c for c in prof["citations"])
    p = prof["params"]
    assert p["e_immature"] > p["v_rest"] > p["e_mature"]
    assert 4.5 <= p["midpoint"] - 2.2 * p["width"] and p["midpoint"] + 2.2 * p["width"] <= 10.5


def test_neutral_params_are_noop():
    for params in ({}, {"e_immature": -45.0, "e_mature": -75.0}, _params(receptors=[7])):
        t = _circuit()
        before = (t.connectivity.weight.copy(), t.connectivity.e_rev)
        t = _run(t, params)
        np.testing.assert_array_equal(t.connectivity.weight, before[0])
        assert t.connectivity.e_rev is before[1] is None


def test_determinism_and_gradual_per_cell_switch():
    a, b = _run(_circuit(), _params(), 1), _run(_circuit(), _params(), 2)
    np.testing.assert_array_equal(a.connectivity.e_rev, b.connectivity.e_rev)
    e = a.connectivity.e_rev
    assert -46.0 < e[0] < -45.0 and -75.0 < e[1] < -74.0           # young cell immature, old cell mature
    t = _circuit()
    t.connectivity.post[:] = 3                                     # cell 3 has age 10: same as cell 2
    t.birth_time[3] = 5.0                                          # now age 5 = midpoint: halfway
    np.testing.assert_allclose(_run(t, _params()).connectivity.e_rev, -60.0, atol=1e-4)


def test_activity_advances_the_switch():
    t = _circuit()
    t.birth_time[:] = [0, 7, 7, 0]                                 # cells 1 and 2 have the same age (0)
    quiet = _run(t, _params()).connectivity.e_rev.copy()
    assert quiet[0] == quiet[1]
    t = _circuit()
    t.birth_time[:] = [0, 7, 7, 0]
    active = _run(t, _params(activity=np.array([0, 0, 8.0, 0]), activity_gain=1.0)).connectivity.e_rev
    assert active[0] == quiet[0] and active[1] < -70.0 < quiet[1]  # the active cell switches earlier
    t = _circuit()
    t.birth_time[:] = [0, 7, 7, 0]
    zero_gain = _run(t, _params(activity=np.array([0, 0, 8.0, 0]), activity_gain=0.0)).connectivity.e_rev
    np.testing.assert_array_equal(zero_gain, quiet)               # gain 0: purely programmed


def _ext(n, drive):
    e = np.zeros((1, n), np.int32)
    e[0, 1:] = drive
    return [e]


def test_gaba_depolarises_immature_and_hyperpolarises_mature_conductance_model():
    """Conductance-based `two_compartment` (P4, EL = -65 mV): the driver fires (Poisson) and the three other cells get
    the same weak suprathreshold drive; GABA onto the immature cell (E_Cl -45 mV) raises its rate above the control,
    onto the mature cell (E_Cl -75 mV) lowers it."""
    t = _run(_circuit(), _params())
    t.mode[0], t.poisson_hz[0] = 1, 200.0
    counts = simulate_counts([t.to_network()], _ext(4, 10), ticks=400, model="two_compartment")[0][0]
    assert counts[1] > counts[3] > counts[2]


def test_gaba_sign_for_integer_lif_with_v_rest():
    """`lif_int` ignores e_rev; with `v_rest` the signed weights follow E_Cl - v_rest."""
    t = _run(_circuit(), _params(v_rest=-65.0))
    assert t.connectivity.weight.tolist() == [300, -300]
    t.mode[0], t.poisson_hz[0] = 1, 200.0
    counts = simulate_counts([t.to_network()], _ext(4, 10), ticks=400, model="lif_int")[0][0]
    assert counts[1] > counts[3] > counts[2]


def test_clock_now_and_age_params():
    t = _circuit()
    t.birth_stage[:] = [0, 3, 0, 0]
    e = _run(t, _params(clock="birth_stage", now=3, midpoint=1.5, width=0.1)).connectivity.e_rev
    assert e[0] > -46.0 and e[1] < -74.0
    e = _run(_circuit(), _params(age=np.array([0, 10.0, 0, 0]))).connectivity.e_rev
    assert e[0] < -74.0 and e[1] > -46.0


def test_cost_within_factor_3():
    params = _params(receptors=[GABA_A], profile=None)

    def run(N):
        E = 4 * N
        rng = np.random.default_rng(0)
        t = Tissue.empty()
        t.add_cells(N, positions=np.zeros((N, 3)), birth_time=rng.random(N).astype(np.float32) * 10)
        t.connectivity = SparseConnectivity(rng.integers(0, N, E).astype(np.int32), rng.integers(0, N, E).astype(np.int32),
                                            np.full(E, -100, np.int32), np.ones(E, np.int32),
                                            receptor_class=np.full(E, GABA_A, np.uint8))
        tracemalloc.start()
        t0 = time.perf_counter()
        _run(t, params)
        dt = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        return peak, dt, TransporterSwitch.cost(N, E, params)

    peak, _, (declared, _) = run(20000)
    assert declared / 3 <= peak <= declared * 3
    small = min(run(50000)[1] for _ in range(3))
    big = min(run(200000)[1] for _ in range(3))
    ratio = TransporterSwitch.cost(200000, 800000, params)[1] / TransporterSwitch.cost(50000, 200000, params)[1]
    assert ratio / 3 <= big / small <= ratio * 3
