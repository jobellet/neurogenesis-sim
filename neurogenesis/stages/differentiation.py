import numpy as np
import math
from typing import Dict, Any, Tuple
from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue
from neurogenesis.params import resolve, Param, worst_case
from neurogenesis.spatial import CellList
from neurogenesis.fields import Field
from neurogenesis.geometry import Geometry
from neurogenesis.expressions import eval_expr


# Mean neighbours per cell assumed by the express cost when radius > 0 (cell-list bins of side radius).
_EXPRESS_MEAN_NEIGHBOURS = 27


@register_stage("express")
class Express:
    @staticmethod
    def cost(N: int, E: int, params: Dict[str, Param]) -> Tuple[int, int]:
        K = int(worst_case(params.get("K"), 0))
        # O(N K^2) operations
        ops = N * K * K * 4
        bytes_cost = N * K * 8
        if K > 0 and float(worst_case(params.get("radius"), 0.0)) > 0:
            nb = _EXPRESS_MEAN_NEIGHBOURS
            cl_bytes, cl_ops = CellList.declared_cost(N, N, nb)
            bytes_cost += cl_bytes + N * nb * K * 4 + N * K * 8
            ops += cl_ops + N * nb * K + N * K * K * 2
        return (bytes_cost, ops)

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0:
            return tissue

        # Neutral parameters
        if not params:
            return tissue
            
        K = int(resolve(params.get("K", 0), genome, fields, None))
        if K <= 0:
            return tissue
            
        if tissue.expression.shape[1] != K:
            new_expr = np.zeros((N, K), dtype=np.float32)
            min_k = min(tissue.expression.shape[1], K)
            if min_k > 0:
                new_expr[:, :min_k] = tissue.expression[:, :min_k]
            tissue.expression = new_expr

        W_param = params.get("weights")
        W = resolve(W_param, genome, fields, None) if W_param is not None else None
        
        if W is None:
            W = np.zeros((K, K), dtype=np.float32)
        elif isinstance(W, list):
            W = np.array(W, dtype=np.float32)
        elif isinstance(W, np.ndarray):
            W = W.astype(np.float32)
        else:
            W = np.zeros((K, K), dtype=np.float32)
            
        if W.shape != (K, K):
            if len(W.shape) == 1 and len(W) == K*K:
                W = W.reshape(K, K)
            else:
                W = np.zeros((K, K), dtype=np.float32)
                
        morphogens = params.get("morphogens")
        morphogens_val = resolve(morphogens, genome, fields, None) if morphogens is not None else []
        if not isinstance(morphogens_val, list):
            morphogens_val = getattr(morphogens, "value", [])
        
        morphogen_inputs = np.zeros((N, K), dtype=np.float32)
        for m in morphogens_val:
            if isinstance(m, dict):
                f_val = resolve(m.get("field"), genome, fields, tissue.positions)
                w_val = m.get("weights")
                if hasattr(w_val, "type") or hasattr(w_val, "value"):
                    w = resolve(w_val, genome, fields, None)
                else:
                    w = w_val
                    
                w = np.array(w, dtype=np.float32)
                
                if isinstance(f_val, (float, int)):
                    f_val = np.full(N, f_val, dtype=np.float32)
                else:
                    f_val = np.asarray(f_val, dtype=np.float32)
                    
                morphogen_inputs += f_val[:, np.newaxis] * w[np.newaxis, :]
            
        neighbor_inputs = np.zeros((N, K), dtype=np.float32)
        radius = float(resolve(params.get("radius", 0.0), genome, fields, None))
        
        if radius > 0:
            cl = CellList(tissue.positions, radius)
            src, dst = cl.query_radius(tissue.positions, radius)
            
            W_n_param = params.get("neighbor_weights")
            W_n = resolve(W_n_param, genome, fields, None) if W_n_param is not None else np.zeros((K, K))
            if isinstance(W_n, list):
                W_n = np.array(W_n, dtype=np.float32)
            W_n = W_n.reshape((K, K))
            
            neighbor_expr_sum = np.zeros((N, K), dtype=np.float32)
            if len(src) > 0:
                mask = src != dst
                src_filtered = src[mask]
                dst_filtered = dst[mask]
                np.add.at(neighbor_expr_sum, src_filtered, tissue.expression[dst_filtered])
                
            neighbor_inputs = neighbor_expr_sum @ W_n.T

        dt = float(resolve(params.get("dt", 1.0), genome, fields, None))
        decay = float(resolve(params.get("decay", 0.0), genome, fields, None))
        
        internal_inputs = tissue.expression @ W.T
        total_input = internal_inputs + morphogen_inputs + neighbor_inputs
        
        activation = 1.0 / (1.0 + np.exp(-np.clip(total_input, -30, 30)))
        
        tissue.expression = tissue.expression * (1.0 - decay * dt) + activation * dt
        
        return tissue

