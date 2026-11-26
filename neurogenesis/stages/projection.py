"""Sparse random expansion (C28): `random_projection` connects each target cell to `fan_in` source cells drawn at random.

With many targets, a small fan-in and strong shared inhibition among the targets, this is the expansion motif of the
fly mushroom body and the dentate gyrus: each input pattern gets a sparse, high-dimensional code (a "tag" or index).
In the fly it implements a variant of locality-sensitive hashing (Kenyon cells sample ~6 of 50 projection neurons;
Dasgupta, Stevens & Navlakha 2017, Science 358:793-796); in the hippocampus, sparse dentate codes separate similar
patterns before CA3 stores them (Marr 1971, Phil Trans R Soc B 262:23-81; Treves & Rolls 1994, Hippocampus 4:374-391;
Leutgeb et al. 2007, Science 315:961-966). The sparsity of the code is set by the inhibition among the targets, which
this stage does not build (grow it with other stages, or connect the targets to inhibitory cells by hand).
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np

from neurogenesis.params import resolve, worst_case
from neurogenesis.stages.base import register_stage
from neurogenesis.stages.guidance import select_cells
from neurogenesis.tissue import MAX_DELAY_TICKS, Tissue


@register_stage("random_projection")
class RandomProjection:
    """Each selected target cell receives synapses from `fan_in` distinct source cells drawn uniformly at random
    (all sources if there are fewer). `sources`, `targets`: selectors {region, cell_type, expressing, threshold}. The draw
    uses a targets x sources array of keys: meant for populations up to a few thousand cells (2048 x 2048 = 32 MB).
    `weight` (a `Param`, toolbox units; its sign is the synapse sign), `delay` (ticks, 1..MAX_DELAY_TICKS),
    `allow_self` (default False), `plastic` (default: unset; False marks the new synapses with the K6 `plastic` mask, a
    fixed expansion that plasticity stages skip and that downstream code can tell apart from synapses made by contact).
    Randomness: one stream (the stage's). O(targets x fan_in).
    Neutral default: `fan_in` 0 (or no sources or targets) = no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        k = int(worst_case(params.get("fan_in"), 0))
        if k <= 0:
            return N * 4, N
        return int(N * N * 16 + N * k * 24), int(N * N * 12 + N * k * 10)     # keys and argsort over targets x sources

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        k = int(round(float(resolve(params.get("fan_in", 0), genome, fields))))
        if k <= 0:
            return tissue
        src = select_cells(tissue, params.get("sources"))
        tgt = select_cells(tissue, params.get("targets"))
        if len(src) == 0 or len(tgt) == 0:
            return tissue
        allow_self = bool(resolve(params.get("allow_self", False), genome, fields))
        w = int(round(float(resolve(params.get("weight", 1.0), genome, fields))))
        d = int(round(float(resolve(params.get("delay", 1), genome, fields))))
        if not 1 <= d <= MAX_DELAY_TICKS:
            raise ValueError(f"random_projection: delay {d} out of [1, {MAX_DELAY_TICKS}]")
        kk = min(k, len(src))
        # k distinct sources per target: argsort of uniform keys (vectorised, no Python loop over targets)
        keys = rng.random((len(tgt), len(src)))
        if not allow_self:
            same = tgt[:, None] == src[None, :]
            keys[same] = 2.0                                   # never chosen while other sources remain
        pick = np.argsort(keys, axis=1)[:, :kk]
        pre = src[pick].ravel()
        post = np.repeat(tgt, kk)
        if not allow_self:
            ok = pre != post
            pre, post = pre[ok], post[ok]
        plastic = params.get("plastic")
        extra = {}
        if plastic is not None:
            extra["plastic"] = np.full(len(pre), bool(resolve(plastic, genome, fields)), np.bool_)
        tissue.connectivity = tissue.connectivity.append(pre, post, np.full(len(pre), w, np.int32),
                                                         np.full(len(pre), d, np.int32), **extra)
        return tissue
