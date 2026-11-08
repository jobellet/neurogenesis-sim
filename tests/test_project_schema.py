"""Tests for Project schema validation and I/O."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from neurogenesis.project.io import Project
from neurogenesis.project import schema


def test_round_trip():
    """Test saving and loading a Project with nested NumPy arrays."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_project.json"
        
        # Create some arrays
        arr1 = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        arr2 = np.array([[1, 2], [3, 4]], dtype=np.int32)
        
        p = Project(
            geometry={"type": "box", "bounds": arr1},
            fields={"gradients": [arr2, "some_string"]},
            schedule=[{"stage": "proliferate", "params": {"rate": 0.5}}],
            genome={"genes": {"a": 1, "b": arr1}},
            metadata={"description": "test project"}
        )
        
        p.save(path)
        
        # Verify files exist
        assert path.exists()
        assert Path(str(path.with_suffix('')) + ".npz").exists()
        
        # Load and compare
        p_loaded = Project.load(path)
        
        assert p_loaded.version == p.version
        assert p_loaded.neuron_model == p.neuron_model
        assert p_loaded.metadata == p.metadata
        assert p_loaded.schedule == p.schedule
        
        np.testing.assert_array_equal(p_loaded.geometry["bounds"], arr1)
        assert p_loaded.geometry["bounds"].dtype == np.float32
        
        np.testing.assert_array_equal(p_loaded.fields["gradients"][0], arr2)
        assert p_loaded.fields["gradients"][0].dtype == np.int32
        assert p_loaded.fields["gradients"][1] == "some_string"
        
        np.testing.assert_array_equal(p_loaded.genome["genes"]["b"], arr1)


def test_schema_rejection():
    """Test that the schema rejects malformed files with clear ValueError messages."""
    # Not a dict
    with pytest.raises(ValueError, match="Project data must be a dictionary"):
        schema.validate(["not", "a", "dict"])
        
    # Missing version
    with pytest.raises(ValueError, match="Project data must contain a 'version' key"):
        schema.validate({"geometry": {}})
        
    # Wrong version type
    with pytest.raises(ValueError, match="'version' must be a string"):
        schema.validate({"version": 1.0, "geometry": {}})
        
    # Missing required field
    valid_data = {
        "version": "1.0.0",
        "geometry": {},
        "fields": {},
        "schedule": [],
        "genome": {},
        "plugins": [],
        "metadata": {}
    }
    
    for field in ["geometry", "schedule", "genome"]:
        data = valid_data.copy()
        del data[field]
        with pytest.raises(ValueError, match=f"Project missing required field: '{field}'"):
            schema.validate(data)
            
    # Wrong field type
    data = valid_data.copy()
    data["schedule"] = {}
    with pytest.raises(ValueError, match="Project field 'schedule' must be of type list"):
        schema.validate(data)


def test_migration():
    """Test migration from legacy 0.1.0 BodyPlan format to 1.0.0 Project."""
    legacy_plan = {
        "name": "toy",
        "regions": [{"name": "sheet"}],
        "projections": [],
        "plugins": ["my_plugin"]
    }
    
    # 0.1.0 didn't have a version field typically, but load adds or defaults it in migration context
    data_to_migrate = legacy_plan.copy()
    
    migrated = schema.migrate(data_to_migrate, "0.1.0", "1.0.0")
    
    # Verify the structure matches 1.0.0
    schema.validate(migrated)
    assert migrated["version"] == "1.0.0"
    assert migrated["plan"] == legacy_plan
    assert migrated["plugins"] == ["my_plugin"]
    assert migrated["neuron_model"] == "lif_int"
    assert migrated["schedule"] == []
    assert migrated["genome"] == {}
    
    # Test loading a legacy format via Project.load by writing a dummy legacy file
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "legacy.json"
        
        legacy_data = legacy_plan.copy()
        legacy_data["version"] = "0.1.0"
        
        with open(path, 'w') as f:
            json.dump(legacy_data, f)
            
        p = Project.load(path)
        assert p.version == schema.SCHEMA_VERSION
        assert p.plan["name"] == "toy"
        assert p.plugins == ["my_plugin"]


