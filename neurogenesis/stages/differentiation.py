import numpy as np
import math
from typing import Dict, Any, Tuple
from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue
from neurogenesis.params import resolve, Param
from neurogenesis.spatial import CellList

@register_stage("express")
class Express:
    @staticmethod
    def cost(N: int, E: int, params: Dict[str, Param]) -> Tuple[int, int]:
        K_param = params.get("K")
        K = getattr(K_param, "value", 0) if K_param is not None else 0
        if not isinstance(K, int):
            K = 0
            
        # O(N K^2) operations
        ops = N * K * K * 4
        bytes_cost = N * K * 8
        return (bytes_cost, ops)

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0:
            return tissue
            
        if not tissue.alive.all():
            tissue.compact()
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
            return tissue
            
        if isinstance(W, list):
            W = np.array(W, dtype=np.float32)
        elif isinstance(W, np.ndarray):
            W = W.astype(np.float32)
        else:
            return tissue
            
        if W.shape != (K, K):
            if len(W.shape) == 1 and len(W) == K*K:
                W = W.reshape(K, K)
            else:
                return tissue
                
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

@register_stage("differentiate")
class Differentiate:
    @staticmethod
    def cost(N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        types_param = params.get("types")
        num_types = len(getattr(types_param, "value", [])) if types_param is not None else 0
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
            if hasattr(v, 'sample'):
                env[f"field_{k}"] = v.sample(tissue.positions)
            elif callable(v):
                env[f"field_{k}"] = v(tissue.positions)
            else:
                env[f"field_{k}"] = np.full(N, v, dtype=np.float32)

        for t_spec in types_val:
            type_id = int(t_spec.get("type_id", 0))
            condition_expr = t_spec.get("condition")
            
            # evaluate condition
            if condition_expr:
                try:
                    mask = eval(condition_expr, {"__builtins__": {}}, env)
                    if isinstance(mask, bool):
                        mask = np.full(N, mask, dtype=bool)
                except Exception as e:
                    # In case of evaluation error, apply to none
                    mask = np.zeros(N, dtype=bool)
            else:
                mask = np.ones(N, dtype=bool)
                
            if np.any(mask):
                tissue.cell_type[mask] = type_id
                if "sign" in t_spec:
                    tissue.sign[mask] = int(t_spec["sign"])
                    
                # Update base_weight according to Dale principle (magnitude * sign)
                if "base_weight" in t_spec:
                    bw = np.abs(int(t_spec["base_weight"]))
                    tissue.base_weight[mask] = np.where(tissue.sign[mask] >= 0, bw, -bw)
                else:
                    # If base_weight isn't specified but sign is, update base_weight sign!
                    if "sign" in t_spec:
                        bw = np.abs(tissue.base_weight[mask])
                        tissue.base_weight[mask] = np.where(tissue.sign[mask] >= 0, bw, -bw)

                if "mode" in t_spec:
                    tissue.mode[mask] = int(t_spec["mode"])
                if "shift_v" in t_spec:
                    tissue.shift_v[mask] = int(t_spec["shift_v"])
                if "shift_s" in t_spec:
                    tissue.shift_s[mask] = int(t_spec["shift_s"])
                if "conn_radius" in t_spec:
                    tissue.conn_radius[mask] = float(t_spec["conn_radius"])
                if "conn_prob" in t_spec:
                    tissue.conn_prob[mask] = float(t_spec["conn_prob"])
                if "burst_period" in t_spec:
                    tissue.burst_period[mask] = int(t_spec["burst_period"])
                if "burst_duty" in t_spec:
                    tissue.burst_duty[mask] = int(t_spec["burst_duty"])
                if "poisson_hz" in t_spec:
                    tissue.poisson_hz[mask] = float(t_spec["poisson_hz"])
                if "refractory" in t_spec:
                    tissue.refractory[mask] = int(t_spec["refractory"])
                if "role" in t_spec:
                    tissue.role[mask] = int(t_spec["role"])
                if "compartment" in t_spec:
                    tissue.compartment[mask] = int(t_spec["compartment"])
                if "threshold" in t_spec:
                    tissue.threshold[mask] = int(t_spec["threshold"])
                    
        return tissue
