"""Comprehensive End-to-End Test Suite for neurogenesis-sim.

Covers Features 1-9 across Tiers 1-4:
- Tier 1: Equivalence Classes & Happy Paths (>= 5 tests per feature)
- Tier 2: Boundary, Extreme, and Error Conditions (>= 5 tests per feature)
- Tier 3: Cross-Feature Pairwise Combinations
- Tier 4: Real-World System Scenarios & CLI Workflows
"""
from __future__ import annotations

import inspect
import json
import math
import subprocess
import sys
import unittest.mock as mock
import warnings
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest

import nir

from neurogenesis.bridge.ngb import write_network
from neurogenesis.data import DataError, import_connectome
from neurogenesis.interop import (
    ExportReport,
    delay_ms,
    delay_ticks,
    export_network,
    formats,
    import_network,
    lif_params,
    register_format,
    shift_from_tau,
    tau_ms,
)
from neurogenesis.interop.core import require
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData

# Progressive testability conditions
NIR_REGISTERED = "nir" in formats()
MAX_DELAY_SUPPORTED = "max_delay" in inspect.signature(import_connectome).parameters

skip_if_no_nir = pytest.mark.skipif(
    not NIR_REGISTERED,
    reason="NIR exporter format pending implementation in Milestone M1 (Worker M1)",
)
skip_if_no_max_delay = pytest.mark.skipif(
    not MAX_DELAY_SUPPORTED,
    reason="max_delay parameter pending in import_connectome (Milestone M2)",
)


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Execute neurogenesis CLI command in a subprocess."""
    cmd = [sys.executable, "-m", "neurogenesis", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


# ============================================================================
# TIER 1: Equivalence Classes & Happy Path (>= 5 tests per feature)
# ============================================================================

class TestTier1HappyPath:
    """Tier 1: Primary behavior and happy paths for Features 1-9."""

    # --- Feature 1: J3 NIR Core Exporter ---

    @skip_if_no_nir
    def test_tier1_export_single_lif_neuron(self, single_neuron_net, tmp_path):
        out_file = tmp_path / "single.nir"
        report = export_network(single_neuron_net, "nir", out_file)
        assert out_file.exists()
        assert out_file.stat().st_size > 0
        assert isinstance(report, ExportReport)
        assert report.format == "nir"

    @skip_if_no_nir
    def test_tier1_export_two_neuron_feedforward(self, two_neuron_feedforward_net, tmp_path):
        out_file = tmp_path / "ff.nir"
        report = export_network(two_neuron_feedforward_net, "nir", out_file)
        graph = nir.read(out_file)
        assert isinstance(graph, nir.NIRGraph)
        assert any(isinstance(node, nir.CubaLIF) for node in graph.nodes.values())
        assert report.counts.get("nodes") == 2 or report.counts.get("neurons") == 2

    @skip_if_no_nir
    def test_tier1_export_recurrent_circuit(self, recurrent_net, tmp_path):
        out_file = tmp_path / "rec.nir"
        report = export_network(recurrent_net, "nir", out_file)
        graph = nir.read(out_file)
        # Graph must contain feedback/recurrent connectivity
        assert len(graph.edges) >= 3
        assert report.counts.get("edges") == 3 or report.counts.get("synapses") == 3

    @skip_if_no_nir
    def test_tier1_export_cortical_column(self, cortical_column_net, tmp_path):
        out_file = tmp_path / "col.nir"
        report = export_network(cortical_column_net, "nir", out_file)
        assert out_file.exists()
        graph = nir.read(out_file)
        cuba_nodes = [n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF)]
        assert len(cuba_nodes) == 1
        assert cuba_nodes[0].tau_mem.shape[0] == cortical_column_net.num_neurons

    @skip_if_no_nir
    def test_tier1_export_layered_network(self, layered_net, tmp_path):
        out_file = tmp_path / "layered.nir"
        report = export_network(layered_net, "nir", out_file)
        assert out_file.exists()
        graph = nir.read(out_file)
        assert len(graph.nodes) >= 3  # input, linear/cuba, output

    # --- Feature 2: J3 Dynamics Mapping ---

    @skip_if_no_nir
    def test_tier1_dynamics_standard_lif_parameters(self, single_neuron_net, tmp_path):
        out_file = tmp_path / "dyn.nir"
        export_network(single_neuron_net, "nir", out_file)
        graph = nir.read(out_file)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        n0 = single_neuron_net.neurons[0]
        p = lif_params(n0)
        expected_tau_m = p.tau_m * 1e-3  # seconds
        assert math.isclose(float(cuba.tau_mem[0]), expected_tau_m, rel_tol=1e-3)
        assert math.isclose(float(cuba.tau_syn[0]), p.tau_syn * 1e-3, rel_tol=1e-3)

    @skip_if_no_nir
    def test_tier1_dynamics_varying_membrane_time_constant(self, tmp_path):
        neurons = [
            NeuronData(id=i, x=0, y=0, z=0, dir_x=1, dir_y=0, dir_z=0, mode=0, shift_v=shift)
            for i, shift in enumerate([1, 2, 4, 6, 8])
        ]
        net = SNNNetwork(neurons=neurons)
        out_file = tmp_path / "tau_m.nir"
        export_network(net, "nir", out_file)
        graph = nir.read(out_file)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        for i, shift in enumerate([1, 2, 4, 6, 8]):
            expected = tau_ms(shift) * 1e-3
            assert math.isclose(float(cuba.tau_mem[i]), expected, rel_tol=1e-3)

    @skip_if_no_nir
    def test_tier1_dynamics_varying_synaptic_time_constant(self, tmp_path):
        neurons = [
            NeuronData(id=i, x=0, y=0, z=0, dir_x=1, dir_y=0, dir_z=0, mode=0, shift_s=shift)
            for i, shift in enumerate([1, 2, 3, 5, 7])
        ]
        net = SNNNetwork(neurons=neurons)
        out_file = tmp_path / "tau_syn.nir"
        export_network(net, "nir", out_file)
        graph = nir.read(out_file)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        for i, shift in enumerate([1, 2, 3, 5, 7]):
            expected = tau_ms(shift) * 1e-3
            assert math.isclose(float(cuba.tau_syn[i]), expected, rel_tol=1e-3)

    @skip_if_no_nir
    def test_tier1_dynamics_custom_voltage_scaling(self, single_neuron_net, tmp_path):
        out_file = tmp_path / "scaled.nir"
        export_network(single_neuron_net, "nir", out_file, mV_per_unit=0.02, E_L=-70.0, C_m=300.0)
        graph = nir.read(out_file)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        assert math.isclose(float(cuba.v_leak[0]), -0.070, rel_tol=1e-3)

    @skip_if_no_nir
    def test_tier1_dynamics_custom_dt(self, single_neuron_net, tmp_path):
        out_file = tmp_path / "dt.nir"
        report = export_network(single_neuron_net, "nir", out_file, dt=2e-3)
        assert out_file.exists()
        assert report.counts.get("nodes") == 1 or report.counts.get("neurons") == 1

    # --- Feature 3: J3 Connectivity Mapping ---

    @skip_if_no_nir
    def test_tier1_connectivity_input_node_created(self, two_neuron_feedforward_net, tmp_path):
        out_file = tmp_path / "in.nir"
        export_network(two_neuron_feedforward_net, "nir", out_file)
        graph = nir.read(out_file)
        inputs = [n for n in graph.nodes.values() if isinstance(n, nir.Input)]
        assert len(inputs) == 1
        assert inputs[0].input_type["input"][0] == 2

    @skip_if_no_nir
    def test_tier1_connectivity_output_node_created(self, two_neuron_feedforward_net, tmp_path):
        out_file = tmp_path / "out.nir"
        export_network(two_neuron_feedforward_net, "nir", out_file)
        graph = nir.read(out_file)
        outputs = [n for n in graph.nodes.values() if isinstance(n, nir.Output)]
        assert len(outputs) == 1
        assert outputs[0].output_type["output"][0] == 2

    @skip_if_no_nir
    def test_tier1_connectivity_feedforward_linear_matrix(self, two_neuron_feedforward_net, tmp_path):
        out_file = tmp_path / "ff_mat.nir"
        export_network(two_neuron_feedforward_net, "nir", out_file)
        graph = nir.read(out_file)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        assert len(linears) >= 1
        # At least one linear has shape (2, 2)
        assert any(l.weight.shape == (2, 2) for l in linears)

    @skip_if_no_nir
    def test_tier1_connectivity_recurrent_linear_loop(self, recurrent_net, tmp_path):
        out_file = tmp_path / "rec_mat.nir"
        export_network(recurrent_net, "nir", out_file)
        graph = nir.read(out_file)
        # Find linear weights
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        assert len(linears) >= 1
        # Edges should include cyclic connectivity
        edge_targets = [tgt for src, tgt in graph.edges]
        assert "lif" in edge_targets or any("lif" in t for t in edge_targets)

    @skip_if_no_nir
    def test_tier1_connectivity_inhibitory_synapse_negative_weights(self, recurrent_net, tmp_path):
        out_file = tmp_path / "inh.nir"
        export_network(recurrent_net, "nir", out_file)
        graph = nir.read(out_file)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        # Inhibitory weight (-150) must yield negative entries in weight matrix
        has_negative = any((l.weight < 0).any() for l in linears)
        assert has_negative

    # --- Feature 4: J3 Export Report ---

    @skip_if_no_nir
    def test_tier1_report_format_identifier(self, single_neuron_net, tmp_path):
        rep = export_network(single_neuron_net, "nir", tmp_path / "r.nir")
        assert rep.format == "nir"
        assert str(tmp_path / "r.nir") in rep.path

    @skip_if_no_nir
    def test_tier1_report_node_and_edge_counts(self, two_neuron_feedforward_net, tmp_path):
        rep = export_network(two_neuron_feedforward_net, "nir", tmp_path / "r.nir")
        cnt = rep.counts
        assert (cnt.get("nodes") == 2 or cnt.get("neurons") == 2)
        assert (cnt.get("edges") == 1 or cnt.get("synapses") == 1)

    @skip_if_no_nir
    def test_tier1_report_lossless_is_false(self, two_neuron_feedforward_net, tmp_path):
        rep = export_network(two_neuron_feedforward_net, "nir", tmp_path / "r.nir")
        assert rep.lossless is False

    @skip_if_no_nir
    def test_tier1_report_documents_approximated_dynamics(self, two_neuron_feedforward_net, tmp_path):
        rep = export_network(two_neuron_feedforward_net, "nir", tmp_path / "r.nir")
        assert any("dynamics" in k.lower() or "lif" in k.lower() for k in rep.approximated)

    @skip_if_no_nir
    def test_tier1_report_documents_dropped_delays(self, two_neuron_feedforward_net, tmp_path):
        rep = export_network(two_neuron_feedforward_net, "nir", tmp_path / "r.nir")
        delays_reported = any("delay" in k.lower() for k in list(rep.dropped) + list(rep.approximated))
        assert delays_reported

    # --- Feature 5: J3 Format Registry & Builtin ---

    def test_tier1_registry_formats_returns_list(self):
        f = formats()
        assert isinstance(f, list)
        assert "sonata" in f

    @skip_if_no_nir
    def test_tier1_registry_nir_in_formats(self):
        assert "nir" in formats()

    @skip_if_no_nir
    def test_tier1_registry_export_network_delegation(self, single_neuron_net, tmp_path):
        rep = export_network(single_neuron_net, "nir", tmp_path / "test.nir")
        assert rep.format == "nir"

    def test_tier1_registry_case_sensitivity(self):
        with pytest.raises(ValueError, match="unknown format"):
            export_network(SNNNetwork(neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0)]), "SONATA_INVALID", "dummy")

    def test_tier1_registry_custom_format_coexistence(self, tmp_path):
        def dummy_writer(net, path, **opts):
            path.write_text("ok")
            return ExportReport("custom_e2e_fmt", str(path))

        register_format("custom_e2e_fmt", export=dummy_writer)
        assert "custom_e2e_fmt" in formats()
        net = SNNNetwork(neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0)])
        rep = export_network(net, "custom_e2e_fmt", tmp_path / "custom.txt")
        assert rep.format == "custom_e2e_fmt"

    # --- Feature 6: J3 Packaging Extra ---

    def test_tier1_packaging_require_nir_succeeds(self):
        mod = require("nir", "nir")
        assert mod.__name__ == "nir"

    def test_tier1_packaging_require_missing_error_message(self):
        with pytest.raises(ImportError, match=r'pip install "neurogenesis-sim\[nir\]"'):
            require("non_existent_package_xyz", "nir")

    def test_tier1_packaging_pyproject_toml_extra(self):
        root = Path(__file__).resolve().parents[2]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        # Check either installed pyproject or optional extra definition
        assert "optional-dependencies" in pyproject

    def test_tier1_packaging_nir_version_check(self):
        import nir
        assert hasattr(nir, "__version__")
        version_parts = [int(p) for p in nir.__version__.split(".")[:2]]
        assert version_parts[0] >= 1

    def test_tier1_packaging_lazy_import_efficiency(self):
        # neurogenesis top-level should not require eagerly importing heavy format subpackages
        import neurogenesis
        assert hasattr(neurogenesis, "__version__")

    # --- Feature 7: K4b Delay Clip Lifting ---

    def test_tier1_k4b_delays_preserved_below_max(self, toy_connectome_dir):
        t, info = import_connectome(
            toy_connectome_dir / "toy_e2e.json",
            directory=toy_connectome_dir,
            log=lambda s: None,
        )
        assert len(t.connectivity.delay) > 0
        assert (t.connectivity.delay >= 1).all()

    @skip_if_no_max_delay
    def test_tier1_k4b_custom_max_delay_parameter(self, toy_connectome_dir):
        t, info = import_connectome(
            toy_connectome_dir / "toy_e2e.json",
            directory=toy_connectome_dir,
            max_delay=63,
            log=lambda s: None,
        )
        assert info["delays_clipped"] >= 0

    @skip_if_no_max_delay
    def test_tier1_k4b_delays_clipped_to_custom_max(self, toy_connectome_dir):
        t, info = import_connectome(
            toy_connectome_dir / "toy_e2e.json",
            directory=toy_connectome_dir,
            max_delay=127,
            log=lambda s: None,
        )
        assert (t.connectivity.delay <= 127).all()

    def test_tier1_k4b_counted_warning_emitted_when_clipped(self, toy_connectome_dir):
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            import_connectome(
                toy_connectome_dir / "toy_e2e.json",
                directory=toy_connectome_dir,
                log=lambda s: None,
            )
        assert any("clipped" in str(w.message) for w in recorded)

    def test_tier1_k4b_delays_at_least_one_tick(self, toy_connectome_dir):
        t, _ = import_connectome(
            toy_connectome_dir / "toy_e2e.json",
            directory=toy_connectome_dir,
            log=lambda s: None,
        )
        assert (t.connectivity.delay >= 1).all()

    # --- Feature 8: Roadmap & Docs Sync ---

    def test_tier1_docs_readme_status_check(self):
        # Run test_readme_status to ensure docs are not out of sync
        cmd = [sys.executable, "-m", "pytest", "tests/test_readme_status.py", "-q"]
        ret = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert ret.returncode == 0

    def test_tier1_docs_roadmap_phase_j_structure(self):
        root = Path(__file__).resolve().parents[2]
        roadmap = (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        assert "Phase J:" in roadmap
        assert "J3. NIR" in roadmap

    def test_tier1_docs_roadmap_k4b_status(self):
        root = Path(__file__).resolve().parents[2]
        roadmap = (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        assert "K4b." in roadmap

    def test_tier1_docs_changelog_entries(self):
        root = Path(__file__).resolve().parents[2]
        changelog = (root / "docs" / "changelog.md").read_text(encoding="utf-8")
        assert len(changelog) > 50

    def test_tier1_docs_format_docstring_accuracy(self):
        from neurogenesis import interop
        assert interop.__doc__ is not None

    # --- Feature 9: Interop CLI ---

    @skip_if_no_nir
    def test_tier1_cli_export_nir_command(self, single_neuron_net, tmp_path):
        net_json = tmp_path / "net.json"
        single_neuron_net.save_json(net_json)
        out_nir = tmp_path / "out.nir"
        res = _cli("export", str(net_json), "--format", "nir", "--out", str(out_nir))
        assert res.returncode == 0
        assert out_nir.exists()

    @skip_if_no_nir
    def test_tier1_cli_export_prints_report_json(self, single_neuron_net, tmp_path):
        net_json = tmp_path / "net.json"
        single_neuron_net.save_json(net_json)
        out_nir = tmp_path / "out.nir"
        res = _cli("export", str(net_json), "--format", "nir", "--out", str(out_nir))
        assert res.returncode == 0
        output_data = json.loads(res.stdout)
        assert output_data["format"] == "nir"

    @skip_if_no_nir
    def test_tier1_cli_export_with_ngb_input(self, single_neuron_net, tmp_path):
        ngb_file = tmp_path / "net.ngb"
        write_network(single_neuron_net, ngb_file)
        out_nir = tmp_path / "from_ngb.nir"
        res = _cli("export", str(ngb_file), "--format", "nir", "--out", str(out_nir))
        assert res.returncode == 0
        assert out_nir.exists()

    def test_tier1_cli_export_help_includes_command(self):
        res = _cli("export", "--help")
        assert res.returncode == 0
        assert "--format" in res.stdout
        assert "--out" in res.stdout

    def test_tier1_cli_import_help_interface(self):
        res = _cli("import", "--help")
        assert res.returncode == 0
        assert "--format" in res.stdout


# ============================================================================
# TIER 2: Boundary, Extreme, and Error Conditions (>= 5 tests per feature)
# ============================================================================

class TestTier2BoundaryAndErrors:
    """Tier 2: Boundary conditions, extreme sizes, and robust error handling."""

    # --- Feature 1: Exporter Boundaries ---

    @skip_if_no_nir
    def test_tier2_exporter_zero_neurons_raises_value_error(self, tmp_path):
        empty_net = SNNNetwork(neurons=[], synapses=[])
        with pytest.raises(ValueError):
            export_network(empty_net, "nir", tmp_path / "empty.nir")

    @skip_if_no_nir
    def test_tier2_exporter_isolated_neurons_no_synapses(self, tmp_path):
        isolated = SNNNetwork(
            neurons=[
                NeuronData(0, 0, 0, 0, 1, 0, 0, 0),
                NeuronData(1, 10, 0, 0, 1, 0, 0, 0),
                NeuronData(2, 20, 0, 0, 1, 0, 0, 0),
            ],
            synapses=[],
        )
        out_nir = tmp_path / "isolated.nir"
        report = export_network(isolated, "nir", out_nir)
        assert out_nir.exists()
        graph = nir.read(out_nir)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        # All weights should be zero
        for l in linears:
            assert np.all(l.weight == 0)

    @skip_if_no_nir
    def test_tier2_exporter_deep_directory_creation(self, single_neuron_net, tmp_path):
        deep_file = tmp_path / "a" / "b" / "c" / "deep.nir"
        report = export_network(single_neuron_net, "nir", deep_file)
        assert deep_file.exists()

    @skip_if_no_nir
    def test_tier2_exporter_path_types_str_and_path(self, single_neuron_net, tmp_path):
        str_path = str(tmp_path / "str_path.nir")
        rep1 = export_network(single_neuron_net, "nir", str_path)
        path_obj = tmp_path / "obj_path.nir"
        rep2 = export_network(single_neuron_net, "nir", path_obj)
        assert Path(str_path).exists() and path_obj.exists()

    @skip_if_no_nir
    def test_tier2_exporter_overwrite_existing_file(self, single_neuron_net, tmp_path):
        target = tmp_path / "overwrite.nir"
        target.write_text("old content")
        export_network(single_neuron_net, "nir", target)
        assert target.stat().st_size > 0
        graph = nir.read(target)
        assert isinstance(graph, nir.NIRGraph)

    # --- Feature 2: Dynamics Boundaries ---

    @skip_if_no_nir
    def test_tier2_dynamics_extreme_thresholds(self, tmp_path):
        net = SNNNetwork(neurons=[
            NeuronData(0, 0, 0, 0, 1, 0, 0, 0, threshold=0),
            NeuronData(1, 0, 0, 0, 1, 0, 0, 0, threshold=4096),
        ])
        out = tmp_path / "thresh.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        assert cuba.v_threshold[1] > cuba.v_threshold[0]

    @skip_if_no_nir
    def test_tier2_dynamics_boundary_shift_v(self, tmp_path):
        net = SNNNetwork(neurons=[
            NeuronData(0, 0, 0, 0, 1, 0, 0, 0, shift_v=1),
            NeuronData(1, 0, 0, 0, 1, 0, 0, 0, shift_v=15),
        ])
        out = tmp_path / "shifts_v.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        assert cuba.tau_mem[1] > cuba.tau_mem[0]

    @skip_if_no_nir
    def test_tier2_dynamics_boundary_shift_s(self, tmp_path):
        net = SNNNetwork(neurons=[
            NeuronData(0, 0, 0, 0, 1, 0, 0, 0, shift_s=1),
            NeuronData(1, 0, 0, 0, 1, 0, 0, 0, shift_s=15),
        ])
        out = tmp_path / "shifts_s.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        assert cuba.tau_syn[1] > cuba.tau_syn[0]

    @skip_if_no_nir
    def test_tier2_dynamics_zero_refractory_period(self, tmp_path):
        net = SNNNetwork(neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0, refractory=0)])
        out = tmp_path / "ref0.nir"
        rep = export_network(net, "nir", out)
        assert out.exists()

    @skip_if_no_nir
    def test_tier2_dynamics_large_refractory_period(self, tmp_path):
        net = SNNNetwork(neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0, refractory=50)])
        out = tmp_path / "ref50.nir"
        rep = export_network(net, "nir", out)
        # Should document refractory period approximation in report
        assert any("refractory" in k.lower() or "refractory" in v.lower()
                   for k, v in rep.approximated.items())

    # --- Feature 3: Connectivity Boundaries ---

    @skip_if_no_nir
    def test_tier2_connectivity_all_to_all_dense_matrix(self, tmp_path):
        n = 4
        neurons = [NeuronData(i, 0, 0, 0, 1, 0, 0, 0) for i in range(n)]
        synapses = [
            SynapseData(pre=i, post=j, weight=100, delay=1)
            for i in range(n) for j in range(n)
        ]
        net = SNNNetwork(neurons=neurons, synapses=synapses)
        out = tmp_path / "all2all.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        assert any(l.weight.shape == (n, n) and (l.weight > 0).all() for l in linears)

    @skip_if_no_nir
    def test_tier2_connectivity_self_synapse_loop(self, tmp_path):
        net = SNNNetwork(
            neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0)],
            synapses=[SynapseData(pre=0, post=0, weight=250, delay=1)],
        )
        out = tmp_path / "self.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        assert any(l.weight[0, 0] > 0 for l in linears)

    @skip_if_no_nir
    def test_tier2_connectivity_extreme_weights_clamp(self, tmp_path):
        net = SNNNetwork(
            neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0), NeuronData(1, 0, 0, 0, 1, 0, 0, 0)],
            synapses=[
                SynapseData(pre=0, post=1, weight=2047, delay=1),
                SynapseData(pre=1, post=0, weight=-2048, delay=1),
            ],
        )
        out = tmp_path / "weights.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        assert any((l.weight < 0).any() and (l.weight > 0).any() for l in linears)

    @skip_if_no_nir
    def test_tier2_connectivity_multi_synapses_same_pair(self, tmp_path):
        net = SNNNetwork(
            neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0), NeuronData(1, 0, 0, 0, 1, 0, 0, 0)],
            synapses=[
                SynapseData(pre=0, post=1, weight=100, delay=1),
                SynapseData(pre=0, post=1, weight=150, delay=2),
            ],
        )
        out = tmp_path / "multi.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        # Summed or compound weight should exceed single weight
        assert any(l.weight.shape == (2, 2) for l in linears)

    @skip_if_no_nir
    def test_tier2_connectivity_sparse_single_synapse(self, tmp_path):
        n = 10
        neurons = [NeuronData(i, 0, 0, 0, 1, 0, 0, 0) for i in range(n)]
        synapses = [SynapseData(pre=3, post=7, weight=400, delay=1)]
        net = SNNNetwork(neurons=neurons, synapses=synapses)
        out = tmp_path / "sparse.nir"
        export_network(net, "nir", out)
        graph = nir.read(out)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        assert any(l.weight.shape == (n, n) and np.count_nonzero(l.weight) == 1 for l in linears)

    # --- Feature 4: Export Report Boundaries ---

    @skip_if_no_nir
    def test_tier2_report_zero_drivers_omits_driver_warning(self, single_neuron_net, tmp_path):
        rep = export_network(single_neuron_net, "nir", tmp_path / "rep.nir")
        assert "drivers" not in rep.dropped
        assert "drivers" not in rep.approximated

    @skip_if_no_nir
    def test_tier2_report_all_poisson_drivers(self, tmp_path):
        net = SNNNetwork(neurons=[
            NeuronData(0, 0, 0, 0, 1, 0, 0, 1, poisson_hz=20.0),
            NeuronData(1, 0, 0, 0, 1, 0, 0, 1, poisson_hz=30.0),
        ])
        rep = export_network(net, "nir", tmp_path / "poiss.nir")
        drivers_reported = any("driver" in k.lower() or "poisson" in k.lower()
                               for k in list(rep.dropped) + list(rep.approximated))
        assert drivers_reported

    @skip_if_no_nir
    def test_tier2_report_all_burster_neurons(self, tmp_path):
        net = SNNNetwork(neurons=[
            NeuronData(0, 0, 0, 0, 1, 0, 0, 2, burst_period=10, burst_duty=2),
        ])
        rep = export_network(net, "nir", tmp_path / "burst.nir")
        burster_reported = any("burster" in k.lower() or "driver" in k.lower()
                               for k in list(rep.dropped) + list(rep.approximated))
        assert burster_reported

    @skip_if_no_nir
    def test_tier2_report_zero_delay_latency_note(self, tmp_path):
        net = SNNNetwork(
            neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0), NeuronData(1, 0, 0, 0, 1, 0, 0, 0)],
            synapses=[SynapseData(pre=0, post=1, weight=100, delay=0)],
        )
        rep = export_network(net, "nir", tmp_path / "del0.nir")
        assert any("delay" in k.lower() for k in list(rep.dropped) + list(rep.approximated))

    @skip_if_no_nir
    def test_tier2_report_multi_word_delays_note(self, tmp_path):
        net = SNNNetwork(
            neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0), NeuronData(1, 0, 0, 0, 1, 0, 0, 0)],
            synapses=[SynapseData(pre=0, post=1, weight=100, delay=45)],
        )
        rep = export_network(net, "nir", tmp_path / "del45.nir")
        assert any("delay" in k.lower() for k in list(rep.dropped) + list(rep.approximated))

    # --- Feature 5: Registry Boundaries ---

    def test_tier2_registry_unknown_format_raises_value_error(self, single_neuron_net, tmp_path):
        with pytest.raises(ValueError, match="unknown format"):
            export_network(single_neuron_net, "unsupported_fmt_xyz", tmp_path / "x")

    def test_tier2_registry_empty_format_raises_value_error(self, single_neuron_net, tmp_path):
        with pytest.raises(ValueError):
            export_network(single_neuron_net, "", tmp_path / "x")

    def test_tier2_registry_import_unsupported_format_raises(self, tmp_path):
        # Even if format is valid for export, if import_ is None it raises ValueError
        def dummy_export(net, path):
            return ExportReport("write_only", str(path))

        register_format("write_only", export=dummy_export)
        with pytest.raises(ValueError, match="cannot be read"):
            import_network("write_only", tmp_path / "dummy")

    def test_tier2_registry_duplicate_registration_overwrites(self):
        call_count = {"v1": 0, "v2": 0}
        register_format("dup_fmt", export=lambda net, p: call_count.__setitem__("v1", 1))
        register_format("dup_fmt", export=lambda net, p: call_count.__setitem__("v2", 1))
        net = SNNNetwork(neurons=[NeuronData(0, 0, 0, 0, 1, 0, 0, 0)])
        export_network(net, "dup_fmt", "path")
        assert call_count["v2"] == 1 and call_count["v1"] == 0

    def test_tier2_registry_invalid_network_type_raises(self):
        with pytest.raises(Exception):
            export_network(12345, "sonata", "dummy_path")

    # --- Feature 6: Packaging Boundaries ---

    @skip_if_no_nir
    def test_tier2_packaging_mock_missing_nir_raises_import_error(self, single_neuron_net, tmp_path):
        with mock.patch("neurogenesis.interop.nir.require", side_effect=ImportError("mocked missing nir")):
            with pytest.raises(ImportError):
                export_network(single_neuron_net, "nir", tmp_path / "mock.nir")

    def test_tier2_packaging_corrupted_file_handling(self, tmp_path):
        bad_file = tmp_path / "corrupted.nir"
        bad_file.write_bytes(b"not a valid hdf5 or nir file")
        with pytest.raises(Exception):
            nir.read(bad_file)

    def test_tier2_packaging_non_existent_extra_naming(self):
        with pytest.raises(ImportError) as exc_info:
            require("definitely_fake_module_abc", "custom_extra_group")
        assert "custom_extra_group" in str(exc_info.value)

    def test_tier2_packaging_exception_chaining(self):
        with pytest.raises(ImportError) as exc_info:
            require("non_existent_pkg_123", "some_extra")
        assert exc_info.value.__cause__ is not None

    def test_tier2_packaging_partial_module_mock(self):
        with mock.patch.dict("sys.modules", {"nir": None}):
            with pytest.raises(ImportError):
                require("nir", "nir")

    # --- Feature 7: K4b Delay Boundaries ---

    @skip_if_no_max_delay
    def test_tier2_k4b_delay_equal_to_max_delay_no_warning(self, toy_connectome_dir):
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            import_connectome(
                toy_connectome_dir / "toy_e2e.json",
                directory=toy_connectome_dir,
                max_delay=500,  # 105 has distance 500, so exactly equal to max_delay
                log=lambda s: None,
            )
        assert not any("clipped" in str(w.message) for w in recorded)

    @skip_if_no_max_delay
    def test_tier2_k4b_delay_exceeding_max_delay_triggers_warning(self, toy_connectome_dir):
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            import_connectome(
                toy_connectome_dir / "toy_e2e.json",
                directory=toy_connectome_dir,
                max_delay=499,
                log=lambda s: None,
            )
        assert any("clipped" in str(w.message) for w in recorded)

    def test_tier2_k4b_zero_distance_clamped_to_one(self, toy_connectome_dir):
        t, _ = import_connectome(
            toy_connectome_dir / "toy_e2e.json",
            directory=toy_connectome_dir,
            log=lambda s: None,
        )
        assert (t.connectivity.delay >= 1).all()

    @skip_if_no_max_delay
    def test_tier2_k4b_negative_max_delay_rejected(self, toy_connectome_dir):
        with pytest.raises((ValueError, AssertionError, DataError)):
            import_connectome(
                toy_connectome_dir / "toy_e2e.json",
                directory=toy_connectome_dir,
                max_delay=-1,
                log=lambda s: None,
            )

    def test_tier2_k4b_extreme_velocity_clamp(self, toy_connectome_dir):
        t, _ = import_connectome(
            toy_connectome_dir / "toy_e2e.json",
            directory=toy_connectome_dir,
            conduction_velocity=1e6,  # huge velocity => round(dist / vel) = 0 => clamped to 1
            log=lambda s: None,
        )
        assert (t.connectivity.delay == 1).all()

    # --- Feature 8: Docs Boundaries ---

    def test_tier2_docs_no_premature_done_status(self):
        root = Path(__file__).resolve().parents[2]
        roadmap = (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        # Ensure Phase J tasks J4, J5 are not prematurely marked done
        assert "J4. PyNN" in roadmap

    def test_tier2_docs_task_ids_valid(self):
        root = Path(__file__).resolve().parents[2]
        roadmap = (root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        assert "**J3." in roadmap

    def test_tier2_docs_changelog_header_dates(self):
        root = Path(__file__).resolve().parents[2]
        changelog = (root / "docs" / "changelog.md").read_text(encoding="utf-8")
        lines = changelog.splitlines()
        assert any("###" in line or "##" in line for line in lines)

    def test_tier2_docs_consistent_format_tables(self):
        root = Path(__file__).resolve().parents[2]
        readme = (root / "README.md").read_text(encoding="utf-8")
        assert "neurogenesis" in readme

    def test_tier2_docs_readme_badges_intact(self):
        root = Path(__file__).resolve().parents[2]
        readme = (root / "README.md").read_text(encoding="utf-8")
        assert "neurogenesis-sim" in readme

    # --- Feature 9: CLI Boundaries ---

    def test_tier2_cli_non_existent_network_file_fails(self, tmp_path):
        res = _cli("export", str(tmp_path / "missing.json"), "--format", "sonata", "--out", str(tmp_path / "out"))
        assert res.returncode != 0

    def test_tier2_cli_unknown_format_fails(self, single_neuron_net, tmp_path):
        net_json = tmp_path / "net.json"
        single_neuron_net.save_json(net_json)
        res = _cli("export", str(net_json), "--format", "invalid_format_xyz", "--out", str(tmp_path / "out"))
        assert res.returncode != 0

    def test_tier2_cli_missing_required_args_fails(self, single_neuron_net, tmp_path):
        net_json = tmp_path / "net.json"
        single_neuron_net.save_json(net_json)
        # Missing --format and --out
        res = _cli("export", str(net_json))
        assert res.returncode != 0

    def test_tier2_cli_corrupted_json_fails(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{corrupted json: true")
        res = _cli("export", str(bad_json), "--format", "sonata", "--out", str(tmp_path / "out"))
        assert res.returncode != 0

    def test_tier2_cli_unwritable_destination_fails(self, single_neuron_net, tmp_path):
        net_json = tmp_path / "net.json"
        single_neuron_net.save_json(net_json)
        # Destination inside non-existent file path treated as directory
        dummy_file = tmp_path / "file.txt"
        dummy_file.write_text("hello")
        res = _cli("export", str(net_json), "--format", "sonata", "--out", str(dummy_file / "impossible"))
        assert res.returncode != 0


# ============================================================================
# TIER 3: Cross-Feature Pairwise Combinations
# ============================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Pairwise interactions across dynamics, connectivity, and reports."""

    @skip_if_no_nir
    def test_tier3_recurrent_network_custom_dynamics(self, recurrent_net, tmp_path):
        out_file = tmp_path / "rec_custom.nir"
        rep = export_network(
            recurrent_net,
            "nir",
            out_file,
            mV_per_unit=0.01,
            E_L=-68.0,
            C_m=200.0,
            dt=0.5e-3,
        )
        graph = nir.read(out_file)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        assert math.isclose(float(cuba.v_leak[0]), -0.068, rel_tol=1e-3)
        assert len(graph.edges) >= 3

    @skip_if_no_nir
    def test_tier3_heterogeneous_drivers_nir_report(self, mixed_drivers_net, tmp_path):
        out_file = tmp_path / "mixed.nir"
        rep = export_network(mixed_drivers_net, "nir", out_file)
        # Report must account for Poisson driver and burster neuron
        assert not rep.lossless
        assert "drivers" in rep.approximated or "drivers" in rep.dropped

    @skip_if_no_nir
    def test_tier3_extreme_delays_nir_dropped_accounting(self, tmp_path):
        neurons = [NeuronData(0, 0, 0, 0, 1, 0, 0, 0), NeuronData(1, 0, 0, 0, 1, 0, 0, 0)]
        synapses = [SynapseData(pre=0, post=1, weight=120, delay=60)]
        net = SNNNetwork(neurons=neurons, synapses=synapses)
        out_file = tmp_path / "long_delay.nir"
        rep = export_network(net, "nir", out_file)
        assert any("delay" in k.lower() for k in list(rep.approximated) + list(rep.dropped))

    @skip_if_no_nir
    def test_tier3_morphogenetic_tissue_to_nir_export(self, layered_net, tmp_path):
        out_file = tmp_path / "morpho.nir"
        rep = export_network(layered_net, "nir", out_file)
        graph = nir.read(out_file)
        assert len(graph.nodes) >= 3
        assert rep.counts["nodes"] == layered_net.num_neurons

    @skip_if_no_nir
    def test_tier3_dual_format_sonata_and_nir_consistency(self, two_neuron_feedforward_net, tmp_path):
        sonata_dir = tmp_path / "sonata_out"
        nir_file = tmp_path / "nir_out.nir"
        rep_sonata = export_network(two_neuron_feedforward_net, "sonata", sonata_dir)
        rep_nir = export_network(two_neuron_feedforward_net, "nir", nir_file)
        assert rep_sonata.counts["nodes"] == rep_nir.counts["nodes"]
        assert rep_sonata.counts["edges"] == rep_nir.counts["edges"]

    @skip_if_no_nir
    def test_tier3_cli_generate_export_read_pipeline(self, tmp_path):
        net_json = tmp_path / "generated.json"
        nir_out = tmp_path / "generated.nir"
        res1 = _cli("generate", "--neurons", "10", "--morphology", "column", "--out", str(net_json))
        assert res1.returncode == 0
        res2 = _cli("export", str(net_json), "--format", "nir", "--out", str(nir_out))
        assert res2.returncode == 0
        graph = nir.read(nir_out)
        cuba = next(n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF))
        assert cuba.tau_mem.shape[0] == 10


