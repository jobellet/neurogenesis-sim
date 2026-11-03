"""Chunked and streaming growth (D4): axon growth for tissues whose synapses do not fit in memory.

`grow_axons_streaming` runs the `grow_axons` guidance rules over chunks of `chunk_size` source cells, with a
`CellList` over targets, and writes each chunk's synapses to an `.npz` shard; `SynapseShardManifest` lists the shards
(JSON). `assemble_shards` concatenates them into one `SparseConnectivity`, `stream_stats` summarises weights, delays
and out-degrees shard by shard, and `streaming_growth_cost` declares the peak memory (O(N) plus one chunk, independent
of E) and operations.
"""
import json
import hashlib
import warnings
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, Union, Iterator, List, Optional, Tuple

import numpy as np
from neurogenesis.tissue import effective_max_delay as effective_max_delay_

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.params import resolve
from neurogenesis.spatial import CellList
from neurogenesis.development.rules import RULES, GuidanceContext, WeightContext
from neurogenesis.stages.connectivity import (
    _normalize_proj_key,
    _get_guidance,
    _sigmoid
)


@dataclass
class SynapseShardManifest:
    directory: Path
    num_neurons: int
    num_synapses: int
    shards: List[dict]
    seed: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d['directory'] = str(d['directory'])
        return d

    def save(self, path: Union[str, Path]) -> None:
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Union[str, Path]) -> 'SynapseShardManifest':
        with open(path, 'r') as f:
            d = json.load(f)
        d['directory'] = Path(d['directory'])
        return cls(**d)

    def iter_shards(self) -> Iterator[SparseConnectivity]:
        for shard_meta in self.shards:
            filepath = self.directory / shard_meta['file']
            data = np.load(filepath)
            yield SparseConnectivity(
                pre=data['pre'],
                post=data['post'],
                weight=data['weight'],
                delay=data['delay']
            )


def assemble_shards(manifest: Union[SynapseShardManifest, str, Path]) -> SparseConnectivity:
    if not isinstance(manifest, SynapseShardManifest):
        manifest = SynapseShardManifest.load(manifest)

    pre_list, post_list, weight_list, delay_list = [], [], [], []
    for shard in manifest.iter_shards():
        pre_list.append(shard.pre)
        post_list.append(shard.post)
        weight_list.append(shard.weight)
        delay_list.append(shard.delay)

    if not pre_list:
        return SparseConnectivity.empty()

    c = SparseConnectivity(
        pre=np.concatenate(pre_list),
        post=np.concatenate(post_list),
        weight=np.concatenate(weight_list),
        delay=np.concatenate(delay_list)
    )
    return c


def stream_stats(manifest: Union[SynapseShardManifest, str, Path]) -> dict:
    if not isinstance(manifest, SynapseShardManifest):
        manifest = SynapseShardManifest.load(manifest)

    total_synapses = 0
    weight_min = float('inf')
    weight_max = float('-inf')
    weight_sum = 0.0

    delay_min = float('inf')
    delay_max = float('-inf')
    delay_sum = 0.0

    out_degree = np.zeros(manifest.num_neurons, dtype=np.int64)

    for shard in manifest.iter_shards():
        if len(shard.pre) == 0:
            continue

        total_synapses += len(shard.pre)

        w = shard.weight
        weight_min = min(weight_min, float(np.min(w)))
        weight_max = max(weight_max, float(np.max(w)))
        weight_sum += float(np.sum(w))

        d = shard.delay
        delay_min = min(delay_min, float(np.min(d)))
        delay_max = max(delay_max, float(np.max(d)))
        delay_sum += float(np.sum(d))

        counts = np.bincount(shard.pre, minlength=manifest.num_neurons)
        if len(counts) > len(out_degree):
            out_degree = np.pad(out_degree, (0, len(counts) - len(out_degree)))
        out_degree[:len(counts)] += counts

    if total_synapses == 0:
        return {
            "total_synapses": 0,
            "weight_mean": 0.0, "weight_min": 0.0, "weight_max": 0.0,
            "delay_mean": 0.0, "delay_min": 0.0, "delay_max": 0.0,
            "out_degree_histogram": out_degree.tolist()
        }

    # Histogram of out-degrees: indices are degree sizes, values are counts of neurons
    histogram = np.bincount(out_degree)

    return {
        "total_synapses": total_synapses,
        "weight_mean": weight_sum / total_synapses,
        "weight_min": weight_min,
        "weight_max": weight_max,
        "delay_mean": delay_sum / total_synapses,
        "delay_min": delay_min,
        "delay_max": delay_max,
        "out_degree_histogram": histogram.tolist()
    }