# Per-cell attributes a type spec may set (besides sign and base_weight); each value may be a Param.
_TYPE_FIELDS = ("mode", "shift_v", "shift_s", "conn_radius", "conn_prob", "burst_period", "burst_duty", "poisson_hz",
                "refractory", "role", "compartment", "threshold", "region")


@register_stage("differentiate")
class Differentiate:
    """Assigns cell types and their per-cell attributes to cells matching each type's condition.

    Every attribute value in a type spec may be a Param (Const, Gene, Field, ...), so genes can control it.
    """
    @staticmethod
    def cost(N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        types_val = worst_case(params.get("types"), [])
        num_types = len(types_val) if isinstance(types_val, list) else 0
        ops = N * num_types * 5
        bytes_cost = N * 4
        return (bytes_cost, ops)

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        types_param = params.get("types")
        if N == 0 or not types_param:
            return tissue
            
        types_val = resolve(types_param, genome, fields, None)
        if not isinstance(types_val, list):
            types_val = getattr(types_param, "value", [])
            
        env = {
            "expr": tissue.expression.T, 
            "np": np, 
            "N": N,
            "lineage": tissue.cell_id, # Can use cell_id for lineage matching for simplicity if needed
            "parent": tissue.parent_id,
            "clone": tissue.clone_id
        }

        # Provide fields as arrays inside env
        for k, v in fields.items():
            if isinstance(v, Field):
                env[f"field_{k}"] = v.values(tissue.positions)
            elif isinstance(v, Geometry):
                env[f"geom_{k}"] = v.contains(tissue.positions)
                env[f"field_{k}"] = v.contains(tissue.positions).astype(np.float32)
            elif callable(v):
                env[f"field_{k}"] = v(tissue.positions)
            else:
                env[f"field_{k}"] = np.full(N, v, dtype=np.float32)

        for t_spec in types_val:
            type_id = int(t_spec.get("type_id", 0))
            condition_expr = t_spec.get("condition")
            
            # evaluate condition
            if condition_expr:
                mask = eval_expr(condition_expr, env)
                if isinstance(mask, (bool, np.bool_)):
                    mask = np.full(N, mask, dtype=bool)
                else:
                    mask = np.asarray(mask, dtype=bool)
                    if mask.shape != (N,):
                        raise ValueError(f"Condition '{condition_expr}' produced shape {mask.shape}, expected ({N},)")
            else:
                mask = np.ones(N, dtype=bool)
                
            if np.any(mask):
                tissue.cell_type[mask] = type_id

                def value(key):
                    v = resolve(t_spec[key], genome, fields, tissue.positions)
                    if isinstance(v, np.ndarray) and v.ndim >= 1 and v.shape[0] == N:
                        v = v[mask]
                    return np.asarray(v)

                if "sign" in t_spec:
                    tissue.sign[mask] = value("sign").astype(np.int32)

                # Update base_weight according to Dale principle (magnitude * sign)
                if "base_weight" in t_spec:
                    bw = np.abs(value("base_weight").astype(np.int32))
                    tissue.base_weight[mask] = np.where(tissue.sign[mask] >= 0, bw, -bw)
                elif "sign" in t_spec:
                    # If base_weight isn't specified but sign is, update base_weight sign
                    bw = np.abs(tissue.base_weight[mask])
                    tissue.base_weight[mask] = np.where(tissue.sign[mask] >= 0, bw, -bw)

                for key in _TYPE_FIELDS:
                    if key in t_spec:
                        arr = getattr(tissue, key)
                        arr[mask] = value(key).astype(arr.dtype)

        return tissue
