import numpy as np
from typing import Dict, Any, Tuple

from neurogenesis.tissue import Tissue
from neurogenesis.params import Param, resolve, Const
from neurogenesis.stages.base import register_stage

@register_stage("migrate")
class MigrateStage:
    def __init__(self):
        pass

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> Tuple[int, int]:
        bytes_cost = N * 8 * 10
        ops_cost = N * 10
        return int(bytes_cost), int(ops_cost)

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0:
            return tissue
            
        speed_param = params.get("speed", Const(0.0))
        speed = resolve(speed_param, genome, fields, tissue.positions)
        
        radial = params.get("radial", Const(False))
        is_radial = resolve(radial, genome, fields, tissue.positions)
        
        target_param = params.get("target", Const(np.array([0.0, 0.0, 0.0])))
        target = resolve(target_param, genome, fields, tissue.positions)
        
        dir_param = params.get("direction", Const(np.array([1.0, 0.0, 0.0])))
        base_directions = resolve(dir_param, genome, fields, tissue.positions)
        if base_directions.shape == (3,):
            base_directions = np.tile(base_directions, (N, 1))

        diff = tissue.positions - target
        norms = np.linalg.norm(diff, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        radial_directions = diff / norms
        
        if np.isscalar(is_radial):
            if is_radial:
                directions = radial_directions
            else:
                directions = base_directions
        else:
            if is_radial.ndim == 1:
                is_radial_mask = is_radial[:, np.newaxis]
            else:
                is_radial_mask = is_radial
            directions = np.where(is_radial_mask, radial_directions, base_directions)

        norms = np.linalg.norm(directions, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        directions = directions / norms

        if np.isscalar(speed):
            step = speed * directions
        else:
            if speed.ndim == 1:
                speed = speed[:, np.newaxis]
            step = speed * directions

        new_positions = tissue.positions + step
        
        stop_field_param = params.get("stop_field", None)
        boundary_param = params.get("boundary", None)
        
        mask = np.ones(N, dtype=bool)

        if stop_field_param is not None:
            stop_condition = resolve(stop_field_param, genome, fields, new_positions)
            if np.isscalar(stop_condition):
                if stop_condition:
                    mask[:] = False
            else:
                if stop_condition.dtype == bool:
                    mask &= ~stop_condition
                else:
                    mask &= (stop_condition <= 0)
                    
        if boundary_param is not None:
            boundary_name = resolve(boundary_param, genome, fields, tissue.positions)
            if isinstance(boundary_name, str) and boundary_name in fields:
                geom = fields[boundary_name]
                if hasattr(geom, "contains"):
                    mask &= geom.contains(new_positions)
                    
        tissue.positions = np.where(mask[:, np.newaxis], new_positions, tissue.positions)
            
        return tissue
            
        speed_param = params.get("speed", Const(1.0))
        speed = resolve(speed_param, genome, fields, tissue.positions)
        
        radial = params.get("radial", Const(False))
        is_radial = resolve(radial, genome, fields, tissue.positions)
        
        target_param = params.get("target", Const(np.array([0.0, 0.0, 0.0])))
        target = resolve(target_param, genome, fields, tissue.positions)
        
        dir_param = params.get("direction", Const(np.array([1.0, 0.0, 0.0])))
        base_directions = resolve(dir_param, genome, fields, tissue.positions)
        if base_directions.shape == (3,):
            base_directions = np.tile(base_directions, (N, 1))

        diff = tissue.positions - target
        norms = np.linalg.norm(diff, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        radial_directions = diff / norms
        
        if np.isscalar(is_radial):
            if is_radial:
                directions = radial_directions
            else:
                directions = base_directions
        else:
            if is_radial.ndim == 1:
                is_radial_mask = is_radial[:, np.newaxis]
            else:
                is_radial_mask = is_radial
            directions = np.where(is_radial_mask, radial_directions, base_directions)

        norms = np.linalg.norm(directions, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        directions = directions / norms

        if np.isscalar(speed):
            step = speed * directions
        else:
            if speed.ndim == 1:
                speed = speed[:, np.newaxis]
            step = speed * directions

        new_positions = tissue.positions + step
        
        stop_field_param = params.get("stop_field", None)
        if stop_field_param is not None:
            stop_condition = resolve(stop_field_param, genome, fields, new_positions)
            if np.isscalar(stop_condition):
                if not stop_condition:
                    tissue.positions = new_positions
            else:
                if stop_condition.dtype == bool:
                    mask = ~stop_condition
                else:
                    mask = stop_condition <= 0
                tissue.positions = np.where(mask[:, np.newaxis] if mask.ndim == 1 else mask, new_positions, tissue.positions)
        else:
            tissue.positions = new_positions
            
        return tissue

@register_stage("sort")
class SortStage:
    def __init__(self):
        pass

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> Tuple[int, int]:
        bytes_cost = N * 8 * 7
        ops_cost = int(N * np.log2(max(2, N)) + N * 3)
        return int(bytes_cost), int(ops_cost)

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0 or ("axis" not in params and "key" not in params):
            return tissue
            
        axis_param = params.get("axis", Const(np.array([0.0, 0.0, 1.0])))
        axis = resolve(axis_param, genome, fields, tissue.positions)
        if axis.shape == (3,):
            axis = axis / (np.linalg.norm(axis) + 1e-9)
        else:
            norms = np.linalg.norm(axis, axis=1, keepdims=True)
            norms[norms < 1e-9] = 1.0
            axis = axis / norms

        key_param = params.get("key", Const("birth_stage"))
        key = resolve(key_param, genome, fields, tissue.positions)
        if isinstance(key, np.ndarray) and key.size > 1:
             sort_values = key
        else:
            key_str = str(key)
            if key_str == "birth_stage":
                sort_values = tissue.birth_stage
            elif key_str == "expression":
                if tissue.expression.shape[1] > 0:
                    sort_values = tissue.expression[:, 0]
                else:
                    sort_values = np.zeros(N)
            else:
                sort_values = np.zeros(N)
                
        sort_idx = np.argsort(sort_values)
        
        if axis.ndim == 1:
            projections = np.dot(tissue.positions, axis)
        else:
            projections = np.sum(tissue.positions * axis, axis=1)
            
        sorted_projections = np.sort(projections)
        
        if axis.ndim == 1:
            positions_no_proj = tissue.positions - np.outer(projections, axis)
            new_positions = positions_no_proj.copy()
            new_positions[sort_idx] += np.outer(sorted_projections, axis)
            tissue.positions = new_positions
        else:
            positions_no_proj = tissue.positions - projections[:, np.newaxis] * axis
            new_positions = positions_no_proj.copy()
            new_positions[sort_idx] += sorted_projections[:, np.newaxis] * axis[sort_idx]
            tissue.positions = new_positions

        return tissue
