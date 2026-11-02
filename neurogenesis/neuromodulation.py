"""Neuromodulation by volume transmission (P5): a diffuse modulator gating three-factor plasticity.

Modulator cells release a transmitter that spreads through the tissue (volume transmission; Agnati, 1995,
Neuroscience). Its level at a cell is the sum over modulator cells of their spike trains low-pass filtered with time
constant `tau_ms` (one tick = 1 ms), weighted by exp(-distance / `space_constant`). That level is the third factor of
`spiking.plasticity.ThreeFactorRule`: dw = eta x eligibility x modulator, the eligibility trace (time constant `tau_e`)
summing pre-synaptic arrivals coinciding with post-synaptic spikes (Izhikevich, 2007, Cerebral Cortex; Fremaux, 2016,
Frontiers in Neural Circuits). Weights keep their sign (Dale's principle) and their magnitude is clipped to
[w_min, w_max].

Entry points: `VolumeModulator` (modulator trace from a spike raster), `apply_modulated_plasticity` (weights after a
spike raster) and the `neuromodulate` stage. The source x target distance kernel is computed in blocks of at most
`MAX_PAIRS` pairs, so memory is O(T (N + S)) for T ticks, N cells and S modulator cells.
"""
from typing import Dict, Any, Tuple, Optional

import numpy as np

from neurogenesis.params import resolve, worst_case
from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.spiking.plasticity import ThreeFactorRule

MAX_PAIRS = 1 << 20  # largest block of (target, source) pairs held at once by the spatial kernel


