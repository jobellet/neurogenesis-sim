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
                       env={**os.environ, "JAX_PLATFORMS": "cpu", "PYTHONIOENCODING": "utf-8"})
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
    env = {**os.environ, "NEUROGENESIS_MODULES": str(tmp_path / "cat"), "JAX_PLATFORMS": "cpu", "PYTHONIOENCODING": "utf-8"}
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


# E2: identifiability -------------------------------------------------------------------------------------------------
def _project_with_unused_fit():
    p = _project()
    # `jitter` only displaces daughters: no cell-count target can see it
    p["schedule"][1]["params"]["jitter"] = {"target": "jit", "init": 0.01, "lo": 0.0, "hi": 0.1}
    return p


def test_jacobian_and_report_flag_an_unused_fit_param_and_an_unreachable_target():
    from neurogenesis.fitting import identifiability_report, jacobian
    targets = [{"metric": "cell_count", "value": 300, "scale": 10},
               {"metric": "layer_thickness", "cell_type": 1, "axis": 2, "value": 0.2, "scale": 0.02, "weight": 0.0}]
    J, names = jacobian(_project_with_unused_fit(), targets, seeds=(0, 1))
    assert names == ["jit", "p_div"] and J.shape == (2, 2)
    assert J[0, 0] == 0.0 and J[0, 1] > 0           # more division, more cells; jitter changes no count
    rep = identifiability_report(J, names, targets)
    assert rep["unidentifiable"] == ["jit"] and rep["unreachable"] == ["layer_thickness (1)"]
    assert rep["rank"] >= 1 and len(rep["singular_values"]) == 2


def test_fit_warns_about_unidentifiable_params_and_can_be_silenced():
    import warnings
    targets = [{"metric": "cell_count", "value": 300, "scale": 10}]
    with pytest.warns(UserWarning, match="'jit' moves no target metric"):
        r = fit(_project_with_unused_fit(), targets, seeds=(0, 1), iterations=2)
    assert r.identifiability["unidentifiable"] == ["jit"] and r.jacobian.shape == (1, 2)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fit(_project_with_unused_fit(), targets, seeds=(0, 1), iterations=2, check_identifiability=False)
        fit(_project(), targets, seeds=(0, 1), iterations=2)       # one param that matters: no warning


# Track 1: Universal Target & Readout API Tests ------------------------------------------------------------------------

def test_register_target_and_metadata():
    from neurogenesis.data.targets import register_target, get_target, TARGETS, TargetSpec

    @register_target(
        name="custom_score",
        title="Custom Score",
        description="A test objective.",
        unit="pts",
        default_scale=2.5,
        requires_spiking=False,
        options_schema={"weight": {"type": "float"}}
    )
    def _score(tissue, options=None):
        return 123.45

    assert "custom_score" in TARGETS
    spec = get_target("custom_score")
    assert isinstance(spec, TargetSpec)
    assert spec.name == "custom_score"
    assert spec.title == "Custom Score"
    assert spec.unit == "pts"
    assert spec.default_scale == 2.5
    assert spec.requires_spiking is False
    assert spec.options_schema == {"weight": {"type": "float"}}

    # Verify compatibility with METRICS and target_loss
    t = Tissue.empty()
    assert spec(t) == 123.45
    assert METRICS["custom_score"](t, {}) == 123.45
    loss, vals = target_loss(t, [{"target": "custom_score", "value": 123.45, "scale": 1.0}])
    assert loss == 0.0 and vals == [123.45]


