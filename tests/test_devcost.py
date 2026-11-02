"""D3: development cost model and `estimate --project`."""
import json
import subprocess
import sys

import numpy as np
import pytest

from neurogenesis.cost import CostError
from neurogenesis.devcost import check_development, estimate_development, schedule_rows
from neurogenesis.stages.base import run_schedule

BOX = {"box": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}}


def _project(n=500, prob=0.5, reps=2):
    return {"version": "1.0.0", "geometry": BOX, "fields": {}, "genome": {}, "plugins": [], "metadata": {},
            "schedule": [{"name": "seed", "operator": "seed_cells", "params": {"N": n, "geometry": "box"}},
                         {"name": "div", "operator": "proliferate", "params": {"prob": prob}, "repeat": reps},
                         {"name": "wire", "operator": "connect_by_hand",
                          "params": {"rules": [{"prob": 0.01, "max_distance": 0.2}]}}]}


def test_predicted_cells_match_a_run_and_repeats_are_expanded():
    p = _project()
    rows = schedule_rows(p)
    assert [r["name"] for r in rows] == ["seed", "div", "div", "wire"]
    assert rows[0]["N_after"] == 500 and rows[1]["N_after"] == 750 and rows[2]["N_after"] == 1125
    t = run_schedule(p, {}, 0)
    assert abs(len(t.alive) - rows[-1]["N_after"]) < 0.1 * rows[-1]["N_after"]
    assert rows[-1]["E_after"] >= len(t.connectivity.pre)                   # synapses: an upper estimate


def test_gene_params_use_their_upper_bound():
    p = _project()
    p["schedule"][1]["params"]["prob"] = {"path": ["p"], "lo": 0.0, "hi": 1.0}
    assert schedule_rows(p)[2]["N_after"] == 2000


def test_estimate_and_refusal():
    e = estimate_development(_project(), calibrated=False)
    assert e["fits"] and e["cells"] == 1125 and e["peak_bytes"] > 0 and e["ops"] > 0
    huge = _project(n=10 ** 9, reps=8)
    with pytest.raises(CostError, match="DOES NOT FIT"):
        check_development(huge)
    assert check_development(huge, force=True)["fits"] is False


def test_peak_memory_within_factor_three_of_a_run():
    import tracemalloc
    p = _project(n=4000, reps=1)
    p["schedule"] = p["schedule"][:2]
    e = estimate_development(p, calibrated=False)
    tracemalloc.start()
    run_schedule(p, {}, 0)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert e["peak_bytes"] / 3 <= peak <= e["peak_bytes"] * 3


def test_cli_estimate_project(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(_project()))
    env = {"NEUROGENESIS_CACHE": str(tmp_path / "cache"), "JAX_PLATFORMS": "cpu", "PATH": "/usr/bin:/bin"}
    import os
    env = {**os.environ, **env}
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "estimate", "--project", str(path)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "fits: 1,125 cells" in r.stdout and "wire" in r.stdout and "about" in r.stdout
    assert (tmp_path / "cache" / "throughput.json").exists()                # calibrated once, cached
