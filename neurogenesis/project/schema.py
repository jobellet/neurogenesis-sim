"""Project schema validation and migration."""
from typing import Any, Dict

SCHEMA_VERSION = "1.1.0"

# Optional top-level sections added in 1.1.0 (K1): absent or a dict.
OPTIONAL_SECTIONS = ("data_sources", "pharmacology", "morphology")

def validate(data: Any) -> None:
    """Validate that the given dictionary conforms to the current Project schema."""
    if not isinstance(data, dict):
        raise ValueError("Project data must be a dictionary")
    
    if "version" not in data:
        raise ValueError("Project data must contain a 'version' key")
    
    if not isinstance(data["version"], str):
        raise ValueError("'version' must be a string")
        
    expected_fields = {
        "geometry": dict,
        "fields": dict,
        "schedule": list,
        "genome": dict,
        "plugins": list,
        "metadata": dict,
    }
    
    for field, expected_type in expected_fields.items():
        if field not in data:
            raise ValueError(f"Project missing required field: '{field}'")
        if not isinstance(data[field], expected_type):
            raise ValueError(f"Project field '{field}' must be of type {expected_type.__name__}")
            
    if "plan" in data and data["plan"] is not None and not isinstance(data["plan"], dict):
        raise ValueError("Project field 'plan' must be a dict if present")
        
    if "neuron_model" in data and not isinstance(data["neuron_model"], str):
        raise ValueError("Project field 'neuron_model' must be a string if present")

    for section in OPTIONAL_SECTIONS:
        if data.get(section) is not None and not isinstance(data[section], dict):
            raise ValueError(f"Project field '{section}' must be a dict if present")
    ds = data.get("data_sources") or {}
    for name, src in ds.items():
        if not isinstance(src, dict) or "dataset" not in src:
            raise ValueError(f"data source {name!r} must be a dict with a 'dataset' id")

def migrate_010_to_100(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a 0.1.0 legacy BodyPlan to a 1.0.0 Project."""
    return {
        "version": "1.0.0",
        "geometry": {},
        "fields": {},
        "schedule": [],
        "genome": {},
        "plan": data,
        "plugins": data.get("plugins", []),
        "neuron_model": "lif_int",
        "metadata": {}
    }

def migrate_100_to_110(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a 1.0.0 Project to 1.1.0: only the version changes (the new sections data_sources, pharmacology and
    morphology are optional), so a migrated project develops exactly as before."""
    out = dict(data)
    out["version"] = "1.1.0"
    return out


_MIGRATIONS = {
    ("0.1.0", "1.0.0"): migrate_010_to_100,
    ("1.0.0", "1.1.0"): migrate_100_to_110,
}


def migrate(data: Dict[str, Any], from_version: str, to_version: str) -> Dict[str, Any]:
    """Migrate data from one version to another, through intermediate versions if needed (e.g. 0.1.0 -> 1.0.0 ->
    1.1.0)."""
    if from_version == to_version:
        return data
    if (from_version, to_version) in _MIGRATIONS:
        return _MIGRATIONS[(from_version, to_version)](data)
    # breadth-first search for a chain of single-step migrations
    paths = [[from_version]]
    seen = {from_version}
    while paths:
        path = paths.pop(0)
        for (a, b) in _MIGRATIONS:
            if a == path[-1] and b not in seen:
                if b == to_version:
                    for x, y in zip(path, path[1:] + [b]):
                        data = _MIGRATIONS[(x, y)](data)
                    return data
                seen.add(b)
                paths.append(path + [b])
    raise ValueError(f"No migration path found from {from_version} to {to_version}")
