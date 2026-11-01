import pytest
import json
import numpy as np

from neurogenesis.stages.base import (
    Stage, register_stage, run_schedule, schedule_cost, STAGE_REGISTRY
)
from neurogenesis.params import Const, Gene, Field, Expr
from neurogenesis.tissue import Tissue


@register_stage("toy_proliferate")
class ToyProliferate:
    @staticmethod
    def cost(N: int, E: int, params: dict):
        return (N * 10, N * 2)

    def run(self, tissue: Tissue, params: dict, genome: dict, fields: dict, rng: np.random.Generator):
        # Adds N cells based on count param
        count = int(params.get("count", Const(5)).value if hasattr(params.get("count"), "value") else params.get("count", 5))
        tissue.add_cells(count)
        return tissue


@register_stage("toy_random_walk")
class ToyRandomWalk:
    def run(self, tissue: Tissue, params: dict, genome: dict, fields: dict, rng: np.random.Generator):
        # Jitter positions using rng
        if len(tissue.positions) > 0:
            tissue.positions += rng.normal(0, 0.1, size=tissue.positions.shape)
        return tissue


def test_stage_registration():
    assert "toy_proliferate" in STAGE_REGISTRY
    assert "toy_random_walk" in STAGE_REGISTRY


def test_schedule_cost():
    project = {
        "schedule": [
            {"operator": "toy_proliferate", "repeat": 2}
        ]
    }
    bytes_cost, ops_cost = schedule_cost(project, N=100, E=0)
    assert bytes_cost == 100 * 10 * 2
    assert ops_cost == 100 * 2 * 2


def test_run_schedule_from_json_dict():
    # Verify that a schedule loaded directly from raw JSON dict executes cleanly
    project_json = """
    {
        "plugins": [],
        "fields": {
            "box_boundary": {"type": "Box", "center": [0, 0, 0], "size": [10, 10, 10]}
        },
        "schedule": [
            {
                "name": "stage_add",
                "operator": "toy_proliferate",
                "params": {"count": {"type": "Const", "value": 4}},
                "repeat": 1
            },
            {
                "name": "stage_walk",
                "operator": "toy_random_walk",
                "params": {},
                "repeat": 1
            }
        ]
    }
    """
    project = json.loads(project_json)
    tissue = run_schedule(project, genome={}, seed=42)
    assert len(tissue.alive) == 4
    assert np.all(tissue.alive)


def test_stage_when_condition():
    # Stage executes only when condition is met
    project = {
        "schedule": [
            {
                "name": "stage_init",
                "operator": "toy_proliferate",
                "params": {"count": 2},
                "repeat": 1
            },
            {
                "name": "stage_conditional_skip",
                "operator": "toy_proliferate",
                "params": {"count": 10},
                "when": "N > 5",  # N=2, so should skip!
                "repeat": 1
            },
            {
                "name": "stage_conditional_run",
                "operator": "toy_proliferate",
                "params": {"count": 3},
                "when": "N == 2",  # N=2, should run!
                "repeat": 1
            }
        ]
    }
    tissue = run_schedule(project, genome={}, seed=42)
    # 2 + 0 + 3 = 5
    assert len(tissue.alive) == 5


def test_schedule_rng_stream_stability_upon_stage_insertion():
    # RULE: Inserting a stage before or after must NOT change random numbers of another named stage!
    project_orig = {
        "schedule": [
            {
                "name": "walk_A",
                "operator": "toy_proliferate",
                "params": {"count": 5},
                "repeat": 1
            },
            {
                "name": "walk_B",
                "operator": "toy_random_walk",
                "params": {},
                "repeat": 1
            }
        ]
    }
    tissue_orig = run_schedule(project_orig, genome={}, seed=999)
    pos_orig = tissue_orig.positions.copy()

    # Now insert a new stage in between
    project_modified = {
        "schedule": [
            {
                "name": "walk_A",
                "operator": "toy_proliferate",
                "params": {"count": 5},
                "repeat": 1
            },
            {
                "name": "walk_INTERMEDIATE",
                "operator": "toy_proliferate",
                "params": {"count": 0},  # no cells added, but a new stage in between
                "repeat": 1
            },
            {
                "name": "walk_B",
                "operator": "toy_random_walk",
                "params": {},
                "repeat": 1
            }
        ]
    }
    tissue_modified = run_schedule(project_modified, genome={}, seed=999)
    pos_modified = tissue_modified.positions.copy()

    # Positions after walk_B must match EXACTLY because name_salt for walk_B is identical!
    assert np.array_equal(pos_orig, pos_modified)


def test_checkpoints():
    project = {
        "schedule": [
            {"name": "s1", "operator": "toy_proliferate", "params": {"count": 2}, "repeat": 1},
            {"name": "s2", "operator": "toy_proliferate", "params": {"count": 3}, "repeat": 1}
        ]
    }
    checkpoints = run_schedule(project, genome={}, seed=1, checkpoints=True)
    assert len(checkpoints) == 2
    assert len(checkpoints[0].alive) == 2
    assert len(checkpoints[1].alive) == 5
