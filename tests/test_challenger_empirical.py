"""Empirical challenge suite for Track 1: Universal Target & Readout API.

Adversarial stress-testing of target registration, non-spiking assay performance,
JAX isolation, and edge cases (0 cells, disconnected cells, zero/negative scales, missing options).
"""
import copy
import inspect
import json
import time
from unittest.mock import patch

import numpy as np
import pytest

from neurogenesis.data.targets import (
    TARGETS,
    TargetSpec,
    get_target,
    register_target,
    extract_fitting_targets,
    compare_type_statistics,
)
from neurogenesis.fitting import METRICS, target_loss, collect_fits, collect_project_genes
from neurogenesis.genome.genes import set_gene, get_gene, from_unit
from neurogenesis.modules import Module
from neurogenesis.pharmacology import Profile, Receptor, compile_weights, apply_drug
from neurogenesis.project.ui_schema import export_ui_schema
from neurogenesis.tissue import SparseConnectivity, Tissue
from neurogenesis.validation import run_assay
from test_development import sheet_plan, toy_genome


def _create_toy_module(assays=()):
    return Module(
        name="toy",
        plan=sheet_plan(),
        genome=toy_genome(),
        inputs=["sheet"],
        outputs=["out"],
        validation={"assays": list(assays)},
        version="1.2.0",
        toolbox=">=0.1, <1.0"
    )


# ==============================================================================
# 1. Target Registration Signatures & Callable Types
# ==============================================================================

def test_signature_single_tissue_arg():
    """Target function taking only (tissue)."""
    @register_target(name="challenger_single_arg")
    def target_single(tissue: Tissue) -> float:
        return float(len(tissue.alive))

    spec = get_target("challenger_single_arg")
    t = Tissue.empty()
    t.add_cells(5, positions=np.zeros((5, 3)))

    assert spec(t) == 5.0
    assert spec(t, {"dummy": 123}) == 5.0
    assert spec(t, None) == 5.0


def test_signature_two_args_tissue_and_options():
    """Target function taking (tissue, options)."""
    @register_target(name="challenger_two_args")
    def target_double(tissue: Tissue, options: dict) -> float:
        mult = options.get("multiplier", 1.0)
        return float(len(tissue.alive) * mult)

    spec = get_target("challenger_two_args")
    t = Tissue.empty()
    t.add_cells(3, positions=np.zeros((3, 3)))

    assert spec(t) == 3.0  # options defaults to empty dict
    assert spec(t, {"multiplier": 4.0}) == 12.0
    assert spec(t, None) == 3.0


def test_signature_tissue_and_optional_options():
    """Target function taking (tissue, options=None)."""
    @register_target(name="challenger_optional_options")
    def target_optional(tissue: Tissue, options=None) -> float:
        opts = options or {}
        return float(opts.get("bias", 10.0))

    spec = get_target("challenger_optional_options")
    t = Tissue.empty()
    assert spec(t) == 10.0
    assert spec(t, {"bias": 42.0}) == 42.0
    assert spec(t, None) == 10.0


def test_signature_lambda_expressions():
    """Target functions defined via lambdas."""
    l1 = lambda tissue: float(np.sum(tissue.alive))
    register_target(name="challenger_lambda_1")(l1)
    spec1 = get_target("challenger_lambda_1")

    l2 = lambda tissue, options: float(options.get("factor", 2.0))
    register_target(name="challenger_lambda_2")(l2)
    spec2 = get_target("challenger_lambda_2")

    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3)))
    assert spec1(t) == 4.0
    assert spec2(t) == 2.0
    assert spec2(t, {"factor": 5.0}) == 5.0


def test_callable_class_instance():
    """Target registered as a callable class instance."""
    class MultiplierTarget:
        def __init__(self, factor: float):
            self.factor = factor

        def __call__(self, tissue: Tissue, options=None) -> float:
            opts = options or {}
            return float(len(tissue.alive) * self.factor * opts.get("extra", 1.0))

    inst = MultiplierTarget(3.0)
    register_target(name="challenger_callable_obj")(inst)
    spec = get_target("challenger_callable_obj")

    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    assert spec(t) == 6.0
    assert spec(t, {"extra": 2.0}) == 12.0


