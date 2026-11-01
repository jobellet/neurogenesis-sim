from __future__ import annotations

import warnings
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Union

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.params import Param, resolve
from neurogenesis.stages.base import register_stage
from neurogenesis.development.rules import RULES, GuidanceContext, WeightContext
from neurogenesis.development.sparse_guidance import sparse_guidance

def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def _normalize_proj_key(key: Any) -> Optional[Tuple[Any, Any]]:
    if isinstance(key, tuple) and len(key) == 2:
        return key[0], key[1]
    if isinstance(key, str):
        if "->" in key:
            parts = key.split("->")
            return parts[0].strip(), parts[1].strip()
        if "," in key:
            parts = key.split(",")
            return parts[0].strip(), parts[1].strip()
        if ":" in key:
            parts = key.split(":")
            return parts[0].strip(), parts[1].strip()
    return None


def _get_guidance(guidance_source: Any, src: Any, dst: Any) -> Optional[Dict[str, Any]]:
    if not guidance_source:
        return None
    
    # List of projection dictionaries: [{"src": 0, "dst": 1, ...}]
    if isinstance(guidance_source, list):
        for item in guidance_source:
            if isinstance(item, dict):
                item_src = item.get("src", item.get("source"))
                item_dst = item.get("dst", item.get("target"))
                if (item_src == src and item_dst == dst) or (str(item_src) == str(src) and str(item_dst) == str(dst)):
                    return item
        return None
        
    if isinstance(guidance_source, dict):
        # 1. Exact tuple match
        if (src, dst) in guidance_source:
            return guidance_source[(src, dst)]
        # 2. String representation of tuple or arrow keys
        candidates = [
            f"{src}->{dst}",
            f"{src},{dst}",
            f"{src}:{dst}",
            str((src, dst)),
            f"{str(src)}->{str(dst)}",
            f"{str(src)},{str(dst)}",
            (str(src), str(dst)),
        ]
        for c in candidates:
            if c in guidance_source:
                return guidance_source[c]
                
        # 3. Check parsed keys
        for k, v in guidance_source.items():
            parsed = _normalize_proj_key(k)
            if parsed is not None:
                p_src, p_dst = parsed
                if (p_src == src and p_dst == dst) or (str(p_src) == str(src) and str(p_dst) == str(dst)):
                    return v

        # 4. If single dict with guidance fields, treat as guidance config directly
        if any(k in guidance_source for k in ("B", "c", "sigma", "p0", "w", "rules_shift")):
            return guidance_source

    return None


class _PlanRulesAdapter:
    def __init__(self, prob_rules: List[str]):
        self.rules = {"probability": prob_rules}


