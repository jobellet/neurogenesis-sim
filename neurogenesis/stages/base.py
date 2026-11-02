from __future__ import annotations

import copy
import importlib
import zlib
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List, Optional, Union, Tuple
import numpy as np

from neurogenesis.params import Param, param_from_dict, param_to_dict, resolve
from neurogenesis.tissue import Tissue
from neurogenesis.geometry import Geometry, geometry_from_dict, _GEOMETRY_REGISTRY
from neurogenesis.fields import Field, field_from_dict, _FIELD_REGISTRY
from neurogenesis.expressions import eval_expr

STAGE_REGISTRY: Dict[str, type] = {}

def register_stage(name: str):
    def decorator(cls: type):
        STAGE_REGISTRY[name] = cls
        cls.operator_name = name
        return cls
    return decorator


def _eval_condition(condition: str, tissue: Tissue, genome: Dict[str, Any], stage_rep: int) -> bool:
    """Evaluates when condition string against current simulation state."""
    if not condition:
        return True
    
    env = {
        "N": len(tissue.alive) if len(tissue.alive) > 0 else 0,
        "N_alive": int(np.sum(tissue.alive)) if len(tissue.alive) > 0 else 0,
        "E": len(tissue.connectivity.pre) if len(tissue.connectivity.pre) > 0 else 0,
        "rep": stage_rep,
        "tissue": tissue,
        "genome": genome,
        "np": np
    }
    try:
        return bool(eval_expr(condition, env))
    except Exception as e:
        raise ValueError(f"Failed to evaluate stage condition '{condition}': {e}")


@dataclass
class Stage:
    name: str
    operator: str
    params: Dict[str, Param]
    when: Optional[str] = None
    repeat: int = 1

    def cost(self, N: int, E: int) -> Tuple[int, int]:
        """Returns (bytes, ops) cost of the stage."""
        cls = STAGE_REGISTRY.get(self.operator)
        if cls and hasattr(cls, 'cost'):
            return cls.cost(N, E, self.params)
        return (0, 0)
        
    def run(self, tissue: Tissue, genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator, rep: int = 0) -> Tissue:
        if self.when and not _eval_condition(self.when, tissue, genome, rep):
            return tissue

        cls = STAGE_REGISTRY.get(self.operator)
        if not cls:
            raise ValueError(f"Operator '{self.operator}' not found in registry (available: {list(STAGE_REGISTRY.keys())})")
            
        # Resolve dictionary params into Param objects if needed
        parsed_params = {
            k: (param_from_dict(v) if isinstance(v, dict) else v)
            for k, v in self.params.items()
        }

        instance = cls()
        if hasattr(instance, 'run'):
            return instance.run(tissue, parsed_params, genome, fields, rng)
        elif callable(instance):
            return instance(tissue, parsed_params, genome, fields, rng)
        else:
            raise ValueError(f"Operator {self.operator} is not callable")


def schedule_cost(project: Dict[str, Any], N: int, E: int) -> Tuple[int, int]:
    """Sums up the expected bytes and ops cost of the entire schedule."""
    total_bytes = 0
    total_ops = 0
    schedule_configs = project.get("schedule", [])
    
    for stage_idx, config in enumerate(schedule_configs):
        params = {k: param_from_dict(v) if isinstance(v, dict) else v for k, v in config.get("params", {}).items()}
        stage = Stage(
            name=config.get("name", f"stage_{stage_idx}"),
            operator=config["operator"],
            params=params,
            when=config.get("when"),
            repeat=config.get("repeat", 1)
        )
        
        bytes_cost, ops_cost = stage.cost(N, E)
        total_bytes += bytes_cost * stage.repeat
        total_ops += ops_cost * stage.repeat
        
    return total_bytes, total_ops


def _instantiate_fields(raw_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Instantiates fields and geometries from raw project definitions.
    
    Unknown types raise ValueError immediately. Never falls back silently.
    """
    instantiated = {}
    for name, f_def in raw_fields.items():
        if isinstance(f_def, (Geometry, Field)):
            instantiated[name] = f_def
        elif isinstance(f_def, dict):
            type_name = f_def.get("type")
            if not type_name:
                raise ValueError(f"Field or geometry {name!r} dictionary missing required 'type' field")
            if type_name in _GEOMETRY_REGISTRY:
                instantiated[name] = geometry_from_dict(f_def)
            elif type_name in _FIELD_REGISTRY or type_name.lower() in _FIELD_REGISTRY:
                instantiated[name] = field_from_dict(f_def)
            else:
                raise ValueError(
                    f"Unknown field or geometry type: {type_name!r} for {name!r}. "
                    f"Must be a registered geometry ({sorted(_GEOMETRY_REGISTRY.keys())}) "
                    f"or field ({sorted(_FIELD_REGISTRY.keys())})."
                )
        else:
            instantiated[name] = f_def
    return instantiated


def run_schedule(
    project: Dict[str, Any],
    genome: Dict[str, Any],
    seed: int,
    checkpoints: bool = False,
    legacy_stream: bool = False
) -> Union[Tissue, List[Tissue]]:
    # 1. Import plugins
    for plugin in project.get("plugins", []):
        importlib.import_module(plugin)
        
    schedule_configs = project.get("schedule", [])
    raw_geoms = project.get("geometry", {})
    raw_fields = project.get("fields", {})
    combined_raw = {**raw_geoms, **raw_fields}
    fields = _instantiate_fields(combined_raw)
    fields = {k: (v.bind(genome) if isinstance(v, Field) else v) for k, v in fields.items()}
    
    tissue = Tissue.empty()
    checkpoints_list = []
    
    # Shared RNG stream if legacy_stream=True
    legacy_rng = np.random.default_rng(seed) if legacy_stream else None
        
    for stage_idx, config in enumerate(schedule_configs):
        stage_name = config.get("name", f"stage_{stage_idx}")
        # Stable name salt independent of stage position in schedule
        name_salt = zlib.crc32(stage_name.encode("utf-8")) & 0xFFFFFFFF
        
        params = {
            k: (param_from_dict(v) if isinstance(v, dict) else v)
            for k, v in config.get("params", {}).items()
        }
        
        stage = Stage(
            name=stage_name,
            operator=config["operator"],
            params=params,
            when=config.get("when"),
            repeat=config.get("repeat", 1)
        )
        
        for rep in range(stage.repeat):
            # Seed stream is isolated by (seed, name_salt, rep) unless legacy_stream is enabled
            if legacy_stream:
                rng = legacy_rng
            else:
                rng = np.random.default_rng([seed, name_salt, rep])
            
            tissue = stage.run(tissue, genome, fields, rng, rep=rep)
            
            if checkpoints:
                checkpoints_list.append(copy.deepcopy(tissue))
                
    if checkpoints:
        return checkpoints_list
    return tissue
