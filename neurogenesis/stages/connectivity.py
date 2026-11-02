from __future__ import annotations

import warnings
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Union

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.params import Param, resolve, worst_case
from neurogenesis.stages.base import register_stage
from neurogenesis.development.rules import RULES, GuidanceContext, WeightContext
from neurogenesis.development.sparse_guidance import sparse_guidance
from neurogenesis.spatial import CHUNK_PAIRS, _BYTES_PER_PAIR, CellList
from neurogenesis.expressions import eval_expr

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


# Largest population (max(Ns, Nd)) for which the default dense Ns x Nd probability path is used, and largest number
# of pairs Ns * Nd that exact=True may allocate (each dense pass holds a few float64 Ns x Nd x 3 temporaries).
DENSE_MAX_CELLS = 2048
EXACT_MAX_PAIRS = 1 << 24


# Declared cost of grow_axons: bytes and operations per cell, per (source, destination) pair on the dense path (float64
# Ns x Nd x 3 difference, distances, probabilities, uniform draws; measured peak 32 B per pair), and per sparse candidate pair within
# 5 sigma (cell-list output, distances, probabilities, draws).
_CELL_BYTES, _CELL_OPS = 256, 100
_DENSE_PAIR_BYTES, _DENSE_PAIR_OPS = 32, 30
_SPARSE_PAIR_BYTES, _SPARSE_PAIR_OPS = 48, 20