@register_stage("grow_axons")
class GrowAxons:
    """Axon guidance and synaptogenesis between region populations (chemoaffinity: Sperry, 1963, PNAS).

    For each projection src->dst, every source cell aims at a target point in the destination's local box,
    ``target = sigmoid(4 (x_src - 0.5) @ B.T + c)`` (after the shift and target rules), and connects to each
    destination cell with probability ``p0 exp(-|x_dst - target|^2 / (2 sigma^2))`` (then the probability rules).
    Weights are ``w`` times uniform noise in [0.9, 1.1], negated and scaled by ``inh`` for inhibitory sources, then the
    weight rules, rounding and clipping to [-wc, wc]. Delays are distance / conduction_velocity, clipped to [1, 31].

    Params (each a Param; nested guidance values may themselves be Params, e.g. a Gene):
        projections: list of "src->dst" strings (also "src,dst", "src:dst") or [src, dst] pairs. If absent, the
            projections are the keys (or src/dst entries) of ``guidance``. An explicit empty list is the neutral
            no-op. Missing both ``projections`` and ``guidance`` raises ValueError.
        guidance: per-projection genes, either a dict keyed "src->dst" or a list of dicts with "src"/"dst" (or
            "source"/"target") plus the genes; a single flat gene dict applies to every listed projection.
            Each listed projection must have an entry, else ValueError. Keys:
                B: 3x3 matrix mapping the centred local source position to target logits (default identity).
                c: 3-vector shift of the target logits (default 0).
                sigma: width of the connection kernel, in local box units [0, 1] (default 0.1).
                p0: peak connection probability (default 0, i.e. no synapses).
                w: mean weight, toolbox current units (default 1).
                wc: weight clip, overrides ``w_clip``; inh: inhibitory factor, overrides ``inh_weight_factor``.
                rules_shift / rules_target / rules_probability / rules_weight: per-projection rule lists.
                plus the genes read by the rules (type_c, type_s, topographic, lamina, source, receptor, ...).
        rules_shift, rules_target, rules_probability, rules_weight: rule names from ``RULES`` (default none).
        conduction_velocity: space units per tick (1 tick = 1 ms), default 1.
        max_delay: ticks, default 31 (kernel maximum; larger values are capped and clipped delays warned).
        w_clip: integer weight clip, default 512. inh_weight_factor: default 1.
        exact: dense Ns x Nd probabilities (default True); False uses the sparse candidate search.
        region_map: name -> region id, for projections written with region names (an unknown name raises).
        bounds_min, bounds_size: per projection end name, box origin and size in space units; otherwise the
            population's bounding box defines its local coordinates.
        identities: per source name, identity per source cell (else cell_type or argmax expression).

    A projection whose source or destination region has no alive cells is a no-op for that projection (an empty
    population is legitimate); a tissue with no alive cells is returned unchanged.

    No dense Ns x Nd arrays except when exact=True below documented threshold (max(Ns, Nd) <= 2048).
    """
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> tuple[int, int]:
        return (N * 64, N * 100)
    
    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if not tissue.alive.any():
            return tissue
            
        projections_param = resolve(params.get("projections"), genome, fields)
        guidance_param = resolve(params.get("guidance"), genome, fields)

        projections: List[Tuple[Any, Any]] = []
        if projections_param is not None:
            for p in projections_param:
                parsed = _normalize_proj_key(p) if isinstance(p, str) else None
                if parsed is None and isinstance(p, (list, tuple)) and len(p) == 2:
                    parsed = (p[0], p[1])
                if parsed is None:
                    raise ValueError(f"grow_axons: cannot parse projection {p!r}; use 'src->dst' or [src, dst]")
                projections.append(parsed)
            if not projections:
                return tissue
        elif isinstance(guidance_param, dict) and guidance_param:
            for k in guidance_param.keys():
                parsed = _normalize_proj_key(k)
                if parsed is None:
                    raise ValueError(f"grow_axons: guidance key {k!r} is not a projection; use 'src->dst' keys "
                                     f"or give 'projections'")
                projections.append(parsed)
        elif isinstance(guidance_param, list) and guidance_param:
            for item in guidance_param:
                item_src = item.get("src", item.get("source")) if isinstance(item, dict) else None
                item_dst = item.get("dst", item.get("target")) if isinstance(item, dict) else None
                if item_src is None or item_dst is None:
                    raise ValueError(f"grow_axons: guidance entry {item!r} needs 'src' and 'dst'")
                projections.append((item_src, item_dst))
        else:
            raise ValueError("grow_axons: no projections given; set 'projections' (an empty list is a no-op) "
                             "or 'guidance' keyed by 'src->dst'")
            
        shift_rules = resolve(params.get("rules_shift", []), genome, fields)
        target_rules = resolve(params.get("rules_target", []), genome, fields)
        prob_rules = resolve(params.get("rules_probability", []), genome, fields)
        weight_rules = resolve(params.get("rules_weight", []), genome, fields)
        
        cv = resolve(params.get("conduction_velocity", 1.0), genome, fields)
        max_delay = resolve(params.get("max_delay", 31), genome, fields)
        global_w_clip = int(resolve(params.get("w_clip", 512), genome, fields))
        global_inh = float(resolve(params.get("inh_weight_factor", 1.0), genome, fields))
        exact = bool(resolve(params.get("exact", True), genome, fields))
        
        region_map = resolve(params.get("region_map", {}), genome, fields)
        bounds_min = resolve(params.get("bounds_min", {}), genome, fields)
        bounds_size = resolve(params.get("bounds_size", {}), genome, fields)

        new_pre_list = []
        new_post_list = []
        new_weight_list = []
        new_delay_list = []
        total_clipped_delays = 0
        effective_max_delay = min(int(max_delay), 31)
        
        alive_idx = np.nonzero(tissue.alive)[0]
        region_ids = tissue.region[alive_idx]
        
        for p in projections:
            src_str, dst_str = p[0], p[1]
            src_reg = region_map.get(src_str, src_str) if isinstance(src_str, str) else src_str
            dst_reg = region_map.get(dst_str, dst_str) if isinstance(dst_str, str) else dst_str
            
            try:
                src_mask = region_ids == int(src_reg)
                dst_mask = region_ids == int(dst_reg)
            except (ValueError, TypeError):
                raise ValueError(f"grow_axons: projection {src_str!r}->{dst_str!r} does not name region ids; "
                                 f"use integer regions or add the names to 'region_map'") from None

            gd = _get_guidance(guidance_param, src_str, dst_str)
            if not isinstance(gd, dict):
                raise ValueError(f"grow_axons: no guidance dict for projection {src_str!r}->{dst_str!r}; add it to "
                                 f"the 'guidance' param (keys: B, c, sigma, p0, w, ...)")

            src_indices = alive_idx[src_mask]
            dst_indices = alive_idx[dst_mask]
            
            if len(src_indices) == 0 or len(dst_indices) == 0:
                continue

            gd = {k: resolve(v, genome, fields) for k, v in gd.items()}
            
            # Local positions
            if src_str in bounds_min and src_str in bounds_size:
                local_src = (tissue.positions[src_indices] - bounds_min[src_str]) / bounds_size[src_str]
            else:
                s_min = np.min(tissue.positions[src_indices], axis=0)
                s_max = np.max(tissue.positions[src_indices], axis=0)
                s_size = np.maximum(s_max - s_min, 1e-9)
                local_src = (tissue.positions[src_indices] - s_min) / s_size
                
            if dst_str in bounds_min and dst_str in bounds_size:
                local_dst = (tissue.positions[dst_indices] - bounds_min[dst_str]) / bounds_size[dst_str]
            else:
                d_min = np.min(tissue.positions[dst_indices], axis=0)
                d_max = np.max(tissue.positions[dst_indices], axis=0)
                d_size = np.maximum(d_max - d_min, 1e-9)
                local_dst = (tissue.positions[dst_indices] - d_min) / d_size

            inhibitory_src = (tissue.sign[src_indices] < 0)
            
            ident_src = resolve(params.get("identities", {}), genome, fields).get(src_str)
            if ident_src is not None:
                ident_src = ident_src[src_mask]
            else:
                if np.any(tissue.cell_type[src_indices] > 0):
                    ident_src = tissue.cell_type[src_indices]
                elif tissue.expression.shape[1] > 0:
                    ident_src = np.argmax(tissue.expression[src_indices], axis=1)

            ctx = GuidanceContext(str(src_str), str(dst_str), local_src, local_dst, inhibitory_src, ident_src, gd)
            if hasattr(tissue, "expression") and tissue.expression.shape[1] > 0:
                ctx.expression_src = tissue.expression[src_indices]
                ctx.expression_dst = tissue.expression[dst_indices]

            ctx.shift = np.asarray(gd.get("c", np.zeros(3)), dtype=float)
            
            p_shift_rules = gd.get("rules_shift", shift_rules)
            for r in p_shift_rules:
                if r in RULES["shift"]:
                    RULES["shift"][r](ctx)
                else:
                    raise ValueError(f"Unknown shift rule: {r!r}")
                
            B = np.asarray(gd.get("B", np.eye(3)), dtype=float)
            ctx.target = _sigmoid(4.0 * (local_src - 0.5) @ B.T + ctx.shift)
            
            p_target_rules = gd.get("rules_target", target_rules)
            for r in p_target_rules:
                if r in RULES["target"]:
                    RULES["target"][r](ctx)
                else:
                    raise ValueError(f"Unknown target rule: {r!r}")
                
            sigma = float(gd.get("sigma", 0.1))
            p0 = float(gd.get("p0", 0.0))
            w_mean = float(gd.get("w", 1.0))
            wc = int(gd.get("wc", global_w_clip))
            inh = float(gd.get("inh", global_inh))
            
            p_prob_rules = gd.get("rules_probability", prob_rules)

            if exact or sigma > 1.0:
                d2 = ((local_dst[None, :, :] - ctx.target[:, None, :]) ** 2).sum(-1)
                ctx.p = p0 * np.exp(-d2 / (2 * sigma ** 2))
                
                for r in p_prob_rules:
                    if r in RULES["probability"]:
                        RULES["probability"][r](ctx)
                    else:
                        raise ValueError(f"Unknown probability rule: {r!r}")
                    
                p_ij = ctx.p
                edges_pre, edges_post = np.nonzero(rng.random(p_ij.shape) < p_ij)
            else:
                edges_pre, edges_post, _ = sparse_guidance(
                    ctx, _PlanRulesAdapter(p_prob_rules), rng, c=5.0, exact=False
                )

            if len(edges_pre) == 0:
                continue
                
            # Vectorized weight calculation without Python loops over synapses
            inh_factors = np.where(inhibitory_src[edges_pre], -inh, 1.0)
            noise = 0.9 + 0.2 * rng.random(len(edges_pre))
            ws = (w_mean * inh_factors * noise).astype(float)
            wctx = WeightContext(str(src_str), str(dst_str), edges_pre, edges_post, ws, gd)
            
            p_weight_rules = gd.get("rules_weight", weight_rules)
            for r in p_weight_rules:
                if r in RULES["weight"]:
                    RULES["weight"][r](wctx)
                else:
                    raise ValueError(f"Unknown weight rule: {r!r}")
                
            final_ws = np.clip(np.round(wctx.w), -wc, wc).astype(np.int32)
            
            abs_src = tissue.positions[src_indices[edges_pre]]
            abs_dst = tissue.positions[dst_indices[edges_post]]
            dists = np.linalg.norm(abs_src - abs_dst, axis=1)
            raw_delays = np.round(dists / cv).astype(np.int32)
            n_clipped = int(np.sum(raw_delays > 31))
            total_clipped_delays += n_clipped
            delays = np.clip(raw_delays, 1, effective_max_delay).astype(np.int32)
            
            new_pre_list.append(src_indices[edges_pre])
            new_post_list.append(dst_indices[edges_post])
            new_weight_list.append(final_ws)
            new_delay_list.append(delays)
            
        if total_clipped_delays > 0:
            warnings.warn(
                f"grow_axons: {total_clipped_delays} synapses clipped to maximum delay 31 ticks (kernel limit)",
                UserWarning,
                stacklevel=2
            )

        if new_pre_list:
            final_pre = np.concatenate([tissue.connectivity.pre] + new_pre_list)
            final_post = np.concatenate([tissue.connectivity.post] + new_post_list)
            final_w = np.concatenate([tissue.connectivity.weight] + new_weight_list)
            final_delay = np.concatenate([tissue.connectivity.delay] + new_delay_list)
            tissue.connectivity = SparseConnectivity(final_pre, final_post, final_w, final_delay)

        return tissue

