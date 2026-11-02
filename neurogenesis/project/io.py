"""Project I/O for reading and writing projects."""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from . import schema

@dataclass
class Project:
    version: str = schema.SCHEMA_VERSION
    geometry: Dict[str, Any] = field(default_factory=dict)
    fields: Dict[str, Any] = field(default_factory=dict)
    schedule: List[Dict[str, Any]] = field(default_factory=list)
    genome: Dict[str, Any] = field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    plugins: List[str] = field(default_factory=list)
    neuron_model: str = "lif_int"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the project to a dictionary, removing None values where appropriate."""
        d = asdict(self)
        if self.plan is None:
            del d["plan"]
        return d

    def save(self, path: str | Path) -> None:
        """Save the project to a JSON file and a sidecar .npz file for large arrays."""
        path = Path(path)
        stem = str(path.with_suffix(''))
        npz_path = f"{stem}.npz"
        
        d = self.to_dict()
        schema.validate(d)
        
        arrays = {}
        array_counter = [0]
        
        def extract_arrays(obj: Any) -> Any:
            if isinstance(obj, np.ndarray):
                key = f"arr_{array_counter[0]}"
                array_counter[0] += 1
                arrays[key] = obj
                return {"$npz": key}
            elif isinstance(obj, dict):
                return {k: extract_arrays(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [extract_arrays(v) for v in obj]
            elif isinstance(obj, tuple):
                return tuple(extract_arrays(v) for v in obj)
            return obj
            
        json_data = extract_arrays(d)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
            
        if arrays:
            np.savez_compressed(npz_path, **arrays)
            
    @classmethod
    def load(cls, path: str | Path) -> "Project":
        """Load a project from a JSON file and its sidecar .npz file if present."""
        path = Path(path)
        stem = str(path.with_suffix(''))
        npz_path = Path(f"{stem}.npz")
        
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
            
        arrays = {}
        if npz_path.exists():
            npz_file = np.load(npz_path)
            arrays = {k: npz_file[k] for k in npz_file.files}
            
        def restore_arrays(obj: Any) -> Any:
            if isinstance(obj, dict):
                if len(obj) == 1 and "$npz" in obj:
                    key = obj["$npz"]
                    if key in arrays:
                        return arrays[key]
                    raise ValueError(f"Missing array reference '{key}' in sidecar file")
                return {k: restore_arrays(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [restore_arrays(v) for v in obj]
            elif isinstance(obj, tuple):
                return tuple(restore_arrays(v) for v in obj)
            return obj
            
        d = restore_arrays(d)
        
        if "version" not in d:
            raise ValueError("Project data must contain a 'version' key")
            
        if d["version"] != schema.SCHEMA_VERSION:
            d = schema.migrate(d, d["version"], schema.SCHEMA_VERSION)
            
        schema.validate(d)
        return cls(**d)