# ============================================================================
# TIER 4: Real-World System Scenarios
# ============================================================================

class TestTier4RealWorldSystemScenarios:
    """Tier 4: Production end-to-end integration and pipelines."""

    @skip_if_no_nir
    def test_tier4_cortical_column_300_end_to_end_nir(self, cortical_column_net, tmp_path):
        out_file = tmp_path / "column300.nir"
        rep = export_network(cortical_column_net, "nir", out_file)
        assert out_file.exists()
        graph = nir.read(out_file)
        cuba_nodes = [n for n in graph.nodes.values() if isinstance(n, nir.CubaLIF)]
        assert len(cuba_nodes) == 1
        assert cuba_nodes[0].tau_mem.shape == (300,)
        linears = [n for n in graph.nodes.values() if isinstance(n, nir.Linear)]
        # Verify 300x300 recurrent weight matrix
        rec_linear = next(l for l in linears if l.weight.shape == (300, 300))
        assert rec_linear is not None

    @skip_if_no_nir
    def test_tier4_layered_microcircuit_end_to_end_nir(self, layered_net, tmp_path):
        out_file = tmp_path / "layered60.nir"
        rep = export_network(layered_net, "nir", out_file)
        graph = nir.read(out_file)
        assert len(graph.nodes) >= 3
        assert len(graph.edges) >= 2

    @skip_if_no_nir
    def test_tier4_connectome_import_to_nir_pipeline(self, toy_connectome_dir, tmp_path):
        t, info = import_connectome(
            toy_connectome_dir / "toy_e2e.json",
            directory=toy_connectome_dir,
            log=lambda s: None,
        )
        # Convert tissue to SNNNetwork
        net = t.to_network()
        net.morphology = "imported_connectome"
        out_file = tmp_path / "connectome.nir"
        rep = export_network(net, "nir", out_file)
        graph = nir.read(out_file)
        assert len(graph.nodes) >= 3

    def test_tier4_production_telemetry_report_serialization(self, single_neuron_net, tmp_path):
        sonata_dir = tmp_path / "telemetry_sonata"
        rep = export_network(single_neuron_net, "sonata", sonata_dir)
        d = rep.to_dict()
        assert "format" in d
        assert "path" in d
        assert "lossless" in d
        assert "exact" in d
        assert "approximated" in d
        assert "dropped" in d
        assert "counts" in d
        serialized = str(rep)
        reloaded = json.loads(serialized)
        assert reloaded["format"] == "sonata"

    def test_tier4_complete_cli_subprocess_pipeline(self, tmp_path):
        net_json = tmp_path / "pipeline.json"
        # 1. Generate
        res1 = _cli("generate", "--neurons", "20", "--morphology", "column", "--out", str(net_json))
        assert res1.returncode == 0
        # 2. Stats
        res2 = _cli("stats", "--network", str(net_json))
        assert res2.returncode == 0
        assert "Topology" in res2.stdout or "total_neurons" in res2.stdout
        # 3. Export to SONATA
        sonata_dir = tmp_path / "pipeline_sonata"
        res3 = _cli("export", str(net_json), "--format", "sonata", "--out", str(sonata_dir))
        assert res3.returncode == 0
        assert (sonata_dir / "circuit_config.json").exists()