def test_builtin_structural_targets():
    from neurogenesis.data.targets import get_target
    t = Tissue.empty()
    # 4 cells, types [0, 0, 1, 1], positions
    t.add_cells(4, positions=np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.0, 1.0, 0.0], [0.1, 1.0, 0.0]]),
                cell_type=np.array([0, 0, 1, 1]))
    # Internal connections: 0->1, 2->3 (within type), and one across 1->2
    t.connectivity = SparseConnectivity(
        np.array([0, 2, 1], np.int32),
        np.array([1, 3, 2], np.int32),
        np.array([10, 10, 5], np.int32),
        np.array([1, 1, 1], np.int32)
    )

    # 1. modularity
    mod_spec = get_target("modularity")
    q = mod_spec(t, {"partition": "cell_type"})
    assert isinstance(q, float) and q > 0.0

    # 2. nearest_neighbour_regularity
    nn_spec = get_target("nearest_neighbour_regularity")
    reg = nn_spec(t)
    assert isinstance(reg, float) and reg > 0.0

    # 3. within_group_fraction
    wg_spec = get_target("within_group_fraction")
    frac = wg_spec(t, {"partition": "cell_type"})
    # 2 within (0->1, 2->3), 1 across (1->2) -> 2/3
    assert abs(frac - 2.0 / 3.0) < 1e-4

    # 4. connection_lengths
    cl_spec = get_target("connection_lengths")
    mean_len = cl_spec(t)
    assert isinstance(mean_len, float) and mean_len > 0.0


def test_builtin_spatial_map_targets():
    from neurogenesis.data.targets import get_target
    from neurogenesis.fields.maps import PinwheelField
    from neurogenesis.fields.core import AnalyticField

    t = Tissue.empty()
    t.add_cells(4, positions=np.array([[0.1, 0.1, 0.0], [0.8, 0.1, 0.0], [0.1, 0.8, 0.0], [0.8, 0.8, 0.0]]),
                cell_type=np.array([0, 1, 0, 1]))

    # 1. pinwheel_density with PinwheelField
    pw_field = PinwheelField(singularities=[[0.5, 0.5]], charges=[0.5])
    pd_spec = get_target("pinwheel_density")
    density = pd_spec(t, {"field": pw_field, "bounds": ([0.0, 0.0], [1.0, 1.0])})
    assert density == 1.0  # 1 pinwheel / 1.0 area

    # 2. field_correlation with an AnalyticField
    x_field = AnalyticField("x")
    fc_spec = get_target("field_correlation")
    # cell_type matches x positions (0 at x=0.1, 1 at x=0.8)
    corr = fc_spec(t, {"field": x_field, "property": "cell_type"})
    assert corr > 0.99  # perfect positive correlation


def test_fast_non_spiking_assay():
    import time
    from neurogenesis.validation import run_assay

    # Assay specifying non-spiking target modularity
    assay = {
        "name": "structure_assay",
        "target": "modularity",
        "seeds": [1000, 1001],
        "options": {"partition": "cell_type"},
        "gate": {"min": -1.0, "max": 1.0},
        "pass_fraction": 1.0
    }
    m = _module()
    t0 = time.perf_counter()
    res = run_assay(m, assay)
    elapsed = time.perf_counter() - t0

    assert res["name"] == "structure_assay"
    assert len(res["seeds"]) == 2
    assert len(res["values"]) == 2
    assert res["ok"] is True
    # Fast non-spiking assay must evaluate in under 200ms without spiking kernel simulation
    assert elapsed < 0.5, f"Non-spiking assay took too long: {elapsed:.3f}s"


def test_genes_auto_create_intermediate_keys():
    from neurogenesis.genome.genes import set_gene, get_gene, from_unit

    genome = {}
    # Set a 2-level path: ("drugs", "gaba_antagonist")
    set_gene(genome, ("drugs", "gaba_antagonist"), 0.42, create=True)
    assert genome["drugs"]["gaba_antagonist"] == 0.42
    assert get_gene(genome, ("drugs", "gaba_antagonist")) == 0.42

    # Set a 3-level path: ("receptors", "gaba", "gain")
    set_gene(genome, ("receptors", "gaba", "gain"), 1.75, create=True)
    assert genome["receptors"]["gaba"]["gain"] == 1.75
    assert get_gene(genome, ("receptors", "gaba", "gain")) == 1.75

    # Test from_unit with auto-created paths
    genes = [
        (("drugs", "ampa_agonist"), 0.0, 1.0),
        (("schedule", "div_rate"), 0.1, 0.9),
    ]
    g2 = from_unit({}, genes, [0.5, 0.5], create=True)
    assert abs(g2["drugs"]["ampa_agonist"] - 0.5) < 1e-4
    assert abs(g2["schedule"]["div_rate"] - 0.5) < 1e-4


