"""Cost estimates: memory counted exactly, refusal of networks that cannot fit, and time estimates that match measured
run times on this machine."""
import time

import numpy as np
import pytest

from neurogenesis import cost
from neurogenesis.spiking.batch import simulate_counts


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cost, "CACHE", tmp_path / "throughput.json")


def test_memory_is_counted_per_array():
    from neurogenesis.spiking.models import get_model
    for m in ("lif_int", "two_compartment", "hh"):
        n, e = 1000, 50000
        assert cost.memory_bytes(m, n, e) == n * (cost.PARAM_BYTES + get_model(m).state_bytes + 4) + e * (cost.SYNAPSE_BYTES + cost.SYNAPSE_WORK_BYTES)
        assert cost.memory_bytes(m, 2 * n, 2 * e) == 2 * cost.memory_bytes(m, n, e) - 0


def test_networks_that_cannot_fit_are_refused_before_allocation():
    with pytest.raises(cost.CostError):
        cost.check("hh", 3 * 10 ** 8, 15 * 10 ** 11, 1000)
    e = cost.check("hh", 3 * 10 ** 8, 15 * 10 ** 11, 1000, force=True)
    assert not e["fits"] and e["verdict"].startswith("DOES NOT FIT")


def test_time_estimate_matches_measured_time():
    net = cost._random_network(3000, 120000, seed=3)
    ext = np.random.default_rng(0).integers(0, 40, (1, 3000)).astype(np.int32)
    for model in ("lif_int", "hh"):
        est = cost.estimate(model, 3000, 120000, 100)
        simulate_counts([net], [ext], ticks=100, model=model, check_cost=False)
        t0 = time.perf_counter()
        simulate_counts([net], [ext], ticks=100, model=model, check_cost=False)
        dt = time.perf_counter() - t0
        assert dt / 4 <= est["seconds_total"] <= dt * 4, (model, dt, est["seconds_total"])


def test_hodgkin_huxley_costs_more_per_neuron_than_integrate_and_fire():
    lif, hhm = (cost.estimate(m, 10 ** 6, 0, 1000) for m in ("lif_int", "hh"))
    assert hhm["seconds_total"] > 5 * lif["seconds_total"] and hhm["ops_per_tick"] > 20 * lif["ops_per_tick"]
