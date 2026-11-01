from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List, Optional, Union, Tuple
import numpy as np

from neurogenesis.params import Param
from neurogenesis.tissue import Tissue

STAGE_REGISTRY: Dict[str, type] = {}

def register_stage(name: str):
    def decorator(cls: type):
        STAGE_REGISTRY[name] = cls
        cls.operator_name = name
        return cls
    return decorator


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
        
    def run(self, tissue: Tissue, genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        cls = STAGE_REGISTRY.get(self.operator)
        if not cls:
            raise ValueError(f"Operator '{self.operator}' not found in registry")
        # Ensure we pass the required arguments
        if hasattr(cls, 'run'):
            return cls().run(tissue, self.params, genome, fields, rng)
        elif hasattr(cls, '__call__'):
            return cls()(tissue, self.params, genome, fields, rng)
        else:
            raise ValueError(f"Operator {self.operator} is not callable")

def schedule_cost(project: Dict[str, Any], N: int, E: int) -> Tuple[int, int]:
    """Sums up the expected bytes and ops cost of the entire schedule."""
    total_bytes = 0
    total_ops = 0
    schedule_configs = project.get("schedule", [])
    
    for stage_idx, config in enumerate(schedule_configs):
        stage = Stage(
            name=config.get("name", f"stage_{stage_idx}"),
            operator=config["operator"],
            params=config.get("params", {}),
            when=config.get("when"),
            repeat=config.get("repeat", 1)
        )
        
        bytes_cost, ops_cost = stage.cost(N, E)
        total_bytes += bytes_cost * stage.repeat
        total_ops += ops_cost * stage.repeat
        
    return total_bytes, total_ops

def run_schedule(project: Dict[str, Any], genome: Dict[str, Any], seed: int, checkpoints: bool = False) -> Union[Tissue, List[Tissue]]:
    schedule_configs = project.get("schedule", [])
    fields = project.get("fields", {})
    
    tissue = Tissue.empty()
    checkpoints_list = []
        
    for stage_idx, config in enumerate(schedule_configs):
        stage = Stage(
            name=config.get("name", f"stage_{stage_idx}"),
            operator=config["operator"],
            params=config.get("params", {}),
            when=config.get("when"),
            repeat=config.get("repeat", 1)
        )
        
        for rep in range(stage.repeat):
            stage_salt = rep
            rng = np.random.default_rng([seed, stage_idx, stage_salt])
            
            tissue = stage.run(tissue, genome, fields, rng)
            
            if checkpoints:
                checkpoints_list.append(copy.deepcopy(tissue))
                
    if checkpoints:
        return checkpoints_list
    return tissue