def test_bare_decorator_without_parentheses():
    """@register_target without parentheses."""
    @register_target
    def challenger_bare_target(tissue: Tissue) -> float:
        """My docstring description."""
        return 123.45

    assert "challenger_bare_target" in TARGETS
    spec = get_target("challenger_bare_target")
    assert spec.name == "challenger_bare_target"
    assert spec.title == "Challenger Bare Target"
    assert "My docstring description" in spec.description
    assert spec.default_scale == 1.0
    assert spec.requires_spiking is False
    assert spec(Tissue.empty()) == 123.45


def test_target_loss_integration_with_new_target():
    """Newly registered target is automatically usable by target_loss."""
    @register_target(name="challenger_loss_target")
    def target_eval(tissue: Tissue, options: dict) -> float:
        return float(len(tissue.alive) * 10)

    t = Tissue.empty()
    t.add_cells(3, positions=np.zeros((3, 3)))
    loss, vals = target_loss(t, [{"target": "challenger_loss_target", "value": 30.0, "scale": 5.0}])
    assert vals == [30.0]
    assert loss == 0.0

    # Test with metric key instead of target key
    loss2, vals2 = target_loss(t, [{"metric": "challenger_loss_target", "value": 35.0, "scale": 5.0}])
    assert vals2 == [30.0]
    assert abs(loss2 - 1.0) < 1e-6  # ((30 - 35) / 5)^2 = 1.0


def test_get_target_unknown_raises_key_error():
    """Querying an unknown target raises KeyError."""
    with pytest.raises(KeyError, match="unknown target"):
        get_target("completely_nonexistent_target_xyz")


# ==============================================================================
# 2. Non-Spiking Assay Performance & JAX Isolation
# ==============================================================================

def test_non_spiking_assay_performance_and_no_jax_simulation():
    """Non-spiking assays must run in sub-second time and strictly NOT invoke simulate_counts."""
    m = _create_toy_module()
    assay = {
        "name": "challenger_fast_assay",
        "target": "cell_count",
        "seeds": [1000, 1001, 1002, 1003],
        "gate": {"min": 10.0, "max": 500.0},
        "pass_fraction": 1.0
    }

    # Patch simulate_counts so if JAX spiking simulation is called, it fails immediately
    with patch("neurogenesis.spiking.batch.simulate_counts", side_effect=AssertionError("simulate_counts MUST NOT BE CALLED")):
        t0 = time.perf_counter()
        res = run_assay(m, assay)
        elapsed = time.perf_counter() - t0

    assert elapsed < 0.5, f"Non-spiking assay exceeded 500ms budget: {elapsed:.3f}s"
    assert res["name"] == "challenger_fast_assay"
    assert len(res["seeds"]) == 4
    assert len(res["values"]) == 4
    assert all(v > 10.0 for v in res["values"])
    assert res["pass_fraction"] == 1.0
    assert res["ok"] is True


def test_non_spiking_assay_targeting_styles():
    """Test resolution of target via assay['target'], readout['target'], and readout['measure']."""
    m = _create_toy_module()

    # 1. assay["target"]
    a1 = {"name": "a1", "target": "modularity", "seeds": [1000]}
    # 2. readout["target"]
    a2 = {"name": "a2", "readout": {"target": "modularity"}, "seeds": [1000]}
    # 3. readout["measure"] matching TARGETS
    a3 = {"name": "a3", "readout": {"measure": "modularity"}, "seeds": [1000]}

    with patch("neurogenesis.spiking.batch.simulate_counts", side_effect=AssertionError("simulate_counts called")):
        r1 = run_assay(m, a1)
        r2 = run_assay(m, a2)
        r3 = run_assay(m, a3)

    assert r1["values"] == r2["values"] == r3["values"]


