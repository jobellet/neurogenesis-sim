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

    # Validate birth cycle predicts laminar depth (rank correlation >= 0.8)
    assert stats["birth_order_rank_corr"] >= 0.8


def test_layered_sheet_birth_order_predicts_layer_across_seeds(tmp_path):
    """Birth cycle consistently predicts laminar depth (inside-out, Spearman r >= 0.8) across 5 seeds."""
    from neurogenesis.stages.base import run_schedule
    sys.path.insert(0, str(ROOT))
    from examples.layered_sheet import build_project, _spearmanr

    proj = build_project()
    proj_dict = proj.to_dict()

    correlations = []
    for seed in [42, 101, 7, 1234, 999]:
        tissue = run_schedule(proj_dict, genome=proj.genome, seed=seed)
        corr, _ = _spearmanr(tissue.generation, tissue.positions[:, 2])
        correlations.append(corr)
        # Verify both excitatory and inhibitory synapses are formed in every seed
        assert np.sum(tissue.connectivity.weight < 0) > 0
        assert np.sum(tissue.connectivity.weight > 0) > 0

    assert all(c >= 0.8 for c in correlations)
    assert np.mean(correlations) >= 0.85




def _run_example(name, tmp_path, *args):
    import json
    r = subprocess.run([sys.executable, str(ROOT / "examples" / name), "--cpu", "--out", str(tmp_path), *args],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "project.json").exists() and (tmp_path / "network.json").exists()
    return json.loads((tmp_path / "stats.json").read_text())


def test_hand_built_network_example(tmp_path):
    """G2.4: a fully hand-built ring compiles, validates (Dale) and propagates activity in order."""
    stats = _run_example("hand_built_network.py", tmp_path)
    assert stats["neurons"] == 17 and stats["synapses"] > 12
    assert stats["propagates_in_order"]


def test_hand_drawn_column_example(tmp_path):
    """G2.1: cells per layer follow the hand-drawn thicknesses; genes set the inhibitory fraction of each layer."""
    stats = _run_example("hand_drawn_column.py", tmp_path)
    counts = np.asarray(stats["cells_per_layer"], float)
    np.testing.assert_allclose(counts / counts.sum(), [0.3, 0.3, 0.4], atol=0.06)
    f = stats["inhibitory_fraction"]
    assert f[0] < 0.15 and 0.2 < f[1] < 0.6 and f[2] > 0.7               # genes -3, 0, +1.5
    assert stats["genes"] == [["inhibitory_bias", "L0"], ["inhibitory_bias", "L1"], ["inhibitory_bias", "L2"]]


def test_hand_drawn_column_genes_change_fates():
    sys.path.insert(0, str(ROOT))
    from examples.hand_drawn_column import build_project, layer_stats
    from neurogenesis.stages.base import run_schedule
    p = build_project(inh_genes=(3.0, 3.0, -3.0))
    f = layer_stats(run_schedule(p.to_dict(), p.genome, 1))["inhibitory_fraction"]
    assert f[0] > 0.8 and f[1] > 0.8 and f[2] < 0.15


def test_pinwheel_sheet_example(tmp_path):
    """G2.2: density follows the hand-placed pinwheels and the map's pinwheels are recovered."""
    stats = _run_example("pinwheel_sheet.py", tmp_path)
    assert stats["density_ratio"] > 1.5
    assert sorted(stats["pinwheel_charges"]) == [-0.5, -0.5, 0.5, 0.5]
    found = np.asarray(stats["pinwheels_found"])
    centres = np.array([[3.0, 3.0], [7.0, 7.0], [3.0, 7.0], [7.0, 3.0]])
    assert np.all(np.min(np.linalg.norm(found[:, None] - centres[None], axis=-1), axis=0) < 0.2)


def test_evolved_development_example(tmp_path):
    """G2.3: a fully genetic schedule (genes collected automatically) improves under island evolution."""
    stats = _run_example("evolved_development.py", tmp_path)
    assert stats["final_best"] > stats["first_best"] + 0.3
    assert ["div"] in stats["genes"] and ["p0"] in stats["genes"] and ["div2"] in stats["genes"]
    assert stats["cells_type1"] > 0 and stats["synapses"] > 0
