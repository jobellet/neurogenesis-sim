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
                if isinstance(w_val, (list, tuple)):
                    w = [resolve(x, genome, fields, None) for x in w_val]   # entries may be Params (e.g. Genes)
                else:
                    w = resolve(w_val, genome, fields, None)

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
        
        kind = str(resolve(params.get("activation", "sigmoid"), genome, fields, None))
        if kind == "sigmoid":
            activation = 1.0 / (1.0 + np.exp(-np.clip(total_input, -30, 30)))
        elif kind == "hill":
            # Hill activation x^n / (k^n + x^n) of the positive part of the input (Alon 2006, An Introduction to
            # Systems Biology); 0 without input, so a Hill step with zero weights only applies decay.
            n = float(resolve(params.get("hill_n", 2.0), genome, fields, None))
            k = float(resolve(params.get("hill_k", 1.0), genome, fields, None))
            xn = np.power(np.maximum(total_input, 0.0), n)
            activation = xn / (k ** n + xn)
        else:
            raise ValueError(f"express: unknown activation {kind!r} (use 'sigmoid' or 'hill')")
        
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
            "cell_id": tissue.cell_id,
            "cell_type": tissue.cell_type,
            "generation": tissue.generation,
            "cycling": tissue.cycling,
            "birth_stage": tissue.birth_stage,
            "birth_time": tissue.birth_time,
            "parent": tissue.parent_id,
            "clone": tissue.clone_id,
            "region": tissue.region,
            "x": tissue.positions[:, 0],
            "y": tissue.positions[:, 1],
            "z": tissue.positions[:, 2],
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


