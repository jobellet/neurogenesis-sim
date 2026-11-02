"""The examples run and do what they claim."""
import subprocess
import sys
from pathlib import Path

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

    # Validate cells per layer (all 3 layers populated)
    cells_per_layer = stats["cells_per_layer"]
    assert len(cells_per_layer) == 3
    assert all(c > 0 for c in cells_per_layer)
    assert stats["total_cells"] == sum(cells_per_layer)

    # Validate layer-to-layer connection matrix
    conn_matrix = stats["connection_matrix"]
    assert len(conn_matrix) == 3 and all(len(row) == 3 for row in conn_matrix)
    assert stats["total_synapses"] > 0
    assert sum(sum(row) for row in conn_matrix) == stats["total_synapses"]

    # Validate delay distribution
    assert stats["delay_min"] >= 1
    assert stats["delay_max"] <= 31
    assert stats["delay_min"] <= stats["delay_mean"] <= stats["delay_max"]

