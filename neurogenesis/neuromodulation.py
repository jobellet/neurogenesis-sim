"""Neuromodulation by volume transmission (P5): a diffuse modulator gating three-factor plasticity.

Modulator cells release a transmitter that spreads through the tissue (volume transmission; Agnati, 1995,
Neuroscience). Its level at a cell is the sum over modulator cells of their spike trains low-pass filtered with time
constant `tau_ms` (one tick = 1 ms), weighted by exp(-distance / `space_constant`). That level is the third factor of
`spiking.plasticity.ThreeFactorRule`: dw = eta x eligibility x modulator, the eligibility trace (time constant `tau_e`)
summing pre-synaptic arrivals coinciding with post-synaptic spikes (Izhikevich, 2007, Cerebral Cortex; Fremaux, 2016,
Frontiers in Neural Circuits). Weights keep their sign (Dale's principle) and their magnitude is clipped to
[w_min, w_max].

Entry points: `VolumeModulator` (modulator trace from a spike raster), `apply_modulated_plasticity` (weights after a
spike raster) and the `neuromodulate` stage.
"""
import numpy as np
from typing import Dict, Any, Tuple, Optional
from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.spiking.plasticity import ThreeFactorRule


class VolumeModulator:
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
        T, N = spikes.shape
        decay = np.exp(-1.0 / self.tau_ms) if self.tau_ms > 0 else 0.0

        if len(self.source_cells) == 0:
            if target_cells is not None:
                return np.full((T, len(target_cells)), self.baseline, dtype=np.float32)
            return np.full(T, self.baseline, dtype=np.float32)

        source_spikes = spikes[:, self.source_cells]

        if positions is not None and target_cells is not None:
            # We must filter first, then apply spatial weights
            src_pos = positions[self.source_cells]
            tgt_pos = positions[target_cells]

            diff = tgt_pos[:, None, :] - src_pos[None, :, :]
            dists = np.linalg.norm(diff, axis=-1)
            spatial_weights = np.exp(-dists / self.space_constant)

            # Filter source spikes O(T * N_sources)
            filtered_sources = np.zeros_like(source_spikes, dtype=np.float32)
            curr = np.zeros(len(self.source_cells), dtype=np.float32)
            for t in range(T):
                curr = curr * decay + source_spikes[t]
                filtered_sources[t] = curr

            trace = filtered_sources @ spatial_weights.T
            return trace * self.gain + self.baseline

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
    modulator = VolumeModulator(source_cells, space_constant, tau_ms)

    if len(tissue.connectivity.pre) == 0:
        return tissue.connectivity.weight

    trace = modulator.modulator_trace(
        spikes, positions=tissue.positions, target_cells=tissue.connectivity.post
    )

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
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        mod_cells = params.get("modulator_cells", [])
        if len(mod_cells) == 0:
            return 0, 0
        num_sources = len(mod_cells)
        ticks = params.get("ticks", 1000)
        bytes_cost = E * 4 + ticks * E * 4
        ops_cost = ticks * num_sources * E + ticks * E * 6
        return bytes_cost, ops_cost

    def run(
        self,
        tissue: Tissue,
        params: Dict[str, Any],
        genome: Dict[str, Any],
        fields: Dict[str, Any],
        rng: np.random.Generator,
    ) -> Tissue:
        mod_cells = params.get("modulator_cells", [])
        if len(mod_cells) == 0:
            return tissue

        spikes = params.get("spikes", None)
        if spikes is None:
            return tissue

        source_cells = np.array(mod_cells)
        space_constant = params.get("space_constant", 50.0)
        tau_ms = params.get("tau_ms", 50.0)
        eta = params.get("eta", 0.05)
        tau_plus = params.get("tau_plus", 20.0)
        tau_minus = params.get("tau_minus", 20.0)
        tau_e = params.get("tau_e", 50.0)
        w_min = params.get("w_min", 0.0)
        w_max = params.get("w_max", 1000.0)

        new_weights = apply_modulated_plasticity(
            tissue,
            spikes,
            source_cells,
            space_constant,
            tau_ms,
            eta,
            tau_plus,
            tau_minus,
            tau_e,
            w_min,
            w_max,
        )
        tissue.connectivity.weight = new_weights

        return tissue