def test_migration_100_to_110_keeps_the_project_and_its_development(tmp_path):
    """K1: a 1.0.0 project loads as 1.1.0, unchanged apart from the version, and grows the same tissue."""
    from neurogenesis.stages.base import run_schedule
    import numpy as np
    old = {"version": "1.0.0", "geometry": {"box": {"type": "Box", "center": [0, 0, 0], "size": [1, 1, 1]}},
           "fields": {}, "schedule": [{"name": "s", "operator": "seed_cells", "params": {"N": 20, "geometry": "box"}},
                                      {"name": "d", "operator": "proliferate", "params": {"prob": 0.5}}],
           "genome": {}, "plugins": [], "metadata": {"a": 1}, "neuron_model": "lif_int"}
    (tmp_path / "old.json").write_text(json.dumps(old))
    p = Project.load(tmp_path / "old.json")
    assert p.version == "1.2.0" and p.data_sources is None and p.pharmacology is None and p.morphology is None
    d = p.to_dict()
    assert {k: v for k, v in d.items() if k != "version"} == {k: v for k, v in old.items() if k != "version"}
    a, b = run_schedule(old, {}, 3), run_schedule(d, {}, 3)
    assert np.array_equal(a.positions, b.positions)
    # Single-step and chained migrations
    m110 = schema.migrate(old, "1.0.0", "1.1.0")
    assert m110["version"] == "1.1.0"
    m120 = schema.migrate(m110, "1.1.0", "1.2.0")
    assert m120["version"] == "1.2.0"
    chained = schema.migrate({"name": "toy", "regions": [], "projections": []}, "0.1.0", "1.1.0")
    assert chained["version"] == "1.1.0" and chained["plan"]["name"] == "toy"
    chained120 = schema.migrate({"name": "toy", "regions": [], "projections": []}, "0.1.0", "1.2.0")
    assert chained120["version"] == "1.2.0" and chained120["plan"]["name"] == "toy"


def test_schema_110_sections_round_trip_and_validation(tmp_path):
    p = Project(data_sources={"fly": {"dataset": "toy_connectome", "filters": {"cell_type": ["A"]}}},
                pharmacology={"profile": "default"}, morphology={"compartments": 3})
    p.save(tmp_path / "p.json")
    q = Project.load(tmp_path / "p.json")
    assert q.data_sources == p.data_sources and q.pharmacology == p.pharmacology and q.morphology == p.morphology
    bad = p.to_dict()
    bad["pharmacology"] = [1]
    with pytest.raises(ValueError, match="pharmacology"):
        schema.validate(bad)
    bad = p.to_dict()
    bad["data_sources"] = {"x": {"files": []}}
    with pytest.raises(ValueError, match="dataset"):
        schema.validate(bad)


def test_schema_120_sections_and_migration(tmp_path):
    """Test 1.2.0 optional sections (targets, compute_cost, provenance) round-trip and validation."""
    targets = [{"metric": "alpha_resonance", "value": 4.0}]
    cost = {"memory_bytes": 1024, "ops_per_tick": 500, "verdict": "fits"}
    prov = {"authors": [{"name": "Jane Doe", "orcid": "0000-0002-1825-0097"}], "doi": "10.1101/2026.01.01.123456"}
    p = Project(targets=targets, compute_cost=cost, provenance=prov)
    assert p.version == "1.2.0"
    p.save(tmp_path / "p120.json")

    loaded = Project.load(tmp_path / "p120.json")
    assert loaded.version == "1.2.0"
    assert loaded.targets == targets
    assert loaded.compute_cost == cost
    assert loaded.provenance == prov

    # Validation: targets can be list or dict
    d = loaded.to_dict()
    schema.validate(d)
    d["targets"] = {"metric": "alpha"}
    schema.validate(d)

    # Rejection: invalid targets type
    d["targets"] = "not-a-list-or-dict"
    with pytest.raises(ValueError, match="targets"):
        schema.validate(d)

    # Rejection: invalid compute_cost type
    d["targets"] = targets
    d["compute_cost"] = [1, 2, 3]
    with pytest.raises(ValueError, match="compute_cost"):
        schema.validate(d)

    # Rejection: invalid provenance type
    d["compute_cost"] = cost
    d["provenance"] = "invalid"
    with pytest.raises(ValueError, match="provenance"):
        schema.validate(d)