@register_stage("temporal_competence")
class TemporalCompetence:
    """Progressive, irreversible progenitor competence cascade (McConnell & Kaznowski 1991, Science;
    McConnell 1995, Neuron; Isshiki et al. 2001, Cell).

    Competence channels in `Tissue.expression` advance one way only for cycling alive cells (`alive & cycling`)
    and are fixed once a cell leaves the cell cycle (`cycling == False`). Driven by `generation` (or `driver` /
    `mapping` `Param`) and optionally advanced by an environmental cue (`environment` / `field` `Param`), never
    reversed. Supports both:
    - cascade channels (`[{"channel": c, "until": threshold}, ...]`), which start competent (`1.0`) and switch
      irreversibly off (`0.0`) once the effective driver exceeds `until`;
    - monotonic state channels (`channels: [c, ...]`), which advance monotonically via `maximum(expr[:, c], driver)`.
    Without `channels`, the stage is a no-op.
    """

    @staticmethod
    def cost(N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        ch = worst_case(params.get("channels"), [])
        n_ch = len(ch) if isinstance(ch, (list, tuple)) else (1 if ch is not None else 1)
        n_ch = max(1, n_ch)
        n = max(1, N)
        return (n * max(24, n_ch * 8), n * max(12, n_ch * 8))

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0 or not params:
            return tissue

        channels_raw = params.get("channels")
        if channels_raw is None:
            return tissue
        channels_val = resolve(channels_raw, genome, fields, None)
        if not isinstance(channels_val, (list, tuple, np.ndarray)):
            if channels_val is None:
                return tissue
            channels_val = [channels_val]
        if len(channels_val) == 0:
            return tissue

        exited_this_cycle = getattr(tissue, "_clock_exited_mask", None)
        if exited_this_cycle is not None and len(exited_this_cycle) == N:
            mask = tissue.alive & (tissue.cycling | exited_this_cycle)
            tissue._clock_exited_mask = None
        else:
            mask = tissue.alive & tissue.cycling
        if not np.any(mask):
            return tissue

        env = {
            **(genome if isinstance(genome, dict) else {}),
            "np": np,
            "N": N,
            "generation": tissue.generation,
            "cycling": tissue.cycling,
            "birth_stage": tissue.birth_stage,
            "birth_time": tissue.birth_time,
            "cell_type": tissue.cell_type,
            "region": tissue.region,
            "x": tissue.positions[:, 0],
            "y": tissue.positions[:, 1],
            "z": tissue.positions[:, 2],
        }
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

        driver_param = params.get("driver", params.get("mapping", params.get("target")))
        if driver_param is None:
            driver_arr = tissue.generation.astype(np.float32)
        else:
            d_val = resolve(driver_param, genome, fields, positions=tissue.positions, context_vars=env)
            if isinstance(d_val, dict):
                driver_arr = np.array(
                    [float(d_val.get(int(g), d_val.get(str(int(g)), g))) for g in tissue.generation],
                    dtype=np.float32,
                )
            elif isinstance(d_val, (list, tuple)) or (
                isinstance(d_val, np.ndarray) and d_val.ndim == 1 and len(d_val) != N
            ):
                table = np.asarray(d_val, dtype=np.float32)
                idx = np.clip(tissue.generation, 0, max(0, len(table) - 1))
                driver_arr = table[idx] if len(table) > 0 else tissue.generation.astype(np.float32)
            elif np.isscalar(d_val):
                driver_arr = np.full(N, float(d_val), dtype=np.float32)
            else:
                driver_arr = np.asarray(d_val, dtype=np.float32).reshape(N)

        env_param = params.get("environment", params.get("field"))
        if env_param is not None:
            if isinstance(env_param, str) and env_param in fields:
                f_obj = fields[env_param]
                e_val = f_obj.values(tissue.positions) if isinstance(f_obj, Field) else resolve(env_param, genome, fields, positions=tissue.positions, context_vars=env)
            else:
                e_val = resolve(env_param, genome, fields, positions=tissue.positions, context_vars=env)
            if np.isscalar(e_val):
                env_arr = np.full(N, float(e_val), dtype=np.float32)
            else:
                env_arr = np.asarray(e_val, dtype=np.float32).reshape(N)
            driver_arr = np.maximum(driver_arr, env_arr)

        # Determine required expression columns K
        cascade_specs = []
        monotonic_cols = []
        thresholds_param = params.get("thresholds")
        thresholds_val = resolve(thresholds_param, genome, fields, None) if thresholds_param is not None else None

        for idx, item in enumerate(channels_val):
            if isinstance(item, dict):
                c_idx = int(item.get("channel", idx))
                u_param = item.get("until", item.get("max_driver", item.get("threshold")))
                cascade_specs.append((c_idx, u_param))
            elif thresholds_val is not None and idx < len(thresholds_val):
                cascade_specs.append((int(item), thresholds_val[idx]))
            else:
                monotonic_cols.append(int(item))

        all_cols = [c for c, _ in cascade_specs] + monotonic_cols
        req_k = (max(all_cols) + 1) if all_cols else 0
        if req_k > tissue.expression.shape[1]:
            new_expr = np.zeros((N, req_k), dtype=np.float32)
            old_k = tissue.expression.shape[1]
            if old_k > 0:
                new_expr[:, :old_k] = tissue.expression
            tissue.expression = new_expr

        if cascade_specs:
            cascade_cols = [c for c, _ in cascade_specs]
            # Initialize brand-new cycling cells (whose cascade channels are all 0) to competent (1.0)
            uninit = mask & (np.sum(tissue.expression[:, cascade_cols], axis=1) == 0.0)
            if np.any(uninit):
                for c in cascade_cols:
                    tissue.expression[uninit, c] = 1.0

            for c, u_param in cascade_specs:
                if u_param is None:
                    continue
                u_val = resolve(u_param, genome, fields, positions=tissue.positions, context_vars=env)
                if np.isscalar(u_val):
                    u_arr = np.full(N, float(u_val), dtype=np.float32)
                else:
                    u_arr = np.asarray(u_val, dtype=np.float32).reshape(N)
                competent = (driver_arr <= u_arr).astype(np.float32)
                tissue.expression[mask, c] = np.minimum(tissue.expression[mask, c], competent[mask])

        for c in monotonic_cols:
            tissue.expression[mask, c] = np.maximum(tissue.expression[mask, c], driver_arr[mask])

        return tissue