def grow_axons_streaming(
    tissue: Tissue,
    params: dict,
    genome: dict,
    fields: dict,
    rng: np.random.Generator,
    out_dir: Union[str, Path],
    chunk_size: int = 1024
) -> SynapseShardManifest:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not tissue.alive.any():
        return SynapseShardManifest(out_dir, len(tissue.alive), 0, [], 0)

    projections_param = resolve(params.get("projections"), genome, fields)
    guidance_param = resolve(params.get("guidance"), genome, fields)

    projections: List[Tuple[Any, Any]] = []
    if projections_param is not None and isinstance(projections_param, list):
        for p in projections_param:
            parsed = _normalize_proj_key(p) if isinstance(p, str) else None
            if parsed is None and isinstance(p, (list, tuple)) and len(p) == 2:
                parsed = (p[0], p[1])
            if parsed is None:
                raise ValueError(f"grow_axons_streaming: cannot parse projection {p!r}")
            projections.append(parsed)
        if not projections:
            return SynapseShardManifest(out_dir, len(tissue.alive), 0, [], 0)
    elif isinstance(guidance_param, dict) and guidance_param:
        for k in guidance_param.keys():
            parsed = _normalize_proj_key(k)
            if parsed is None:
                raise ValueError(f"grow_axons_streaming: guidance key {k!r} is not a projection")
            projections.append(parsed)
    elif isinstance(guidance_param, list) and guidance_param:
        for item in guidance_param:
            item_src = item.get("src", item.get("source")) if isinstance(item, dict) else None
            item_dst = item.get("dst", item.get("target")) if isinstance(item, dict) else None
            if item_src is None or item_dst is None:
                raise ValueError(f"grow_axons_streaming: guidance entry {item!r} needs 'src' and 'dst'")
            projections.append((item_src, item_dst))
    else:
        raise ValueError("grow_axons_streaming: no projections given")

    shift_rules = resolve(params.get("rules_shift", []), genome, fields)
    target_rules = resolve(params.get("rules_target", []), genome, fields)
    prob_rules = resolve(params.get("rules_probability", []), genome, fields)
    weight_rules = resolve(params.get("rules_weight", []), genome, fields)

    cv = resolve(params.get("conduction_velocity", 1.0), genome, fields)
    max_delay = resolve(params.get("max_delay"), genome, fields)
    global_w_clip = int(resolve(params.get("w_clip", 512), genome, fields))  # type: ignore
    global_inh = float(resolve(params.get("inh_weight_factor", 1.0), genome, fields))  # type: ignore
    exact = resolve(params.get("exact"), genome, fields)

    region_map = resolve(params.get("region_map", {}), genome, fields)
    if not isinstance(region_map, dict): region_map = {}
    bounds_min = resolve(params.get("bounds_min", {}), genome, fields)
    if not isinstance(bounds_min, dict): bounds_min = {}
    bounds_size = resolve(params.get("bounds_size", {}), genome, fields)
    if not isinstance(bounds_size, dict): bounds_size = {}

    effective_max_delay = effective_max_delay_(max_delay)

    alive_idx = np.nonzero(tissue.alive)[0]
    region_ids = tissue.region[alive_idx]

    total_synapses = 0
    shards_meta = []
    shard_idx = 0
    total_clipped_delays = 0

    for p in projections:
        src_str, dst_str = p[0], p[1]
        src_reg = region_map.get(src_str, src_str) if isinstance(src_str, str) else src_str
        dst_reg = region_map.get(dst_str, dst_str) if isinstance(dst_str, str) else dst_str

        try:
            src_mask = region_ids == int(src_reg)
            dst_mask = region_ids == int(dst_reg)
        except (ValueError, TypeError):
            raise ValueError(f"grow_axons_streaming: projection {src_str!r}->{dst_str!r} does not name region ids")

        gd = _get_guidance(guidance_param, src_str, dst_str)
        if not isinstance(gd, dict):
            raise ValueError(f"grow_axons_streaming: no guidance dict for projection {src_str!r}->{dst_str!r}")

        src_indices = alive_idx[src_mask]
        dst_indices = alive_idx[dst_mask]

        if len(src_indices) == 0 or len(dst_indices) == 0:
            continue

        gd = {k: resolve(v, genome, fields) for k, v in gd.items()}

        if dst_str in bounds_min and dst_str in bounds_size:
            local_dst_full = (tissue.positions[dst_indices] - bounds_min[dst_str]) / bounds_size[dst_str]
        else:
            d_min = np.min(tissue.positions[dst_indices], axis=0)
            d_max = np.max(tissue.positions[dst_indices], axis=0)
            d_size = np.maximum(d_max - d_min, 1e-9)
            local_dst_full = (tissue.positions[dst_indices] - d_min) / d_size

        sigma = float(gd.get("sigma", 0.1))
        p0 = float(gd.get("p0", 0.0))
        w_mean = float(gd.get("w", 1.0))
        wc = int(gd.get("wc", global_w_clip))
        inh = float(gd.get("inh", global_inh))

        p_shift_rules = gd.get("rules_shift", shift_rules)
        p_target_rules = gd.get("rules_target", target_rules)
        p_prob_rules = gd.get("rules_probability", prob_rules)
        p_weight_rules = gd.get("rules_weight", weight_rules)

        B = np.asarray(gd.get("B", np.eye(3)), dtype=float)
        shift_vec = np.asarray(gd.get("c", np.zeros(3)), dtype=float)

        dense = bool(exact)
        cl = None
        if not dense:
            radius = 5.0 * sigma
            cl = CellList(local_dst_full, cutoff=radius)

        for i in range(0, len(src_indices), chunk_size):
            chunk_src_indices = src_indices[i:i + chunk_size]

            if src_str in bounds_min and src_str in bounds_size:
                local_src = (tissue.positions[chunk_src_indices] - bounds_min[src_str]) / bounds_size[src_str]
            else:
                s_min = np.min(tissue.positions[src_indices], axis=0)
                s_max = np.max(tissue.positions[src_indices], axis=0)
                s_size = np.maximum(s_max - s_min, 1e-9)
                local_src = (tissue.positions[chunk_src_indices] - s_min) / s_size

            inhibitory_src = (tissue.sign[chunk_src_indices] < 0)

            identities_param = resolve(params.get("identities", {}), genome, fields)
            ident_src_full = identities_param.get(src_str) if isinstance(identities_param, dict) else None
            if ident_src_full is not None:
                ident_src = ident_src_full[src_mask][i:i + chunk_size]
            else:
                if np.any(tissue.cell_type[chunk_src_indices] > 0):
                    ident_src = tissue.cell_type[chunk_src_indices]
                elif hasattr(tissue, "expression") and tissue.expression.shape[1] > 0:
                    ident_src = np.argmax(tissue.expression[chunk_src_indices], axis=1)
                else:
                    ident_src = None

            ctx = GuidanceContext(str(src_str), str(dst_str), local_src, local_dst_full, inhibitory_src, ident_src, gd)
            if hasattr(tissue, "expression") and tissue.expression.shape[1] > 0:
                ctx.expression_src = tissue.expression[chunk_src_indices]  # type: ignore
                ctx.expression_dst = tissue.expression[dst_indices]  # type: ignore

            ctx.shift = shift_vec

            for r in p_shift_rules:
                if r in RULES["shift"]:
                    RULES["shift"][r](ctx)
                else:
                    raise ValueError(f"Unknown shift rule: {r!r}")

            ctx.target = _sigmoid(4.0 * (local_src - 0.5) @ B.T + ctx.shift)

            for r in p_target_rules:
                if r in RULES["target"]:
                    RULES["target"][r](ctx)
                else:
                    raise ValueError(f"Unknown target rule: {r!r}")

            if dense:
                d2 = ((local_dst_full[None, :, :] - ctx.target[:, None, :]) ** 2).sum(-1)
                ctx.p = p0 * np.exp(-d2 / (2 * sigma ** 2))
                for r in p_prob_rules:
                    if r in RULES["probability"]:
                        RULES["probability"][r](ctx)
                    else:
                        raise ValueError(f"Unknown probability rule: {r!r}")

                p_ij = ctx.p
                edges_pre, edges_post = np.nonzero(rng.random(p_ij.shape) < p_ij)
            else:
                assert cl is not None
                pre_idx, post_idx, dists = cl.query_radius(ctx.target, radius, return_distances=True)
                if len(pre_idx) == 0:
                    continue
                p_sparse = p0 * np.exp(-(dists ** 2) / (2 * sigma ** 2))

                for r in p_prob_rules:
                    if r == "identity_expression":
                        if ctx.identity_src is not None and "type_s" in ctx.gd:
                            factor = np.clip(np.asarray(ctx.gd["type_s"], float)[ctx.identity_src], 0.0, 1.0)
                            p_sparse = p_sparse * factor[pre_idx]
                    elif r == "no_autapse":
                        if ctx.src == ctx.dst:
                            global_pre = chunk_src_indices[pre_idx]
                            global_post = dst_indices[post_idx]
                            mask = global_pre != global_post
                            pre_idx = pre_idx[mask]
                            post_idx = post_idx[mask]
                            p_sparse = p_sparse[mask]
                    elif r == "source_sign":
                        if ctx.gd.get("source") in ("exc", "inh"):
                            is_inh = (ctx.gd["source"] == "inh")
                            mask = (ctx.inhibitory_src[pre_idx] == is_inh)
                            p_sparse = p_sparse * mask
                    elif r in RULES["probability"]:
                        raise NotImplementedError(f"Probability rule '{r}' is not supported in streaming sparse guidance.")
                    else:
                        raise ValueError(f"Unknown probability rule: {r!r}")

                formed = rng.random(len(p_sparse)) < p_sparse
                edges_pre = pre_idx[formed]
                edges_post = post_idx[formed]

            if len(edges_pre) == 0:
                continue

            inh_factors = np.where(inhibitory_src[edges_pre], -inh, 1.0)
            noise = 0.9 + 0.2 * rng.random(len(edges_pre))
            ws = (w_mean * inh_factors * noise).astype(float)
            wctx = WeightContext(str(src_str), str(dst_str), edges_pre, edges_post, ws, gd)

            for r in p_weight_rules:
                if r in RULES["weight"]:
                    RULES["weight"][r](wctx)
                else:
                    raise ValueError(f"Unknown weight rule: {r!r}")

            final_ws = np.clip(np.round(wctx.w), -wc, wc).astype(np.int32)

            abs_src = tissue.positions[chunk_src_indices[edges_pre]]
            abs_dst = tissue.positions[dst_indices[edges_post]]
            dists_abs = np.linalg.norm(abs_src - abs_dst, axis=1)
            raw_delays = np.round(dists_abs / cv).astype(np.int32)  # type: ignore
            n_clipped = int(np.sum(raw_delays > effective_max_delay))
            total_clipped_delays += n_clipped
            delays = np.clip(raw_delays, 1, effective_max_delay).astype(np.int32)

            global_pre = chunk_src_indices[edges_pre]
            global_post = dst_indices[edges_post]

            filename = f"shard_{shard_idx:05d}.npz"
            filepath = out_dir / filename
            np.savez_compressed(
                filepath,
                pre=global_pre,
                post=global_post,
                weight=final_ws,
                delay=delays
            )

            with open(filepath, "rb") as f:
                sha256_hash = hashlib.sha256(f.read()).hexdigest()

            num_syn = len(global_pre)
            shards_meta.append({
                "file": filename,
                "num_synapses": num_syn,
                "min_pre": int(np.min(global_pre)),
                "max_pre": int(np.max(global_pre)),
                "sha256": sha256_hash
            })

            total_synapses += num_syn
            shard_idx += 1

    if total_clipped_delays > 0:
        warnings.warn(
            f"grow_axons_streaming: {total_clipped_delays} synapses clipped to maximum delay {effective_max_delay} ticks",
            UserWarning,
            stacklevel=2
        )

    manifest = SynapseShardManifest(
        directory=out_dir,
        num_neurons=len(tissue.alive),
        num_synapses=total_synapses,
        shards=shards_meta,
        seed=0
    )
    return manifest


def streaming_growth_cost(N: int, E: int, params: dict, chunk_size: int = 1024) -> dict:
    """Declare peak working memory and operations for chunked streaming axon growth.

    Peak memory is bounded by the target CellList O(N) plus one chunk's candidates
    O(chunk_size * k_max), independent of total synapse count E written to disk.
    """
    n_proj = max(1, len(params.get("projections", [1])))
    k_est = min(max(1, N), 64)
    active_chunk = min(max(1, N), chunk_size)
    return {
        "bytes": int(N * 32 + active_chunk * k_est * 24),
        "ops": int(n_proj * max(1, N) * k_est * 20),
    }

