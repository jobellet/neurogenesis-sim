"""Declared parameter ranges (neurogenesis.stages.bounds): each listed stage runs on random values inside them and on
the corners of the box, and the shipped profile defaults lie inside them."""
import itertools
import json
import signal
from pathlib import Path

import numpy as np
import pytest

import neurogenesis.stages  # noqa: F401
from neurogenesis.stages.base import STAGE_REGISTRY
from neurogenesis.stages.bounds import PARAM_BOUNDS, param_bounds
from neurogenesis.tissue import SparseConnectivity, Tissue

ROOT = Path(__file__).resolve().parents[1]
RECEPTORS = str(ROOT / "examples" / "profiles" / "example_receptors.json")
GABA_A = 4


def _cells(n=40, cycling=True):
    t = Tissue.empty()
    rng = np.random.default_rng(0)
    t.add_cells(n, positions=rng.random((n, 3)), birth_time=rng.random(n).astype(np.float32) * 20,
                generation=rng.integers(1, 12, n).astype(np.int32))
    t.cycling[:] = cycling
    return t


def _circuit():
    t = _cells(12, cycling=False)
    pre = np.arange(12, dtype=np.int32) % 6
    post = (np.arange(12, dtype=np.int32) + 3) % 12
    t.connectivity = SparseConnectivity(pre, post, np.full(12, -300, np.int32), np.ones(12, np.int32),
                                        receptor_class=np.full(12, GABA_A, np.uint8))
    return t


def _check_cycle(t):
    assert np.all(np.isfinite(t.positions)) and np.all(np.isfinite(t.birth_time))
    assert t.cycling.dtype == bool


def _check_switch(t):
    assert np.all(np.isfinite(t.connectivity.e_rev[t.connectivity.receptor_class == GABA_A]))


HARNESS = {  # stage -> (tissue factory, fixed parameters, check)
    "proliferate": (lambda: _cells(30), {}, _check_cycle),
    "cell_cycle_clock": (lambda: _cells(30), {}, _check_cycle),
    "transporter_switch": (_circuit, {"receptors": ["gaba_a"], "profile": RECEPTORS}, _check_switch),
}


class _Timeout(Exception):
    pass


def _run(stage, params, seed):
    make, fixed, check = HARNESS[stage]
    t = make()

    def alarm(*_):
        raise _Timeout(f"{stage} {params}: no result after 20 s")

    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(20)
    try:
        out = STAGE_REGISTRY[stage]().run(t, {**fixed, **params}, {}, {}, np.random.default_rng(seed))
    finally:
        signal.alarm(0)
    check(out)


def test_every_bounded_stage_has_a_harness_and_is_registered():
    assert set(PARAM_BOUNDS) == set(HARNESS)
    assert all(s in STAGE_REGISTRY for s in PARAM_BOUNDS)
    assert param_bounds("nothing") is None
    for stage, b in PARAM_BOUNDS.items():
        assert all(lo < hi for lo, hi in b.values()), stage


@pytest.mark.parametrize("stage", sorted(PARAM_BOUNDS))
def test_stage_runs_on_the_corners_and_random_values(stage):
    b = PARAM_BOUNDS[stage]
    names = sorted(b)
    for i, corner in enumerate(itertools.product(*[b[n] for n in names])):
        if i >= 64:                                 # at most 64 corners (transporter_switch has 6 parameters)
            break
        _run(stage, dict(zip(names, corner)), i)
    rng = np.random.default_rng(123)
    for i in range(40):
        _run(stage, {n: float(rng.uniform(*b[n])) for n in names}, i)


def test_profile_defaults_lie_inside_the_declared_ranges():
    sw = json.loads((ROOT / "examples" / "profiles" / "transporter_switch.json").read_text())["params"]
    for k, (lo, hi) in PARAM_BOUNDS["transporter_switch"].items():
        assert lo <= sw[k] <= hi, k
    cc = json.loads((ROOT / "examples" / "profiles" / "cell_cycle_clock.json").read_text())
    for k, (lo, hi) in PARAM_BOUNDS["cell_cycle_clock"].items():
        assert lo <= cc[k] <= hi, k
