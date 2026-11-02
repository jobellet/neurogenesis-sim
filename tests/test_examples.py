"""The examples run and do what they claim."""
import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def test_topographic_map_example(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "topographic_map.py"), "--cpu", "--out", str(tmp_path)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.startswith("stimulus")]
    u0, u1 = (float(l.rsplit(" ", 1)[1]) for l in lines)
    assert u0 < 0.3 and u1 > 0.7                                           # the map is topographic
    assert (tmp_path / "network.json").exists() and (tmp_path / "module.json").exists()


def test_layered_sheet_example(tmp_path):
    import json
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "layered_sheet.py"), "--cpu", "--out", str(tmp_path)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "project.json").exists()
    assert (tmp_path / "network.json").exists()
    assert (tmp_path / "stats.json").exists()

    with open(tmp_path / "stats.json", "r", encoding="utf-8") as f:
        stats = json.load(f)

    # Validate cell types (excitatory across layers + superficial inhibitory interneurons)
    cells_per_type = stats["cells_per_type"]
    assert len(cells_per_type) == 4
    assert all(c > 0 for c in cells_per_type)
    assert stats["total_cells"] == sum(cells_per_type)

    # Validate both excitatory and inhibitory synapses exist
    assert stats["inhibitory_synapses"] > 0
    assert stats["excitatory_synapses"] > 0
    assert stats["inhibitory_synapses"] + stats["excitatory_synapses"] == stats["total_synapses"]

    # Validate layer-to-layer connection matrix
    conn_matrix = stats["connection_matrix"]
    assert len(conn_matrix) == 4 and all(len(row) == 4 for row in conn_matrix)
    assert stats["total_synapses"] > 0
    assert sum(sum(row) for row in conn_matrix) == stats["total_synapses"]

    # Validate delay distribution
    assert stats["delay_min"] >= 1
    assert stats["delay_max"] <= 31
    assert stats["delay_min"] <= stats["delay_mean"] <= stats["delay_max"]

    # Validate birth order predicts laminar depth (rank correlation > 0.7)
    assert stats["birth_order_rank_corr"] > 0.7


def test_layered_sheet_birth_order_predicts_layer_across_seeds(tmp_path):
    """Birth order consistently predicts laminar depth (inside-out) across 5 seeds."""
    from scipy.stats import spearmanr
    from neurogenesis.stages.base import run_schedule
    sys.path.insert(0, str(ROOT))
    from examples.layered_sheet import build_project

    proj = build_project()
    proj_dict = proj.to_dict()

    correlations = []
    for seed in [42, 101, 7, 1234, 999]:
        tissue = run_schedule(proj_dict, genome=proj.genome, seed=seed)
        corr, _ = spearmanr(tissue.birth_stage, tissue.positions[:, 2])
        correlations.append(corr)
        # Verify both excitatory and inhibitory synapses are formed in every seed
        assert np.sum(tissue.connectivity.weight < 0) > 0
        assert np.sum(tissue.connectivity.weight > 0) > 0

    assert all(c > 0.7 for c in correlations)
    assert np.mean(correlations) > 0.75