def _cost_projections(params: Dict[str, Param]) -> Tuple[int, bool, List[float]]:
    """Worst-case view of grow_axons params for its cost: number of projections, whether every projection joins two
    different ends (then Ns + Nd <= N), and the sigma upper bounds found in the guidance (default 0.1)."""
    guidance = worst_case(params.get("guidance"), None)
    entries = []
    if isinstance(guidance, dict):
        entries = [(k, v) for k, v in guidance.items() if isinstance(v, dict)] or [(None, guidance)]
    elif isinstance(guidance, list):
        entries = [((g.get("src", g.get("source")), g.get("dst", g.get("target"))), g)
                   for g in guidance if isinstance(g, dict)]
    projections = worst_case(params.get("projections"), None)
    if isinstance(projections, (list, tuple)):
        keys = list(projections)
    else:
        keys = [k for k, _ in entries]
    pairs = [_normalize_proj_key(k) if isinstance(k, str) else (tuple(k) if isinstance(k, (list, tuple))
             and len(k) == 2 else None) for k in keys]
    region_map = worst_case(params.get("region_map"), None)
    rmap = region_map if isinstance(region_map, dict) else {}

    def _res(end: Any) -> str:
        if end in rmap:
            return str(rmap[end])
        if str(end) in rmap:
            return str(rmap[str(end)])
        return str(end)

    distinct = bool(pairs) and all(p is not None and _res(p[0]) != _res(p[1]) for p in pairs)
    sigmas = [float(worst_case(g.get("sigma"), 0.1)) for _, g in entries] or [0.1]
    return max(1, len(keys)), distinct, sigmas


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
        exact: unset (default): dense Ns x Nd probabilities when max(Ns, Nd) <= DENSE_MAX_CELLS (2048), else the
            sparse cell-list candidate search (radius 5 sigma; only the identity_expression, no_autapse and source_sign
            probability rules). True: always dense, ValueError if Ns * Nd > EXACT_MAX_PAIRS (2^24). False: always sparse
            (except sigma > 1 below DENSE_MAX_CELLS, where the kernel covers the whole box and dense is used).
        region_map: name -> region id, for projections written with region names (an unknown name raises).
        bounds_min, bounds_size: per projection end name, box origin and size in space units; otherwise the
            population's bounding box defines its local coordinates.
        identities: per source name, identity per source cell (else cell_type or argmax expression).

    A projection whose source or destination region has no alive cells is a no-op for that projection (an empty
    population is legitimate); a tissue with no alive cells is returned unchanged.

    No dense Ns x Nd arrays except below max(Ns, Nd) <= 2048, or with exact=True below Ns * Nd <= 2^24.
    """
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> tuple[int, int]:
        """Cost of the largest projection, taken as Ns = Nd = N / 2 when every projection joins two different ends,
        else N: below DENSE_MAX_CELLS cells per side (or with exact=True) the dense path holds all Ns x Nd pairs,
        above it the sparse path holds the pairs within 5 sigma (a fraction 4/3 pi (5 sigma)^3 of the unit box,
        sigma the largest upper bound in the guidance) plus one cell-list chunk. Memory is that of one projection,
        operations the sum over projections."""
        n_proj, distinct, sigmas = _cost_projections(params)
        exact = worst_case(params.get("exact"), None)
        side = N // 2 if distinct else N
        sigma = max(sigmas)
        if exact or (side <= DENSE_MAX_CELLS and (exact is None or sigma > 1.0)):
            pairs = min(side * side, EXACT_MAX_PAIRS) if exact else side * side
            nbytes, ops = pairs * _DENSE_PAIR_BYTES, pairs * _DENSE_PAIR_OPS
        else:
            pairs = int(side * side * min(1.0, 4.0 / 3.0 * np.pi * (5.0 * sigma) ** 3))
            nbytes, ops = pairs * _SPARSE_PAIR_BYTES + CHUNK_PAIRS * _BYTES_PER_PAIR, pairs * _SPARSE_PAIR_OPS
        return int(N * _CELL_BYTES + nbytes), int(N * _CELL_OPS + n_proj * ops)

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
        exact = resolve(params.get("exact"), genome, fields)
        
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

            n_src, n_dst = len(src_indices), len(dst_indices)
            if exact:
                if n_src * n_dst > EXACT_MAX_PAIRS:
                    raise ValueError(f"grow_axons: exact=True for {src_str!r}->{dst_str!r} needs {n_src} x {n_dst} "
                                     f"dense pairs, above the limit {EXACT_MAX_PAIRS}; leave 'exact' unset to use the "
                                     f"sparse candidate search")
                dense = True
            else:
                dense = max(n_src, n_dst) <= DENSE_MAX_CELLS and (exact is None or sigma > 1.0)
            if dense:
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
            c = tissue.connectivity
            tissue.connectivity = SparseConnectivity.concat([c, SparseConnectivity(
                np.concatenate(new_pre_list), np.concatenate(new_post_list), np.concatenate(new_weight_list),
                np.concatenate(new_delay_list))])
            for k, ref in (("pre", c.pre), ("post", c.post), ("weight", c.weight), ("delay", c.delay)):
                setattr(tissue.connectivity, k, getattr(tissue.connectivity, k).astype(ref.dtype, copy=False))

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

# Mean synapses per cell assumed by the connect_by_hand cost for connection rules.
_RULE_MEAN_SYNAPSES = 100
# Largest N for which connect_by_hand accepts a dense N x N connection matrix.
DENSE_MATRIX_MAX_CELLS = 2048


def _select_cells(tissue: Tissue, selector: Any) -> np.ndarray:
    """Indices of the living cells a rule side selects: None (all), a dict of `region` / `cell_type` values (ints or
    lists, all keys must match), or a boolean expression over `cell_type`, `region`, `birth_stage`, `generation`,
    `sign`, `x`, `y`, `z` (restricted evaluator)."""
    mask = tissue.alive.copy()
    if selector is None:
        return np.flatnonzero(mask)
    if isinstance(selector, str):
        env = {"cell_type": tissue.cell_type, "region": tissue.region, "birth_stage": tissue.birth_stage,
               "generation": tissue.generation, "sign": tissue.sign, "x": tissue.positions[:, 0],
               "y": tissue.positions[:, 1], "z": tissue.positions[:, 2], "np": np}
        m = np.asarray(eval_expr(selector, env), dtype=bool)
        return np.flatnonzero(mask & np.broadcast_to(m, mask.shape))
    if isinstance(selector, dict):
        for key in ("region", "cell_type"):
            if key in selector:
                mask &= np.isin(getattr(tissue, key), np.asarray(selector[key]).ravel())
        return np.flatnonzero(mask)
    raise ValueError(f"connect_by_hand: invalid cell selector {selector!r}")


def _rule_synapses(tissue: Tissue, rule: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
                   rng: np.random.Generator) -> Tuple[np.ndarray, ...]:
    """(pre, post, weight, delay) of one connection rule; O(E) memory (no Npre x Npost array)."""
    val = lambda k, d: resolve(rule.get(k, d), genome, fields)
    pre_idx = _select_cells(tissue, rule.get("pre"))
    post_idx = _select_cells(tissue, rule.get("post"))
    prob = float(val("prob", 1.0))
    empty = (np.zeros(0, np.int32),) * 4
    if len(pre_idx) == 0 or len(post_idx) == 0 or prob <= 0:
        return empty
    max_d = rule.get("max_distance")
    if max_d is not None:
        r = float(resolve(max_d, genome, fields))
        q, c, d = CellList(tissue.positions[post_idx], r).query_radius(tissue.positions[pre_idx], r, return_distances=True)
        pre, post = pre_idx[q], post_idx[c]
        p = np.full(len(pre), prob)
        if rule.get("sigma") is not None:
            sigma = float(resolve(rule["sigma"], genome, fields))
            p = p * np.exp(-d ** 2 / (2 * sigma ** 2))
        keep = rng.random(len(pre)) < p
        pre, post = pre[keep], post[keep]
    else:
        n_pairs = len(pre_idx) * len(post_idx)
        k = int(rng.binomial(n_pairs, min(prob, 1.0)))
        flat = rng.choice(n_pairs, size=k, replace=False) if k < n_pairs else np.arange(n_pairs)
        flat = np.sort(flat)
        pre, post = pre_idx[flat // len(post_idx)], post_idx[flat % len(post_idx)]
    if not bool(val("allow_autapse", False)):
        keep = pre != post
        pre, post = pre[keep], post[keep]
    E = len(pre)
    w = np.full(E, int(val("weight", 1)), dtype=np.int32)
    if bool(val("dale", False)):
        w = np.abs(w) * np.where(tissue.sign[pre] < 0, -1, 1).astype(np.int32)
    if rule.get("velocity") is not None:
        dist = np.linalg.norm(tissue.positions[post] - tissue.positions[pre], axis=1)
        delay = np.round(dist / float(val("velocity", 1.0))).astype(np.int64)
        n_clip = int(np.sum(delay > 31))
        if n_clip:
            warnings.warn(f"connect_by_hand: {n_clip} synapses clipped to maximum delay 31 ticks (kernel limit)", UserWarning, stacklevel=3)
        delay = np.clip(delay, 1, 31).astype(np.int32)
    else:
        delay = np.full(E, int(val("delay", 1)), dtype=np.int32)
    return pre.astype(np.int32), post.astype(np.int32), w, delay


@register_stage("connect_by_hand")
class ConnectByHand:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> tuple[int, int]:
        b, ops = N * 32, N * 10
        if params.get("matrix") is not None:
            b, ops = b + N * N * 8, ops + N * N
        if params.get("rules"):
            b, ops = b + N * _RULE_MEAN_SYNAPSES * 40, ops + N * _RULE_MEAN_SYNAPSES * 30
        return (b, ops)

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        pre = np.asarray(resolve(params.get("pre", []), genome, fields), dtype=np.int32)
        post = np.asarray(resolve(params.get("post", []), genome, fields), dtype=np.int32)
        if params.get("matrix") is not None:
            self._add_matrix(tissue, params, genome, fields)
        if params.get("rules"):
            rules = resolve(params["rules"], genome, fields)
            for rule in (rules if isinstance(rules, list) else [rules]):
                self._append(tissue, *_rule_synapses(tissue, rule, genome, fields, rng))

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

        self._append(tissue, pre, post, weight, delay)
        return tissue

    @staticmethod
    def _append(tissue: Tissue, pre, post, weight, delay) -> None:
        tissue.connectivity = tissue.connectivity.append(pre, post, weight, delay)

    def _add_matrix(self, tissue, params, genome, fields) -> None:
        """Synapses from a dense N x N weight matrix (row = pre, column = post; 0 = no synapse), N <= 2048."""
        W = np.asarray(resolve(params["matrix"], genome, fields), dtype=np.float64)
        N = len(tissue.alive)
        if W.shape != (N, N):
            raise ValueError(f"connect_by_hand: matrix shape {W.shape} != ({N}, {N})")
        if N > DENSE_MATRIX_MAX_CELLS:
            raise ValueError(f"connect_by_hand: dense matrices are limited to {DENSE_MATRIX_MAX_CELLS} cells; use 'rules' or index lists")
        pre, post = np.nonzero(W)
        D = resolve(params.get("delay_matrix", params.get("delay", 1)), genome, fields)
        D = np.asarray(D, dtype=np.int64)
        delay = D[pre, post] if D.ndim == 2 else np.full(len(pre), int(D), dtype=np.int64)
        if len(delay) and (delay.min() < 1 or delay.max() > 31):
            raise ValueError("connect_by_hand: delay out of kernel limit [1, 31]")
        self._append(tissue, pre, post, np.trunc(W[pre, post]).astype(np.int32), delay)
