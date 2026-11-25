"""Cell selectors handed through `run_schedule` (as `Const(dict)`) select the right cells (bug fixed 2026-11-25: they
were ignored, so every cell grew every neurite type, and `refine_by_activity` drove no source)."""
import numpy as np

import neurogenesis.stages  # noqa: F401
from neurogenesis.stages.base import run_schedule


def _project(extra):
    pts_a = [[0.0, float(i), 0.0] for i in range(5)]
    pts_b = [[10.0, float(i), 0.0] for i in range(5)]
    sched = [{"name": "a", "operator": "seed_cells", "params": {"points": pts_a, "region": 1, "cell_type": 1}},
             {"name": "b", "operator": "seed_cells", "params": {"points": pts_b, "region": 2, "cell_type": 2}}] + extra
    return {"fields": {}, "schedule": sched}


def test_grow_arbors_selector_through_run_schedule():
    t = run_schedule(_project([{"name": "ax", "operator": "grow_arbors",
                                "params": {"cells": {"region": [1]}, "steps": 3, "compartment": "axon"}}]), {}, 0)
    grown = np.unique(t.morphology.cell)
    assert set(np.asarray(t.region)[grown].tolist()) == {1}


def test_secrete_cue_selector_through_run_schedule():
    from neurogenesis.stages.base import STAGE_REGISTRY
    seen = {}
    cls = STAGE_REGISTRY["secrete_cue"]
    orig = cls.run

    def spy(self, tissue, params, genome, fields, rng):
        out = orig(self, tissue, params, genome, fields, rng)
        seen["pts"] = fields["c"].points.copy()
        return out
    cls.run = spy
    try:
        run_schedule(_project([{"name": "s", "operator": "secrete_cue",
                                "params": {"name": "c", "cells": {"cell_type": [2]}, "length": 1.0}}]), {}, 0)
    finally:
        cls.run = orig
    assert len(seen["pts"]) == 5 and np.all(seen["pts"][:, 0] == 10.0)


def test_refine_sources_selector_drives_those_cells():
    t = run_schedule(_project([{"name": "w", "operator": "connect_by_hand", "params": {"pre": [5, 6], "post": [0, 1]}},
                               {"name": "r", "operator": "refine_by_activity",
                                "params": {"rule": "stdp", "ticks": 5, "sources": {"region": [2]}, "poisson_hz": 20.0}}]), {}, 0)
    driven = np.flatnonzero(np.asarray(t.mode) == 1)
    assert len(driven) == 5 and set(np.asarray(t.region)[driven].tolist()) == {2}
