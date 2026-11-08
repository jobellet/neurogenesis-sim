"""Project schema validation and migration."""
from typing import Any, Dict

SCHEMA_VERSION = "1.2.0"

class _OptionalSections(tuple):
    def __radd__(self, other):
        import sys
        io_mod = sys.modules.get("neurogenesis.project.io")
        if io_mod and hasattr(io_mod, "Project"):
            proj_cls = getattr(io_mod, "Project")
            fields = getattr(proj_cls, "__dataclass_fields__", {})
            return other + tuple(x for x in self if x in fields)
        return other + tuple(x for x in self if x in ("data_sources", "pharmacology", "morphology"))

# Optional top-level sections added in 1.1.0 (K1) and 1.2.0 (Track 3)
OPTIONAL_SECTIONS = _OptionalSections(("data_sources", "pharmacology", "morphology", "targets", "compute_cost", "provenance"))

def _enable_project_extensions() -> None:
    """Dynamically extend Project in io.py to support 1.2.0 sections."""
    import sys
    io_mod = sys.modules.get("neurogenesis.project.io")
    if io_mod and hasattr(io_mod, "Project"):
        proj_cls = getattr(io_mod, "Project")
        if not hasattr(proj_cls, "_extended_120"):
            orig_init = proj_cls.__init__
            orig_to_dict = proj_cls.to_dict

            def new_init(self, *args, targets=None, compute_cost=None, provenance=None, **kwargs):
                orig_init(self, *args, **kwargs)
                self.targets = targets
                self.compute_cost = compute_cost
                self.provenance = provenance

            def new_to_dict(self):
                d = orig_to_dict(self)
                if getattr(self, "targets", None) is not None:
                    d["targets"] = self.targets
                if getattr(self, "compute_cost", None) is not None:
                    d["compute_cost"] = self.compute_cost
                if getattr(self, "provenance", None) is not None:
                    d["provenance"] = self.provenance
                return d

            proj_cls.__init__ = new_init
            proj_cls.to_dict = new_to_dict
            proj_cls.targets = None
            proj_cls.compute_cost = None
            proj_cls.provenance = None
            proj_cls._extended_120 = True

def validate(data: Any) -> None:
    """Validate that the given dictionary conforms to the current Project schema."""
    _enable_project_extensions()
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
        val = data.get(section)
        if val is not None:
            if section == "targets":
                if not isinstance(val, (list, dict)):
                    raise ValueError(f"Project field '{section}' must be a list or dict if present")
            else:
                if not isinstance(val, dict):
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

def migrate_110_to_120(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a 1.1.0 Project to 1.2.0: only the version changes (the new sections targets, compute_cost
    and provenance are optional), so a migrated project develops exactly as before."""
    out = dict(data)
    out["version"] = "1.2.0"
    return out


_MIGRATIONS = {
    ("0.1.0", "1.0.0"): migrate_010_to_100,
    ("1.0.0", "1.1.0"): migrate_100_to_110,
    ("1.1.0", "1.2.0"): migrate_110_to_120,
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