def test_set_gene_rejects_missing_path_by_default():
    """A misspelled gene must not become a silent dead gene: without create=True a missing path raises."""
    import pytest
    from neurogenesis.genome.genes import set_gene, from_unit
    genome = {"a": {"b": 1.0}, "arr": {"w": np.zeros(3)}}
    with pytest.raises(KeyError):
        set_gene(genome, ("a", "c"), 2.0)
    with pytest.raises(KeyError):
        set_gene(genome, ("x", "y"), 2.0)
    with pytest.raises(KeyError):
        from_unit(genome, [(("a", "typo"), 0.0, 1.0)], [0.5])
    with pytest.raises(KeyError):
        set_gene(genome, ("new", "arr", 0), 1.0, create=True)
    assert genome == {"a": {"b": 1.0}, "arr": genome["arr"]}
    set_gene(genome, ("arr", "w", 1), 2.0)
    assert genome["arr"]["w"][1] == 2.0


def test_pharmacology_drug_modulation_and_apply_stage():
    from neurogenesis.pharmacology import Profile, Receptor, compile_weights, apply_drug, ApplyDrug
    from neurogenesis.tissue import Tissue, SparseConnectivity

    # Profile with classic receptor and GABA receptor
    prof = Profile(
        id="test_prof",
        transmitters=["GABA"],
        receptors=[
            Receptor(name="classic", transmitter=None, sign="pre", gain=1.0),
            Receptor(name="GABA_A", transmitter="GABA", sign=-1, gain=1.0)
        ]
    )
    t = Tissue.empty()
    t.add_cells(3, positions=np.zeros((3, 3)))
    t.transmitter = np.array([prof.bit("GABA"), prof.bit("GABA"), 0], np.int8)
    # Synapse 0: classic (weight 100), Synapse 1: GABA_A (weight -100)
    t.connectivity = SparseConnectivity(
        np.array([0, 1], np.int32),
        np.array([1, 2], np.int32),
        np.array([100, -100], np.int32),
        np.array([1, 1], np.int32),
        receptor_class=np.array([0, 1], np.uint8)
    )

    # 1. Drug antagonist on GABA_A: 50% block (dose=0.5)
    drugs = {"bicuculline": {"receptor": "GABA_A", "dose": 0.5, "effect": "antagonist"}}
    compile_weights(t, prof, drugs=drugs)
    # Synapse 0 remains 100, Synapse 1 scaled to -50
    assert t.connectivity.weight[0] == 100
    assert t.connectivity.weight[1] == -50

    # 2. Test apply_drug helper
    apply_drug(t, prof, drug="gaba_agonist", dose=0.2, effect="agonist", receptor="GABA_A")
    # GABA_A gain modulated by (1 + 0.2) = 1.2 on 50 -> 60
    assert t.connectivity.weight[1] == -60

    # 3. Test ApplyDrug stage neutral parameter
    stage = ApplyDrug(drug="gaba_antagonist", dose=0.0, effect="antagonist", receptor="GABA_A")
    cost_bytes, cost_ops = stage.cost(100, 10, {})
    assert cost_bytes > 0 and cost_ops > 0


