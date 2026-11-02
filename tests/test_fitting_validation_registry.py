"""E2 fitting of Fit params, E3 semi-supervised and Pareto evolution, E4 validation assays, G1 module registry."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from neurogenesis.fitting import METRICS, cmaes, evaluate, fit, register_metric, target_loss, with_fit
from neurogenesis.params import FIT_KEY, Fit, collect_fits, resolve
from neurogenesis.stages.base import run_schedule
from neurogenesis.tissue import SparseConnectivity, Tissue

from test_development import sheet_plan, toy_genome

BOX = {"box": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}}


def _project():
    return {"version": "1.0.0", "geometry": BOX, "fields": {}, "genome": {}, "plugins": [], "metadata": {},
            "schedule": [{"name": "seed", "operator": "seed_cells", "params": {"N": 100, "geometry": "box"}},
                         {"name": "div", "operator": "proliferate",
                          "params": {"prob": {"target": "p_div", "init": 0.1, "lo": 0.0, "hi": 1.0}}, "repeat": 2}]}


# E2 ---------------------------------------------------------------------------------------------------------------
def test_fit_values_resolve_from_the_genome_and_are_clipped():
    p = Fit("a", init=0.2, lo=0.0, hi=1.0)
    assert resolve(p, {}, {}) == 0.2
    assert resolve(p, {FIT_KEY: {"a": 0.7}}, {}) == 0.7
    assert resolve(p, {FIT_KEY: {"a": 3.0}}, {}) == 1.0
    assert collect_fits(_project()) == [("p_div", 0.1, 0.0, 1.0)]


def test_cmaes_minimises_a_quadratic_deterministically():
    f = lambda x: float(np.sum((x - [0.2, 0.8]) ** 2))
    x, best, hist = cmaes(f, np.array([0.5, 0.5]), iterations=40, seed=1)
    np.testing.assert_allclose(x, [0.2, 0.8], atol=1e-3)
    x2, _, _ = cmaes(f, np.array([0.5, 0.5]), iterations=40, seed=1)
    np.testing.assert_array_equal(x, x2)
    assert [h["best"] for h in hist] == sorted([h["best"] for h in hist], reverse=True)


def test_fit_matches_a_cell_count_target_over_seeds():
    r = fit(_project(), [{"metric": "cell_count", "value": 300, "scale": 10}], seeds=(0, 1), iterations=8)
    assert 0.6 < r.values["p_div"] < 0.9                    # 100 (1 + p)^2 = 300 -> p ~ 0.73
    assert all(abs(m[0] - 300) < 20 for m in r.metrics)
    t = run_schedule(_project(), r.genome, 0)                # the fitted genome develops the fitted tissue
    assert abs(len(t.alive) - 300) < 20
    r2 = fit(_project(), [{"metric": "cell_count", "value": 300, "scale": 10}], seeds=(0, 1), iterations=8)
    assert r2.values == r.values


def test_metrics_on_a_toy_tissue():
    t = Tissue.empty()
    t.add_cells(4, positions=np.array([[0, 0, 0], [0.1, 0, 0], [0, 0, 1.0], [5, 5, 5]]), cell_type=np.array([0, 0, 1, 1]))
    t.connectivity = SparseConnectivity(np.array([0, 1], np.int32), np.array([1, 2], np.int32), np.array([1, 1], np.int32),
                                        np.array([1, 1], np.int32))
    loss, vals = target_loss(t, [{"metric": "cell_count", "cell_type": 1, "value": 2},
                                 {"metric": "synapse_count", "pre_cell_type": 0, "value": 2},
                                 {"metric": "mean_in_degree", "post_cell_type": 1, "value": 0.5},
                                 {"metric": "connection_probability", "d_max": 0.5, "value": 0.5},
                                 {"metric": "layer_thickness", "axis": 2, "lower": 0, "upper": 100, "value": 5.0}])
    assert vals == [2.0, 2.0, 0.5, 0.5, 5.0] and loss == 0.0
    with pytest.raises(ValueError, match="unknown metric"):
        target_loss(t, [{"metric": "nope", "value": 0}])


def test_custom_metric_and_firing_rate():
    @register_metric("toy_metric")
    def _m(t, o):
        return 42.0
    assert "toy_metric" in METRICS
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)), mode=np.array([1, 0]), poisson_hz=np.array([100.0, 0.0]),
                threshold=np.array([1024, 1024]))
    loss, vals = target_loss(t, [{"metric": "firing_rate", "ticks": 1000, "cell_type": 0, "value": 0},
                                 {"metric": "toy_metric", "value": 42}])
    assert 25 < vals[0] < 75                                 # (100 Hz + 0 Hz) / 2


def test_cli_fit(tmp_path):
    from neurogenesis.project.io import Project
    Project(**_project()).save(tmp_path / "p.json")
    (tmp_path / "t.json").write_text(json.dumps([{"metric": "cell_count", "value": 200, "scale": 10}]))
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "fit", "--project", str(tmp_path / "p.json"),
                        "--targets", str(tmp_path / "t.json"), "--seeds", "0", "--iterations", "3",
                        "--out", str(tmp_path / "g.json")], capture_output=True, text=True,
                       env={**os.environ, "JAX_PLATFORMS": "cpu"})
    assert r.returncode == 0, r.stderr
    assert "p_div" in json.loads((tmp_path / "g.json").read_text())[FIT_KEY]


# E3 ---------------------------------------------------------------------------------------------------------------
def test_pareto_sort_and_front():
    from neurogenesis.evolution.semi_supervised import crowding_distance, non_dominated_sort, pareto_front
    F = np.array([[1, 5], [2, 4], [3, 3], [1, 1], [2, 2], [0, 0]])
    assert list(non_dominated_sort(F)) == [0, 0, 0, 2, 1, 3]
    assert list(pareto_front(F)) == [0, 1, 2]
    d = crowding_distance(F[:3])
    assert np.isinf(d[0]) and np.isinf(d[2]) and np.isfinite(d[1])


def test_evolve_pareto_spreads_along_a_trade_off():
    from neurogenesis.evolution.semi_supervised import evolve_pareto, pareto_front
    genes = [(("a",), 0.0, 1.0)]

    def evaluate(genomes, seeds):                            # two conflicting objectives of one gene
        a = np.array([g["a"] for g in genomes])
        return np.stack([a, 1 - a ** 2], 1), [{}] * len(genomes)
    P, F, hist = evolve_pareto({"a": 0.5}, genes, evaluate, pop=16, gens=10, sigma=0.2)
    front = F[pareto_front(F)]
    assert len(front) == len(F)                              # every survivor is Pareto optimal here
    assert front[:, 0].max() - front[:, 0].min() > 0.5       # and they cover the trade-off
    P2, _, _ = evolve_pareto({"a": 0.5}, genes, evaluate, pop=16, gens=10, sigma=0.2)
    np.testing.assert_array_equal(P, P2)


def test_inner_fit_evaluator_refits_fit_params_inside_evolution():
    from neurogenesis.evolution.islands import evolve
    from neurogenesis.evolution.semi_supervised import inner_fit_evaluator
    project = _project()
    project["schedule"].append({"name": "kill", "operator": "apoptosis", "params": {"prob": {"path": ["death"], "lo": 0.0, "hi": 0.5}}})
    targets = [{"metric": "cell_count", "value": 250, "scale": 10}]

    def outer(genomes, seeds):                               # prefers little death; fit must compensate with division
        return [-g["death"] for g in genomes], [{} for _ in genomes]
    ev = inner_fit_evaluator(project, targets, outer, fit_seeds=(0,), iterations=4)
    P, hist = evolve({"death": 0.3}, [(("death",), 0.0, 0.5)], ev, pop=4, gens=2, seeds_per_gen=1, elite=1, parents=2)
    info = hist[-1]["best_info"]
    assert "p_div" in info["fit"] and info["fit_loss"] < 10.0          # within ~30 cells after 4 inner iterations
    fixed = inner_fit_evaluator(project, targets, outer, refit=False)
    _, info2 = fixed([{"death": 0.1}], (0,))
    assert info2[0]["fit"] == {}


# E4 ---------------------------------------------------------------------------------------------------------------
def _module(assays=()):
    from neurogenesis.modules import Module
    g = toy_genome()
    return Module(name="toy", plan=sheet_plan(), genome=g, inputs=["sheet"], outputs=["out"],
                  validation={"assays": list(assays)}, version="1.2.0", toolbox=">=0.1, <1.0")


def test_validation_assay_drives_and_gates():
    from neurogenesis.validation import run_assay
    drive = {"name": "drive", "ticks": 60, "seeds": [1000, 1001], "stimuli": [{}, {"sheet": 4000}],
             "readout": {"region": "map", "measure": "rate"}, "metric": "difference", "gate": {"min": 1.0}}
    r = run_assay(_module(), drive)
    assert r["ok"] and all(v > 1.0 for v in r["values"])
    assert run_assay(_module(), drive) == r                  # deterministic
    ko = dict(drive, name="ko", knockout={"projections": [["sheet", "map"]]}, gate={"max": 0.0})
    r_ko = run_assay(_module(), ko)
    assert r_ko["ok"] and r_ko["values"] == [0.0, 0.0]       # without the projection the map no longer responds
    impossible = dict(drive, gate={"min": 1e9})
    assert not run_assay(_module(), impossible)["ok"]


def test_cli_validate_reads_assays_from_the_module(tmp_path):
    good = {"name": "fires", "ticks": 40, "seeds": [1000], "stimuli": [{"sheet": 4000}],
            "readout": {"region": "map", "measure": "fraction_active"}, "gate": {"min": 0.01}}
    _module([good]).save(tmp_path / "m.json")
    env = {**os.environ, "JAX_PLATFORMS": "cpu"}
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "validate", str(tmp_path / "m.json")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "PASS  fires" in r.stdout
    _module([dict(good, gate={"min": 2.0})]).save(tmp_path / "bad.json")
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "validate", str(tmp_path / "bad.json")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 1 and "FAIL" in r.stdout


# G1 ---------------------------------------------------------------------------------------------------------------
def test_version_ranges():
    from neurogenesis.modules.registry import parse_version, satisfies
    assert parse_version("1.2") == (1, 2, 0) and parse_version("1.2.3-rc1") == (1, 2, 3)
    assert satisfies("0.1.0", ">=0.1, <0.2") and not satisfies("0.2.0", ">=0.1, <0.2")
    assert satisfies("3.0.0", "*") and satisfies("1.0.0", "!=0.9") and not satisfies("1.0.0", "==1.0.1")
    with pytest.raises(ValueError):
        satisfies("1.0.0", "~1.0")


def test_install_list_get_and_compatibility(tmp_path):
    from neurogenesis.modules.registry import RegistryError, get, install, list_modules, uninstall
    cat = str(tmp_path / "cat")
    m = _module()
    m.save(tmp_path / "m1.json")
    m.version = "1.3.0"
    m.save(tmp_path / "m2.json")
    install(str(tmp_path / "m1.json"), catalogue=cat)
    install(str(tmp_path / "m2.json"), catalogue=cat)
    assert [e["version"] for e in list_modules(cat)] == ["1.2.0", "1.3.0"]
    assert get("toy", catalogue=cat).version == "1.3.0"
    assert get("toy", "1.2.0", catalogue=cat).version == "1.2.0"
    assert get("toy", catalogue=cat, toolbox_version="0.5.0").version == "1.3.0"
    m.description = "changed"
    m.save(tmp_path / "m2b.json")
    with pytest.raises(RegistryError, match="different content"):
        install(str(tmp_path / "m2b.json"), catalogue=cat)
    install(str(tmp_path / "m2b.json"), catalogue=cat, force=True)
    m.toolbox = ">=9.0"
    m.version = "2.0.0"
    m.save(tmp_path / "m3.json")
    with pytest.raises(RegistryError, match="needs toolbox"):
        install(str(tmp_path / "m3.json"), catalogue=cat)
    uninstall("toy", "1.3.0", catalogue=cat)
    assert get("toy", catalogue=cat).version == "1.2.0"
    with pytest.raises(RegistryError):
        get("missing", catalogue=cat)


def test_cli_install_and_list(tmp_path):
    _module().save(tmp_path / "m.json")
    env = {**os.environ, "NEUROGENESIS_MODULES": str(tmp_path / "cat"), "JAX_PLATFORMS": "cpu"}
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "install", str(tmp_path / "m.json")], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "modules"], capture_output=True, text=True, env=env)
    assert "toy" in r.stdout and "1.2.0" in r.stdout


def test_module_version_fields_round_trip_and_old_files_load():
    from neurogenesis.modules import Module
    m = _module()
    d = m.to_dict()
    assert Module.from_dict(d).version == "1.2.0" and Module.from_dict(d).toolbox == ">=0.1, <1.0"
    del d["version"], d["toolbox"]
    old = Module.from_dict(d)
    assert old.version == "0.1.0" and old.toolbox == "*"