def test_non_spiking_assay_gate_boundary_conditions():
    """Assay gating logic on edge boundaries."""
    m = _create_toy_module()

    # Read actual cell count for seed 1000
    r_base = run_assay(m, {"name": "base", "target": "cell_count", "seeds": [1000]})
    actual_val = r_base["values"][0]

    # Exact min match passes
    a_pass = {"name": "gate_pass", "target": "cell_count", "seeds": [1000], "gate": {"min": actual_val}}
    res_pass = run_assay(m, a_pass)
    assert res_pass["ok"] is True

    # Exact max match passes
    a_max = {"name": "gate_max", "target": "cell_count", "seeds": [1000], "gate": {"max": actual_val}}
    res_max = run_assay(m, a_max)
    assert res_max["ok"] is True

    # Min above value fails
    a_fail = {"name": "gate_fail", "target": "cell_count", "seeds": [1000], "gate": {"min": actual_val + 1.0}}
    res_fail = run_assay(m, a_fail)
    assert res_fail["ok"] is False
    assert res_fail["pass_fraction"] == 0.0


# ==============================================================================
# 3. Edge Cases: 0 cells, Disconnected cells, Scales, Missing options
# ==============================================================================

def test_zero_cells_tissue_on_all_builtins():
    """All built-in targets must evaluate cleanly on an empty tissue (0 cells)."""
    t_zero = Tissue.empty()

    targets_to_test = [
        "modularity",
        "nearest_neighbour_regularity",
        "within_group_fraction",
        "connection_lengths",
        "pinwheel_density",
        "field_correlation",
        "mean_weight",
        "column_fraction",
        "cell_count",
        "density",
        "layer_thickness",
        "synapse_count",
        "mean_in_degree",
        "connection_probability",
    ]

    for name in targets_to_test:
        spec = get_target(name)
        # Call with minimal options
        val = spec(t_zero, {"volume": 1.0})
        assert isinstance(val, (int, float)), f"{name} failed on zero cells: returned {val}"
        assert not np.isnan(val), f"{name} returned NaN on zero cells"
        assert not np.isinf(val), f"{name} returned Inf on zero cells"


def test_disconnected_cells_tissue():
    """Cells exist, but there are zero synapses (completely disconnected network)."""
    t = Tissue.empty()
    # 20 cells randomly distributed
    rng = np.random.default_rng(42)
    pos = rng.uniform(0.0, 1.0, size=(20, 3))
    t.add_cells(20, positions=pos, cell_type=np.zeros(20, int))

    assert len(t.connectivity.pre) == 0

    # Structural targets on disconnected tissue
    assert get_target("modularity")(t) == 0.0
    assert get_target("within_group_fraction")(t) == 0.0
    assert get_target("connection_lengths")(t) == 0.0
    assert get_target("mean_weight")(t) == 0.0
    assert get_target("column_fraction")(t, {"columns": [[0.5, 0.5]]}) == 0.0
    assert get_target("synapse_count")(t) == 0.0
    assert get_target("mean_in_degree")(t) == 0.0
    assert get_target("connection_probability")(t) == 0.0

    # Regularity on disconnected cells works on spatial positions
    reg = get_target("nearest_neighbour_regularity")(t)
    assert reg > 0.0
    assert not np.isnan(reg)


def test_zero_and_negative_default_scale_handling():
    """Test registration and behaviour with zero and negative default scales."""
    # Register zero scale
    @register_target(name="challenger_zero_scale", default_scale=0.0)
    def target_zero_s(t: Tissue) -> float:
        return 1.0

    spec_zero = get_target("challenger_zero_scale")
    assert spec_zero.default_scale == 0.0

    # Register negative scale
    @register_target(name="challenger_neg_scale", default_scale=-5.0)
    def target_neg_s(t: Tissue) -> float:
        return 2.0

    spec_neg = get_target("challenger_neg_scale")
    assert spec_neg.default_scale == -5.0

    # Verify UI schema export handles zero and negative scales without crashing
    doc = export_ui_schema()
    target_names = [item["name"] for item in doc["targets"]]
    assert "challenger_zero_scale" in target_names
    assert "challenger_neg_scale" in target_names

    zero_doc = next(item for item in doc["targets"] if item["name"] == "challenger_zero_scale")
    assert zero_doc["default_scale"] == 0.0

    neg_doc = next(item for item in doc["targets"] if item["name"] == "challenger_neg_scale")
    assert neg_doc["default_scale"] == -5.0