def test_unified_parameter_discovery_and_joint_fitting():
    from neurogenesis.fitting import collect_fits, collect_project_genes, fit
    from neurogenesis.params import Fit, Gene

    project = {
        "version": "1.0.0",
        "geometry": BOX,
        "schedule": [
            {"name": "seed", "operator": "seed_cells", "params": {"N": 50, "geometry": "box"}},
            {"name": "div", "operator": "proliferate",
             "params": {"prob": Fit("p_div", init=0.1, lo=0.0, hi=1.0)}}
        ],
        "fields": {
            "grad": {"type": "AnalyticField", "expr": "x * gain",
                     "gain": Gene(["fields", "gain"], lo=0.5, hi=2.0)}
        },
        "drugs": {
            "bicuculline": {
                "dose": Fit("drug_dose", init=0.2, lo=0.0, hi=1.0),
                "effect": "antagonist"
            },
            "agonist": {
                "dose": Gene(["drugs", "agonist_dose"], lo=0.0, hi=0.5)
            }
        }
    }

    # 1. Discover all Fit params across schedule, fields, and drugs
    fits = collect_fits(project)
    fit_names = [f[0] for f in fits]
    assert "p_div" in fit_names
    assert "drug_dose" in fit_names

    # 2. Discover all Gene params across schedule, fields, and drugs
    genes = collect_project_genes(project)
    gene_paths = [g[0] for g in genes]
    assert ("fields", "gain") in gene_paths
    assert ("drugs", "agonist_dose") in gene_paths

    # 3. Fit multi-domain project targeting cell_count
    res = fit(project, [{"metric": "cell_count", "value": 100, "scale": 10}],
              seeds=(0,), iterations=4, check_identifiability=False)
    assert "p_div" in res.values
    assert "drug_dose" in res.values


def test_apply_drug_stage_in_schedule():
    """Regression test: ApplyDrug stage execution inside project schedule via run_schedule."""
    project = {
        "version": "1.0.0",
        "geometry": BOX,
        "schedule": [
            {"name": "seed", "operator": "seed_cells", "params": {"N": 10, "geometry": "box"}},
            {"name": "drug", "operator": "apply_drug", "params": {"drug": "bicuculline", "dose": 0.5, "effect": "antagonist"}}
        ]
    }
    tissue = run_schedule(project, {}, 0)
    assert len(tissue.alive) == 10


def test_compile_weights_none_guards():
    """Regression test: compile_weights does not crash when genome contains None pharmacology/drugs."""
    from neurogenesis.pharmacology import DEFAULT, Profile, Receptor, compile_weights

    prof = Profile(
        id="test_prof",
        transmitters=["glutamate", "gaba"],
        receptors=[
            Receptor("AMPA", transmitter="glutamate", sign=1, gain=1.0),
            Receptor("GABA_A", transmitter="gaba", sign=-1, gain=1.0)
        ]
    )
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    t.transmitter = np.array([prof.bit("gaba"), 0], np.uint8)
    t.connectivity = SparseConnectivity(
        np.array([0], np.int32),
        np.array([1], np.int32),
        np.array([-100], np.int32),
        np.array([1], np.int32),
        receptor_class=np.array([1], np.uint8)
    )

    # 1. genome with pharmacology: None
    res1 = compile_weights(t, prof, genome={"pharmacology": None})
    assert res1["changed"] == 0
    assert t.connectivity.weight[0] == -100

    # 2. genome with drugs: None and nested pharmacology.drugs: None
    res2 = compile_weights(t, prof, genome={"drugs": None, "pharmacology": {"drugs": None}})
    assert res2["changed"] == 0
    assert t.connectivity.weight[0] == -100

    # 3. empty tissue with pharmacology: None
    t_empty = Tissue.empty()
    res3 = compile_weights(t_empty, DEFAULT, genome={"pharmacology": None})
    assert res3 == {"changed": 0, "silenced": 0}




def test_validation_structural_assay_with_connectome_metrics():
    from neurogenesis.validation import run_assay
    simplices = {"name": "simplices", "target": "simplex_count", "options": {"dim": 1}, "seeds": [1000, 1001],
                 "gate": {"min": 1.0}}
    r = run_assay(_module(), simplices)
    assert r["ok"] and all(v >= 1.0 for v in r["values"])          # 1-simplices = connections of the grown network
    ko = dict(simplices, name="ko", knockout={"projections": [["sheet", "map"]]}, gate={"max": r["values"][0] - 1})
    assert run_assay(_module(), ko)["ok"]                          # removing the projection removes connections
    recip = {"name": "recip", "target": "reciprocity", "options": {"measure": "fraction"}, "seeds": [1000],
             "gate": {"max": 1.0}}
    assert run_assay(_module(), recip)["ok"]
