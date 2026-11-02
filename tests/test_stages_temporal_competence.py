import json
import time
import tracemalloc
from pathlib import Path

import numpy as np

from neurogenesis.fields import AnalyticField
from neurogenesis.params import Const, Field
from neurogenesis.stages.differentiation import Differentiate, TemporalCompetence
from neurogenesis.stages.population import CellCycleClock, Proliferate, SeedCells
from neurogenesis.tissue import Tissue


PROFILE_PATH = Path(__file__).resolve().parents[1] / "examples" / "profiles" / "temporal_competence.json"


def _load_profile():
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_temporal_competence_neutral_noop():
    t = Tissue.empty(K=2)
    t.add_cells(8, positions=np.ones((8, 3)), expression=np.full((8, 2), 0.5, dtype=np.float32))
    before = t.expression.copy()

    stage = TemporalCompetence()
    out1 = stage.run(t, {}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(out1.expression, before)

    out2 = stage.run(t, {"channels": []}, {}, {}, np.random.default_rng(0))
    assert np.array_equal(out2.expression, before)


def test_temporal_competence_determinism_and_birth_order_fates():
    prof = _load_profile()
    channels = prof["channels"]
    diff_types = prof["differentiate_types"]

    def grow_lineage(seed):
        rng = np.random.default_rng(seed)
        t = Tissue.empty()
        t = SeedCells().run(t, {"N": 20, "position": [0.0, 0.0, 0.0]}, {}, {}, rng)
        for _ in range(11):
            t = CellCycleClock().run(t, {"k": 0.009, "a": 1.97}, {}, {}, rng)
            t = TemporalCompetence().run(t, {"channels": channels}, {}, {}, rng)
            t = Proliferate().run(t, {"prob": 1.0, "jitter": 0.01}, {}, {}, rng)
        t = Differentiate().run(t, {"types": diff_types}, {}, {}, rng)
        return t

    t1 = grow_lineage(7)
    t2 = grow_lineage(7)
    assert np.array_equal(t1.expression, t2.expression)
    assert np.array_equal(t1.cell_type, t2.cell_type)

    # Verify one rule table assigns birth-order-dependent fates matching the competence windows:
    # CC1-CC3 -> type 0 (VI), CC4-CC6 -> type 1 (V), CC7-CC9 -> type 2 (IV), CC10-CC11 -> type 3 (II/III)
    assert np.all(t1.cell_type[(t1.generation >= 1) & (t1.generation <= 3)] == 0)
    assert np.all(t1.cell_type[(t1.generation >= 4) & (t1.generation <= 6)] == 1)
    assert np.all(t1.cell_type[(t1.generation >= 7) & (t1.generation <= 9)] == 2)
    assert np.all(t1.cell_type[(t1.generation >= 10) & (t1.generation <= 11)] == 3)


def test_temporal_competence_heterochronic_transplantation_outcomes():
    """Acceptance test (docs/ROADMAP.md C15): simulate the three heterochronic transplantation outcomes
    by moving cells between young and old tissues."""
    prof = _load_profile()
    channels = prof["channels"]
    diff_types = prof["differentiate_types"]
    rng = np.random.default_rng(42)

    young_fields = {"host_env": AnalyticField("2.0")}
    old_fields = {"host_env": AnalyticField("10.0")}
    comp_params = {"channels": channels, "environment": Field(name="host_env")}

    # Grow young donor tissue at cycle 2 (competence window for fate 0, with both cycling and postmitotic cells)
    young_donor = Tissue.empty()
    young_donor.add_cells(
        10,
        positions=np.zeros((10, 3)),
        generation=np.full(10, 2, dtype=np.int32),
        cycling=np.ones(10, dtype=bool),
    )
    young_donor = TemporalCompetence().run(young_donor, comp_params, {}, young_fields, rng)
    # First 5 cells exit the cell cycle at CC2 (postmitotic deep-layer neurons); next 5 remain cycling S-phase progenitors
    young_donor.cycling[:5] = False

    # Grow old donor tissue at cycle 10 (competence restricted to superficial fate 3)
    old_donor = Tissue.empty()
    old_donor.add_cells(
        10,
        positions=np.zeros((10, 3)),
        generation=np.full(10, 10, dtype=np.int32),
        cycling=np.ones(10, dtype=bool),
    )
    old_donor = TemporalCompetence().run(old_donor, comp_params, {}, old_fields, rng)
    old_donor.cycling[:5] = False  # 5 postmitotic late neurons, 5 cycling late progenitors

    # --- Experiment A: Transplant young cells (5 postmitotic + 5 cycling) into an OLD host tissue ---
    old_host = old_donor.subset(np.arange(10))
    transplanted_young = young_donor.subset(np.arange(10))
    chimera_old_host = Tissue.concatenate([old_host, transplanted_young])

    # Run competence and differentiation in the old host environment (host_env = 10.0)
    chimera_old_host = TemporalCompetence().run(chimera_old_host, comp_params, {}, old_fields, rng)
    chimera_old_host = Differentiate().run(chimera_old_host, {"types": diff_types}, {}, old_fields, rng)

    # Outcome 1: Young postmitotic cells (indices 10..14) keep their early deep-layer fate (type 0)
    assert chimera_old_host.cell_type[10:15].tolist() == [0] * 5
    # Outcome 2: Young cycling progenitors (indices 15..19) moved into the old host adopt the old (superficial) fate (type 3)
    assert chimera_old_host.cell_type[15:20].tolist() == [3] * 5

    # --- Experiment B: Transplant old cycling progenitors into a YOUNG host tissue ---
    young_host = young_donor.subset(np.arange(10))
    transplanted_old_progenitors = old_donor.subset(np.arange(5, 10))  # cycling old progenitors
    chimera_young_host = Tissue.concatenate([young_host, transplanted_old_progenitors])

    # Run competence and differentiation in the young host environment (host_env = 2.0)
    chimera_young_host = TemporalCompetence().run(chimera_young_host, comp_params, {}, young_fields, rng)
    chimera_young_host = Differentiate().run(chimera_young_host, {"types": diff_types}, {}, young_fields, rng)

    # Outcome 3: Old cycling progenitors (indices 10..14) moved into a young environment do NOT regain early fates (stay type 3)
    assert chimera_young_host.cell_type[10:15].tolist() == [3] * 5


def test_temporal_competence_cost_within_factor_3():
    prof = _load_profile()
    params = {"channels": Const(prof["channels"])}

    def run(N):
        t = Tissue.empty(K=4)
        t.add_cells(N, positions=np.zeros((N, 3)), generation=np.full(N, 5, dtype=np.int32))
        t.expression[:] = 1.0
        tracemalloc.start()
        t0 = time.perf_counter()
        TemporalCompetence().run(t, params, {}, {}, np.random.default_rng(0))
        dt = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        return peak, dt, TemporalCompetence.cost(N, 0, params)

    peak, _, (declared_bytes, _) = run(20000)
    assert declared_bytes / 3 <= peak <= declared_bytes * 3

    small = min(run(50000)[1] for _ in range(3))
    big = min(run(200000)[1] for _ in range(3))
    ratio_ops = TemporalCompetence.cost(200000, 0, params)[1] / TemporalCompetence.cost(50000, 0, params)[1]
    assert ratio_ops / 3 <= big / small <= ratio_ops * 3

