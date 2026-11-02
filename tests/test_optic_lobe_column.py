import pytest
import numpy as np
import os
import subprocess
import sys
from pathlib import Path
import re

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.fitting import target_loss
from neurogenesis.data.targets import extract_fitting_targets, compare_type_statistics

def test_extract_fitting_targets_and_metrics():
    t = Tissue.empty()
    t.add_cells(5, positions=np.array([[0,0,0], [1,0,0], [0,1,0], [1,1,0], [0,0,0]]), cell_type=np.array([0, 0, 1, 1, 2]))
    t.connectivity = SparseConnectivity(
        np.array([0, 1, 4], np.int32), 
        np.array([2, 3, 3], np.int32), 
        np.array([10, 10, -5], np.int32), 
        np.array([1, 1, 1], np.int32)
    )
    
    targets = extract_fitting_targets(t)
    
    assert any(tg["metric"] == "cell_count" and tg["cell_type"] == 0 and tg["value"] == 2 for tg in targets)
    assert any(tg["metric"] == "cell_count" and tg["cell_type"] == 1 and tg["value"] == 2 for tg in targets)
    
    assert any(tg["metric"] == "synapse_count" and tg["pre_cell_type"] == 0 and tg["post_cell_type"] == 1 and tg["value"] == 2 for tg in targets)
    assert any(tg["metric"] == "mean_in_degree" and tg["pre_cell_type"] == 0 and tg["post_cell_type"] == 1 and tg["value"] == 1.0 for tg in targets)
    
    loss, vals = target_loss(t, [{"metric": "mean_weight", "pre_cell_type": 0, "post_cell_type": 1, "value": 10.0}])
    assert vals[0] == 10.0 and loss == 0.0
    
    loss, vals = target_loss(t, [{"metric": "mean_weight", "pre_cell_type": 2, "post_cell_type": 1, "value": -5.0}])
    assert vals[0] == -5.0 and loss == 0.0
    
    columns = np.array([[0,0,0], [1,1,0]])
    targets = extract_fitting_targets(t, columns=columns)
    cf_0_1 = next(tg for tg in targets if tg["metric"] == "column_fraction" and tg["pre_cell_type"] == 0 and tg["post_cell_type"] == 1)
    loss, vals = target_loss(t, [cf_0_1])
    assert cf_0_1["value"] == 0.5

def test_compare_type_statistics():
    t1 = Tissue.empty()
    t1.add_cells(2, positions=np.zeros((2,3)), cell_type=np.array([0, 1]))
    t1.connectivity = SparseConnectivity(np.array([0], np.int32), np.array([1], np.int32), np.array([1], np.int32), np.array([1], np.int32))
    
    t2 = Tissue.empty()
    t2.add_cells(2, positions=np.zeros((2,3)), cell_type=np.array([0, 1]))
    t2.connectivity = SparseConnectivity(np.array([0], np.int32), np.array([1], np.int32), np.array([1], np.int32), np.array([1], np.int32))
    
    stats = compare_type_statistics(t1, t2)
    assert stats["count_l1_rel_error"] == 0.0
    assert stats["matrix_cosine_similarity"] == 1.0
    assert stats["degree_mean_rel_error"] == 0.0

def test_example_optic_lobe_column(tmp_path):
    env = {**os.environ, "JAX_PLATFORMS": "cpu"}
    r = subprocess.run([sys.executable, "examples/optic_lobe_column.py", "--dir", str(tmp_path)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "Simulation complete. Success." in r.stdout
    
    match = re.search(r"Cosine Similarity:\s*([0-9.]+)", r.stdout)
    assert match, "Could not find Cosine Similarity in output"
    sim = float(match.group(1))
    assert sim >= 0.85, f"Cosine similarity too low: {sim} < 0.85"
