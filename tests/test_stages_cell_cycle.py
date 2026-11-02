import json
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pytest

from neurogenesis.fields import AnalyticField
from neurogenesis.params import Const, Expr, Field, Gene
from neurogenesis.stages.base import run_schedule
from neurogenesis.stages.population import Apoptosis, CellCycleClock, Proliferate, SeedCells
from neurogenesis.tissue import Tissue


PROFILE_PATH = Path(__file__).resolve().parents[1] / "examples" / "profiles" / "cell_cycle_clock.json"


def _load_profile():
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_cell_cycle_clock_neutral_noop():
    t = Tissue.empty(K=2)
    t.add_cells(10, positions=np.ones((10, 3)), generation=np.arange(10, dtype=np.int32))
    gen_before = t.generation.copy()
    cyc_before = t.cycling.copy()
    btime_before = t.birth_time.copy()

    stage = CellCycleClock()
    out_empty = stage.run(t, {}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(out_empty.generation, gen_before)
    assert np.array_equal(out_empty.cycling, cyc_before)
    assert np.array_equal(out_empty.birth_time, btime_before)

    out_k0 = stage.run(t, {"k": 0.0, "a": 1.97}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(out_k0.generation, gen_before)
    assert np.array_equal(out_k0.cycling, cyc_before)
    assert np.array_equal(out_k0.birth_time, btime_before)


def test_cell_cycle_clock_determinism_and_param_sources():
    fields = {"grad": AnalyticField("0.01 + 0.02 * x")}
    genome = {"clock": {"k": 0.05, "a": 1.5}}
    params = {
        "k": Gene(path=("clock", "k"), lo=0.0, hi=1.0),
        "a": Expr(formula="1.5"),
        "T_C": Expr(formula="8.0 + 1.0 * generation"),
    }

    def run_once(seed):
        t = Tissue.empty()
        t.add_cells(50, positions=np.linspace(0.0, 1.0, 150).reshape(50, 3))
        rng = np.random.default_rng(seed)
        for _ in range(4):
            t = CellCycleClock().run(t, params, genome, fields, rng)
            t = Proliferate().run(t, {"prob": 1.0, "jitter": 0.05}, genome, fields, rng)
        return t

    t1 = run_once(42)
    t2 = run_once(42)
    assert np.array_equal(t1.cycling, t2.cycling)
    assert np.array_equal(t1.generation, t2.generation)
    assert np.allclose(t1.birth_time, t2.birth_time)
    assert np.allclose(t1.positions, t2.positions)

    # Also test Field Param for k and table Q
    t_field = Tissue.empty()
    t_field.add_cells(200, positions=np.column_stack([np.linspace(0.0, 10.0, 200), np.zeros((200, 2))]))
    t_field = CellCycleClock().run(
        t_field,
        {"k": Field(name="grad"), "a": Const(1.0)},
        {},
        fields,
        np.random.default_rng(7),
    )
    assert np.any(~t_field.cycling) and np.any(t_field.cycling)


def test_cell_cycle_clock_schedule_acceptance_mouse_profile():
    """Acceptance test (docs/ROADMAP.md C14): 11 x (cell_cycle_clock -> proliferate), averaged over >= 20 seeds."""
    prof = _load_profile()
    k = prof["k"]
    a = prof["a"]
    cycles = prof["cycles"]
    tc_table = prof["T_C_hours"]
    death_prob = prof["basal_death_prob_per_cycle"]

    n_founders = 50
    n_seeds = 25

    q_by_cycle = np.zeros((n_seeds, cycles))
    pve_by_cycle = np.zeros((n_seeds, cycles))
    neurons_no_death = np.zeros(n_seeds)
    cc1_7_fraction = np.zeros(n_seeds)

    clock_stage = CellCycleClock()
    prolif_stage = Proliferate()
    seed_stage = SeedCells()

    for s in range(n_seeds):
        rng = np.random.default_rng(1000 + s)
        t = Tissue.empty()
        t = seed_stage.run(t, {"N": n_founders, "position": [0.0, 0.0, 0.0]}, {}, {}, rng)
        for cc in range(1, cycles + 1):
            cyc_before = int(np.sum(t.alive & t.cycling))
            pve_by_cycle[s, cc - 1] = cyc_before / n_founders
            t = clock_stage.run(t, {"k": k, "a": a, "T_C": tc_table}, {}, {}, rng)
            cyc_after = int(np.sum(t.alive & t.cycling))
            q_by_cycle[s, cc - 1] = (cyc_before - cyc_after) / max(1, cyc_before)
            t = prolif_stage.run(t, {"prob": 1.0, "jitter": 0.01}, {}, {}, rng)

        # After 11 cycles Q(11) = 1.0, so all cells have exited the cycle
        assert not np.any(t.cycling)
        neurons_no_death[s] = int(np.sum(t.alive & ~t.cycling)) / n_founders
        cc1_7_fraction[s] = float(np.mean(t.generation <= 7))

        # Check division/birth times follow cumulative T_C(CC) and frozen exit generation in 1..11
        expected_cum_tc = np.cumsum(tc_table)
        for cc in range(1, cycles + 1):
            mask_cc = t.generation == cc
            if np.any(mask_cc):
                assert np.allclose(t.birth_time[mask_cc], expected_cum_tc[cc - 1], atol=1e-4)

    mean_q = np.mean(q_by_cycle, axis=0)
    expected_q = np.array([min(1.0, k * (cc ** a)) for cc in range(1, cycles + 1)])
    np.testing.assert_allclose(mean_q, expected_q, atol=0.03)

    # CC8 is the first cycle with Q > 0.5, and the progenitor pool peaks at CC8
    first_q_gt_half = int(np.where(mean_q > 0.5)[0][0]) + 1
    assert first_q_gt_half == 8
    mean_pve = np.mean(pve_by_cycle, axis=0)
    peak_pve_cycle = int(np.argmax(mean_pve)) + 1
    assert peak_pve_cycle == 8

    # Neurons per founder ≈ 156 without death (tolerance ±6 across 25 seeds)
    assert abs(float(np.mean(neurons_no_death)) - 156.0) <= 6.0

    # About 27 % of the neurons born in CC1–CC7 (tolerance ±0.025)
    assert abs(float(np.mean(cc1_7_fraction)) - 0.27) <= 0.025

    # Also verify via run_schedule with 11 x (cell_cycle_clock -> proliferate -> apoptosis(prob=0.01))
    schedule_with_death = [{"name": "seed", "operator": "seed_cells", "params": {"N": n_founders, "position": [0.0, 0.0, 0.0]}}]
    for cc in range(1, cycles + 1):
        schedule_with_death.append({"name": f"clock_{cc}", "operator": "cell_cycle_clock", "params": {"q_table": prof["reference_Q"], "T_C": tc_table}})
        schedule_with_death.append({"name": f"prolif_{cc}", "operator": "proliferate", "params": {"prob": 1.0, "jitter": 0.01}})
        schedule_with_death.append({"name": f"apopt_{cc}", "operator": "apoptosis", "params": {"prob": death_prob}})

    neurons_with_death = []
    for s in range(n_seeds):
        t_death = run_schedule({"schedule": schedule_with_death}, genome={}, seed=2000 + s)
        neurons_with_death.append(int(np.sum(t_death.alive)) / n_founders)

    # Neurons per founder ≈ 140 with 1 % death per cycle (tolerance ±6 across 25 seeds)
    assert abs(float(np.mean(neurons_with_death)) - 140.0) <= 6.0


def test_cell_cycle_clock_cost_within_factor_3():
    params = {"k": Const(0.009), "a": Const(1.97), "T_C": Const([8.1, 10.0, 15.0, 20.0])}

    def run(N):
        t = Tissue.empty()
        t.add_cells(N, positions=np.zeros((N, 3)))
        tracemalloc.start()
        t0 = time.perf_counter()
        CellCycleClock().run(t, params, {}, {}, np.random.default_rng(1))
        dt = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        return peak, dt, CellCycleClock.cost(N, 0, params)

    peak, _, (declared_bytes, _) = run(20000)
    assert declared_bytes / 3 <= peak <= declared_bytes * 3

    small = min(run(50000)[1] for _ in range(3))
    big = min(run(200000)[1] for _ in range(3))
    ratio_ops = CellCycleClock.cost(200000, 0, params)[1] / CellCycleClock.cost(50000, 0, params)[1]
    assert ratio_ops / 3 <= big / small <= ratio_ops * 3