@register_stage("place_by_hand")
class PlaceByHand:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> tuple[int, int]:
        return (N * 64, N * 10)
        
    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        pos = np.asarray(resolve(params.get("positions", []), genome, fields))
        if len(pos) == 0:
            return tissue
        
        region = resolve(params.get("region", 0), genome, fields)
        if isinstance(region, (int, float)):
            region = np.full(len(pos), int(region), dtype=np.int32)
        else:
            region = np.asarray(region, dtype=np.int32)
            
        kwargs = {"positions": pos, "region": region}
        
        for k in ["cell_type", "birth_stage", "sign", "mode", "shift_v", "shift_s", "base_weight", "threshold", "directions"]:
            val = resolve(params.get(k), genome, fields)
            if val is not None:
                if isinstance(val, (int, float, np.integer, np.floating)):
                    kwargs[k] = np.full(len(pos), val)
                else:
                    kwargs[k] = np.asarray(val)
                    
        tissue.add_cells(len(pos), **kwargs)
        return tissue

@register_stage("connect_by_hand")
class ConnectByHand:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> tuple[int, int]:
        return (N * 32, N * 10)
        
    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        pre = np.asarray(resolve(params.get("pre", []), genome, fields), dtype=np.int32)
        post = np.asarray(resolve(params.get("post", []), genome, fields), dtype=np.int32)
        
        if len(pre) == 0 or len(post) == 0:
            return tissue
            
        N = len(tissue.alive)
        if np.any(pre < 0) or np.any(pre >= N):
            raise ValueError(f"connect_by_hand: pre index out of range [0, {N - 1}]")
        if np.any(post < 0) or np.any(post >= N):
            raise ValueError(f"connect_by_hand: post index out of range [0, {N - 1}]")

        weight = resolve(params.get("weight", 1.0), genome, fields)
        if isinstance(weight, (int, float)):
            weight = np.full(len(pre), int(weight), dtype=np.int32)
        else:
            weight = np.asarray(weight, dtype=np.int32)
            
        delay = resolve(params.get("delay", 1.0), genome, fields)
        if isinstance(delay, (int, float)):
            delay = np.full(len(pre), int(delay), dtype=np.int32)
        else:
            delay = np.asarray(delay, dtype=np.int32)
            
        if np.any(delay < 1) or np.any(delay > 31):
            raise ValueError(f"connect_by_hand: delay out of kernel limit [1, 31]: range [{np.min(delay)}, {np.max(delay)}]")

        new_pre = np.concatenate([tissue.connectivity.pre, pre])
        new_post = np.concatenate([tissue.connectivity.post, post])
        new_weight = np.concatenate([tissue.connectivity.weight, weight])
        new_delay = np.concatenate([tissue.connectivity.delay, delay])
        
        tissue.connectivity = SparseConnectivity(new_pre, new_post, new_weight, new_delay)
        return tissue
