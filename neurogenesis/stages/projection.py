"""Random sparse convergence (C28): `random_projection` connects each target cell to `fan_in` source cells drawn at random.

Anatomical wiring rule: some target populations receive a few inputs drawn without structure from a source population,
e.g. each Kenyon cell of the fly mushroom body receives about 7 projection-neuron inputs with no detectable pattern
(Caron, Ruta, Abbott & Axel 2013, Nature 497:113-117). This stage builds only the convergence; any inhibition among the
targets is grown or wired by other stages.
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