class VolumeModulator:
    """Modulator level from the spikes of `source_cells`: exponential filter (`tau_ms`) and exponential spatial
    decay (`space_constant`, space units), times `gain`, plus `baseline`."""

    def __init__(
        self,
        source_cells: np.ndarray,
        space_constant: float = 50.0,
        tau_ms: float = 50.0,
        baseline: float = 0.0,
        gain: float = 1.0,
    ):
        self.source_cells = np.asarray(source_cells, dtype=np.int32)
        self.space_constant = float(space_constant)
        self.tau_ms = float(tau_ms)
        self.baseline = float(baseline)
        self.gain = float(gain)

    def modulator_trace(
        self,
        spikes: np.ndarray,
        positions: Optional[np.ndarray] = None,
        target_cells: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """(T,) global level from a (T, N) spike raster, or (T, len(target_cells)) levels at `target_cells` when
        `positions` are given."""
        T, N = spikes.shape
        decay = np.exp(-1.0 / self.tau_ms) if self.tau_ms > 0 else 0.0

        if len(self.source_cells) == 0:
            if target_cells is not None:
                return np.full((T, len(target_cells)), self.baseline, dtype=np.float32)
            return np.full(T, self.baseline, dtype=np.float32)

        source_spikes = spikes[:, self.source_cells]

        if positions is not None and target_cells is not None:
            # Filter source spikes O(T * N_sources), then weight by distance in blocks of targets
            filtered_sources = np.zeros(source_spikes.shape, dtype=np.float32)
            curr = np.zeros(len(self.source_cells), dtype=np.float32)
            for t in range(T):
                curr = curr * decay + source_spikes[t]
                filtered_sources[t] = curr

            target_cells = np.asarray(target_cells)
            src_pos = np.asarray(positions[self.source_cells], dtype=np.float64)
            trace = np.empty((T, len(target_cells)), dtype=np.float32)
            block = max(1, MAX_PAIRS // len(self.source_cells))
            for a in range(0, len(target_cells), block):
                tgt_pos = np.asarray(positions[target_cells[a:a + block]], dtype=np.float64)
                dists = np.linalg.norm(tgt_pos[:, None, :] - src_pos[None, :, :], axis=-1)
                if self.space_constant > 0:
                    spatial_weights = np.exp(-dists / self.space_constant)
                else:
                    spatial_weights = (dists == 0).astype(np.float64)
                trace[:, a:a + block] = filtered_sources @ spatial_weights.T.astype(np.float32)
            trace *= self.gain
            trace += self.baseline
            return trace

        else:
            total_spikes = source_spikes.sum(axis=1)
            trace = np.zeros(T, dtype=np.float32)
            curr = 0.0

            for t in range(T):
                curr = curr * decay + total_spikes[t]
                trace[t] = curr

            return trace * self.gain + self.baseline


def apply_modulated_plasticity(
    tissue: Tissue,
    spikes: np.ndarray,
    source_cells: np.ndarray,
    space_constant: float = 50.0,
    tau_ms: float = 50.0,
    eta: float = 0.05,
    tau_plus: float = 20.0,
    tau_minus: float = 20.0,
    tau_e: float = 50.0,
    w_min: float = 0.0,
    w_max: float = 1000.0,
) -> np.ndarray:
    """Weights after `ThreeFactorRule` over a (T, N) spike raster, gated by the volume modulator of `source_cells`.

    `tau_plus` and `tau_minus` are accepted for a timing-dependent eligibility; the current rule's eligibility is the
    pre / post coincidence filtered with `tau_e`, so they do not change the result.
    """
    modulator = VolumeModulator(source_cells, space_constant, tau_ms)

    if len(tissue.connectivity.pre) == 0:
        return tissue.connectivity.weight

    # Modulator level per cell (columns indexed by cell, as ThreeFactorRule reads modulator[t][post]), computed only
    # at the cells that receive synapses
    targets = np.unique(tissue.connectivity.post)
    trace = np.zeros((spikes.shape[0], spikes.shape[1]), dtype=np.float32)
    trace[:, targets] = modulator.modulator_trace(spikes, positions=tissue.positions, target_cells=targets)

    rule = ThreeFactorRule(eta=eta, tau_e=tau_e)
    delays = tissue.connectivity.delay

    import jax.numpy as jnp

    weights = tissue.connectivity.weight
    pre = tissue.connectivity.pre
    post = tissue.connectivity.post

    final_w = rule.apply(
        weights=jnp.array(weights),
        pre=jnp.array(pre),
        post=jnp.array(post),
        delays=jnp.array(delays),
        spikes=jnp.array(spikes),
        modulator=jnp.array(trace),
        original_weights=jnp.array(weights),
    )
    final_w = np.array(final_w)

    # Dale's sign and w_min / w_max clipping
    is_exc = weights >= 0
    w_min_mag = min(abs(w_min), abs(w_max))
    w_max_mag = max(abs(w_min), abs(w_max))

    mags = np.abs(final_w)
    mags = np.clip(mags, w_min_mag, w_max_mag)

    # Preserve original sign
    final_w = np.where(is_exc, mags, -mags)

    return final_w


@register_stage("neuromodulate")
class NeuromodulateStage:
    """Three-factor plasticity gated by volume transmission from `modulator_cells` over the spike raster `spikes`
    (T, N); every other parameter is a Param. No modulator cells or no spikes: no-op."""

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        if params.get("modulator_cells") is None or E == 0:
            return 0, 0
        cells = worst_case(params["modulator_cells"], None)
        S = N if cells is None else np.atleast_1d(cells).size  # a Field / Expr: any cell may be a source
        if S == 0:
            return 0, 0
        T = int(worst_case(params.get("ticks"), 1000))
        P = min(N, E)  # cells receiving synapses
        kernel = min(P * S, max(MAX_PAIRS, S))
        # trace per cell (NumPy, JAX copy) and the raster copied to JAX, filtered sources, distance kernel block
        bytes_cost = 3 * T * N * 4 + T * S * 4 + kernel * 6 * 8 + 4 * E * 4
        ops_cost = T * S + P * S * 8 + T * P * S * 2 + T * E * 6
        return bytes_cost, ops_cost

    def run(
        self,
        tissue: Tissue,
        params: Dict[str, Any],
        genome: Dict[str, Any],
        fields: Dict[str, Any],
        rng: np.random.Generator,
    ) -> Tissue:
        spikes = params.get("spikes", None)
        if params.get("modulator_cells") is None or spikes is None:
            return tissue

        def value(key, default):
            return resolve(params.get(key, default), genome=genome, fields=fields)

        source_cells = np.atleast_1d(np.asarray(value("modulator_cells", []), dtype=np.int64)).ravel()
        if source_cells.size == 0:
            return tissue

        spikes = np.asarray(spikes)
        ticks = value("ticks", None)
        if ticks is not None:
            spikes = spikes[: int(ticks)]

        tissue.connectivity.weight = apply_modulated_plasticity(
            tissue,
            spikes,
            source_cells,
            space_constant=float(value("space_constant", 50.0)),
            tau_ms=float(value("tau_ms", 50.0)),
            eta=float(value("eta", 0.05)),
            tau_plus=float(value("tau_plus", 20.0)),
            tau_minus=float(value("tau_minus", 20.0)),
            tau_e=float(value("tau_e", 50.0)),
            w_min=float(value("w_min", 0.0)),
            w_max=float(value("w_max", 1000.0)),
        )
        return tissue
