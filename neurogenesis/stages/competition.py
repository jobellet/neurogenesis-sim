"""Competitive synapse elimination (C22)."""
from typing import Dict, Any, Tuple
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve, worst_case
from neurogenesis.stages.refinement import coactivity, _COACT_CHUNK


@register_stage("competitive_elimination")
class CompetitiveEliminationStage:
    """Inputs onto a target that fire it less than `fraction` of its strongest competitor are weakened or removed.

    An input's score is its coactivity with the target (pre spikes, after the synapse delay, followed by a target spike
    within `window` ticks). A target is a candidate only if it spiked at least `min_target_spikes` times (a silent
    target eliminates nothing). Synchronous inputs score alike and are all kept. Elimination by competition, not disuse
    alone: Willshaw 1981, Proc R Soc Lond B 212:401-419; Gouze, Lasry & Changeux 1983, Biol Cybern 46:207-215;
    Balice-Gordon & Lichtman 1994, Nature 372:519-524. Non-plastic synapses (K6) still compete but are never changed.
    Activity: `spikes` (a (T, N) raster), else the raster recorded by `refine_by_activity` with `record: true`; without
    either the stage is a no-op. Neutral default `fraction` 0 = no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        # Coactivity of a (ticks, N) raster: blocks of at most 2^22 (tick, synapse) pairs, about 24 bytes each
        ticks = int(worst_case(params.get("ticks"), 100))
        return E * 40 + ticks * N * 12 + min(ticks * E, _COACT_CHUNK) * 24, ticks * (E * 20 + N * 4) + E * 30

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        conn = tissue.connectivity
        fraction = float(resolve(params.get("fraction", 0.0), genome, fields))
        if conn is None or len(conn.pre) == 0 or fraction <= 0:
            return tissue
        spikes = params.get("spikes")
        spikes = getattr(tissue, "_activity_spikes", None) if spikes is None else resolve(spikes, genome, fields)
        if spikes is None:
            return tissue
        spikes = np.asarray(spikes)
        N = len(tissue.alive)
        if spikes.ndim != 2 or spikes.shape[1] != N:
            raise ValueError(f"competitive_elimination: activity raster has shape {spikes.shape}, expected (T, {N})")
        window = int(resolve(params.get("window", 5), genome, fields))
        min_target = float(resolve(params.get("min_target_spikes", 1), genome, fields))
        delta = int(resolve(params.get("delta", 0), genome, fields))
        remove = bool(resolve(params.get("remove", False), genome, fields))

        score = coactivity(spikes, conn.pre, conn.post, conn.delay, window).astype(np.float64)
        # Strongest competitor per target: sort by target, reduceat over groups (O(E log E) sort, O(E) reduce)
        order = np.argsort(conn.post, kind="stable")
        post_sorted = conn.post[order]
        starts = np.flatnonzero(np.r_[True, post_sorted[1:] != post_sorted[:-1]])
        group_max = np.maximum.reduceat(score[order], starts)
        best = np.empty(len(score))
        best[order] = np.repeat(group_max, np.diff(np.r_[starts, len(order)]))

        driven = spikes.sum(axis=0, dtype=np.int64) >= min_target            # silent targets eliminate nothing
        lose = driven[conn.post] & (best > 0) & (score < fraction * best)
        if conn.plastic is not None:
            lose &= conn.plastic                                             # K6: non-plastic never changed
        if not lose.any():
            return tissue
        if remove:
            tissue.connectivity = conn.take(~lose)
        elif delta:
            w = conn.weight
            mag = np.maximum(np.abs(w) - delta, 0)
            conn.weight = np.where(lose, np.sign(w) * mag, w).astype(np.int32)
        return tissue