def test_missing_options_and_none_options():
    """All built-in targets must tolerate options=None and empty options without crashing."""
    t = Tissue.empty()
    t.add_cells(4, positions=np.array([[0,0,0], [0.2,0,0], [0,0.2,0], [0.2,0.2,0]]))
    t.connectivity = SparseConnectivity(
        np.array([0, 1], np.int32),
        np.array([1, 2], np.int32),
        np.array([10, 20], np.int32),
        np.array([1, 1], np.int32)
    )

    targets_to_test = [
        "modularity",
        "nearest_neighbour_regularity",
        "within_group_fraction",
        "connection_lengths",
        "pinwheel_density",
        "field_correlation",
        "mean_weight",
        "column_fraction",
    ]

    for name in targets_to_test:
        spec = get_target(name)
        # 1. options is None
        v_none = spec(t, None)
        assert not np.isnan(v_none)

        # 2. options is {}
        v_empty = spec(t, {})
        assert not np.isnan(v_empty)

        # 3. options with invalid / missing keys
        v_junk = spec(t, {"random_unrecognized_key": 9999})
        assert not np.isnan(v_junk)


# ==============================================================================
# 4. Genes Auto-creation & Pharmacology Stress Testing
# ==============================================================================

def test_genes_deep_path_auto_creation():
    """set_gene auto-creates arbitrary nested dictionary structures."""
    genome = {}
    path = ("deeply", "nested", "hierarchy", "of", "parameters")
    set_gene(genome, path, 3.14159)
    assert genome["deeply"]["nested"]["hierarchy"]["of"]["parameters"] == 3.14159
    assert get_gene(genome, path) == 3.14159


def test_pharmacology_extreme_doses():
    """compile_weights behavior under extreme doses (negative dose, overdose > 1.0)."""
    prof = Profile(
        id="stress_prof",
        transmitters=["GABA"],
        receptors=[
            Receptor(name="GABA_A", transmitter="GABA", sign=-1, gain=1.0)
        ]
    )
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    t.transmitter = np.array([prof.bit("GABA"), 0], np.int8)
    t.connectivity = SparseConnectivity(
        np.array([0], np.int32),
        np.array([1], np.int32),
        np.array([-100], np.int32),
        np.array([1], np.int32),
        receptor_class=np.array([0], np.uint8)
    )

    # 1. Overdose antagonist (dose = 2.5): should clamp to 0, not go negative
    drugs_overdose = {"antagonist": {"receptor": "GABA_A", "dose": 2.5, "effect": "antagonist"}}
    t1 = copy.deepcopy(t)
    compile_weights(t1, prof, drugs=drugs_overdose)
    assert t1.connectivity.weight[0] == 0

    # 2. High dose agonist (dose = 5.0): should scale weight by 1 + 5.0 = 6.0 (-600)
    drugs_agonist = {"agonist": {"receptor": "GABA_A", "dose": 5.0, "effect": "agonist"}}
    t2 = copy.deepcopy(t)
    compile_weights(t2, prof, drugs=drugs_agonist)
    assert t2.connectivity.weight[0] == -600

    # 3. Negative dose antagonist (dose = -0.5): max(0, 1 - (-0.5)) = 1.5 -> -150
    drugs_neg = {"antagonist": {"receptor": "GABA_A", "dose": -0.5, "effect": "antagonist"}}
    t3 = copy.deepcopy(t)
    compile_weights(t3, prof, drugs=drugs_neg)
    assert t3.connectivity.weight[0] == -150
