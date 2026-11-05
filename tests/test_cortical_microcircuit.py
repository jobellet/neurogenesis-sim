"""Tests for the two-phase cortical microcircuit example (Phase M3)."""
import json
from pathlib import Path
import pytest

from examples.cortical_microcircuit import build_scaffold, run_experiment, save_assay_config


def test_cortical_microcircuit_scaffold():
    t = build_scaffold(n_driver=8, n_l4=8, n_l23=16, seed=0)
    assert len(t.alive) == 32
    assert t.connectivity is not None
    assert len(t.connectivity.pre) > 0
    # Contacts field created by cluster_boutons
    assert hasattr(t.connectivity, "contacts")
    assert len(t.connectivity.contacts) == len(t.connectivity.pre)


def test_cortical_microcircuit_acceptance_criteria(tmp_path):
    # Run with small ticks for fast test execution
    results = run_experiment(ticks=60, seed=42)
    p2 = results["post_eye_opening"]

    # Acceptance numbers from prompt and grounding document:
    # 1. Multiplicity regression on residual correlation has a positive, significant slope (P < 0.01)
    assert p2["multiplicity_slope"] > 0.0
    assert p2["p_value"] < 0.01

    # 2. Orientation selectivity gOSI > 0.25 maintained after pruning
    assert p2["gOSI"] > 0.25

    # 3. Surround suppression present
    assert p2["surround_suppression"] > 0.0

    # 4. Assay config JSON generation and validation harness compatibility
    assay_file = tmp_path / "assay.json"
    spec = save_assay_config(assay_file)
    assert assay_file.exists()
    loaded = json.loads(assay_file.read_text(encoding="utf-8"))
    assert loaded["name"] == spec["name"]
    assert "readout" in loaded and "stimuli" in loaded and "gate" in loaded
