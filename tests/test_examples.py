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
