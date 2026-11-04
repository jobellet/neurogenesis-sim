"""Parameter profiles: every value has a status and a source, and profiles can extend each other."""
import copy
import glob
import json
import os

import pytest

from neurogenesis import cli
from neurogenesis.profiles import (check_profile, find_profile, load_parameter_profile, provenance_counts)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = sorted(glob.glob(os.path.join(ROOT, "examples", "profiles", "*.json")))

GOOD = {
    "id": "toy",
    "description": "toy",
    "rate": 2.5,
    "table": [1.0, 2.0, 3.0],
    "provenance": {
        "rate": {"status": "measured", "quantity": "a rate", "source": ["doi:10.1000/xyz123"], "evidence": "abstract"},
        "table": {"status": "free", "quantity": "a virtual table", "note": "no biological counterpart", "bounds": [0, 5]},
    },
}


def _with(**changes):
    d = copy.deepcopy(GOOD)
    for k, v in changes.items():
        d[k] = v
    return d


def _write(tmp_path, name, d):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps(d))
    return p


@pytest.mark.parametrize("path", PROFILES, ids=[os.path.basename(p) for p in PROFILES])
def test_shipped_profiles_declare_provenance(path):
    assert check_profile(path) == []


def test_good_profile_and_counts():
    assert check_profile(GOOD) == []
    assert provenance_counts([GOOD]) == {"measured": 1, "derived": 0, "assumed": 0, "free": 1}


def test_a_parameter_without_provenance_is_refused():
    d = _with()
    d["extra"] = 7
    assert any("'extra'" in e and "no provenance" in e for e in check_profile(d))
    assert any("provenance" in e for e in check_profile({"id": "x", "rate": 1}))


@pytest.mark.parametrize("entry, fragment", [
    ({"status": "guess", "quantity": "q"}, "status"),
    ({"status": "measured", "quantity": "q", "evidence": "abstract"}, "source"),
    ({"status": "measured", "quantity": "q", "source": ["doi:10.1000/a"]}, "evidence"),
    ({"status": "measured", "quantity": "q", "source": ["Smith 2001"], "evidence": "abstract"}, "doi:"),
    ({"status": "derived", "quantity": "q"}, "method"),
    ({"status": "assumed", "quantity": "q"}, "note"),
    ({"status": "free", "quantity": "q", "note": "n", "bounds": [3, 1]}, "bounds"),
    ({"status": "free", "note": "n"}, "quantity"),
])
def test_bad_entries_are_refused(entry, fragment):
    d = _with()
    d["provenance"]["rate"] = entry
    assert any(fragment in e for e in check_profile(d)), check_profile(d)


def test_dangling_entry_and_element_coverage():
    d = _with()
    d["provenance"]["nothing"] = {"status": "free", "quantity": "q", "note": "n"}
    assert any("no such key" in e for e in check_profile(d))
    d = _with()
    d["provenance"]["table[7]"] = {"status": "free", "quantity": "q", "note": "n"}
    assert any("no such key" in e for e in check_profile(d))
    # a list is covered by entries for each element, and a glob covers matching keys
    d = _with(table=[1.0, 2.0])
    del d["provenance"]["table"]
    d["provenance"]["table[0]"] = {"status": "free", "quantity": "q", "note": "n"}
    assert any("'table'" in e for e in check_profile(d))
    d["provenance"]["table[1]"] = {"status": "assumed", "quantity": "q", "note": "n"}
    assert check_profile(d) == []
    d = _with(reference_a=1, reference_b=2)
    d["provenance"]["reference_*"] = {"status": "derived", "quantity": "q", "method": "computed"}
    assert check_profile(d) == []


def test_extends_merges_and_requires_own_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("NEUROGENESIS_PROFILES", str(tmp_path))
    _write(tmp_path, "base", _with(id="base_mouse"))
    child = {"id": "child_rat", "extends": "base_mouse", "rate": 4.0,
             "provenance": {"rate": {"status": "measured", "quantity": "a rate in rat", "species": "rat",
                                     "source": ["doi:10.1000/rat1"], "evidence": "full_text"}}}
    p = _write(tmp_path, "child", child)
    merged = load_parameter_profile("child_rat")
    assert merged["rate"] == 4.0 and merged["table"] == [1.0, 2.0, 3.0]
    assert merged["provenance"]["rate"]["species"] == "rat" and "table" in merged["provenance"]
    assert check_profile(p) == []
    # overriding a value while keeping the parent's provenance would describe the wrong species
    bad = {"id": "child_bad", "extends": "base_mouse", "rate": 9.0}
    errs = check_profile(_write(tmp_path, "bad", bad))
    assert any("'rate'" in e and "own" in e for e in errs)
    assert find_profile("child_rat") == p


def test_extends_cycle_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("NEUROGENESIS_PROFILES", str(tmp_path))
    _write(tmp_path, "a", {"id": "a", "extends": "b"})
    _write(tmp_path, "b", {"id": "b", "extends": "a"})
    assert any("cycle" in e for e in check_profile("a"))


def test_cli_check_exit_status(tmp_path, capsys, monkeypatch):
    good = _write(tmp_path, "good", GOOD)
    bad = _write(tmp_path, "bad", {"id": "bad", "rate": 1})
    monkeypatch.setattr("sys.argv", ["neurogenesis", "profile", "check", str(good)])
    cli.main()
    assert "ok" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["neurogenesis", "profile", "check", str(bad)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    monkeypatch.setattr("sys.argv", ["neurogenesis", "profile", "show", str(good)])
    cli.main()
    assert "measured" in capsys.readouterr().out
