import numpy as np
from typing import Any, Dict, Tuple, Optional
import warnings

from neurogenesis.params import resolve
from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage


def apply_dendritic_attenuation(
    tissue: Tissue,
    length_constant: Any = 100.0,
    dendrite_velocity: Any = None,
    genome: Optional[Dict] = None,
    fields: Optional[Dict] = None,
    distal_compartment_threshold: Optional[float] = None,
) -> Tissue:
    """
    Applies dendritic attenuation to synaptic weights based on `dendritic_distance`.
    Optionally computes `dendritic_distance` if missing or NaN and `post_node` is present.
    Optionally sets `compartment = 1` for synapses / cells if `distal_compartment_threshold` is exceeded.
    """
    genome = genome or {}
    fields = fields or {}
    length_const = float(resolve(length_constant, genome=genome, fields=fields))

    if len(tissue.connectivity.pre) == 0:
        return tissue

    c = tissue.connectivity

    # Try to compute dendritic_distance if missing or NaN
    has_dend_dist = c.dendritic_distance is not None
    if has_dend_dist:
        valid_dist = ~np.isnan(c.dendritic_distance)
    else:
        valid_dist = np.zeros(len(c.pre), dtype=bool)

    if (
        not np.all(valid_dist)
        and c.post_node is not None
        and tissue.morphology is not None
    ):
        try:
            path_lengths = tissue.morphology.path_length_to_root()
            valid_post_nodes = c.post_node >= 0

            new_dist = np.full(len(c.pre), np.nan, dtype=np.float32)
            if has_dend_dist:
                new_dist = c.dendritic_distance.copy()

            update_mask = (~valid_dist) & valid_post_nodes
            new_dist[update_mask] = path_lengths[c.post_node[update_mask]]

            c.dendritic_distance = new_dist
            has_dend_dist = True
            valid_dist = ~np.isnan(c.dendritic_distance)
        except AttributeError:
            pass

    if not has_dend_dist:
        return tissue

    d = np.where(valid_dist, c.dendritic_distance, 0.0)

    attenuation = np.exp(-d / length_const)
    new_weights = c.weight * attenuation

    signs = np.sign(new_weights)
    mags = np.abs(new_weights)
    mags = np.where(mags > 0, np.maximum(mags, 1.0), 0.0)
    c.weight = signs * mags

    if dendrite_velocity is not None:
        velocity = float(resolve(dendrite_velocity, genome=genome, fields=fields))
        delay_add = np.round(d / velocity).astype(np.int32)
        total_delay = c.delay + delay_add

        from neurogenesis.tissue import MAX_DELAY_TICKS as MAXD
        exceeds = total_delay > MAXD
        if np.any(exceeds):
            count = np.sum(exceeds)
            warnings.warn(
                f"Dendritic delay exceeds {MAXD} ticks for {count} synapses. Clipping to {MAXD}."
            )

        c.delay = np.clip(total_delay, 1, MAXD)

    if distal_compartment_threshold is not None:
        thresh = float(resolve(distal_compartment_threshold, genome=genome, fields=fields))
        is_distal = d >= thresh
        if not hasattr(tissue, "compartment") or tissue.compartment is None:
            tissue.compartment = np.zeros(len(tissue.alive), dtype=np.int32)

        distal_post_cells = c.post[is_distal]
        tissue.compartment[distal_post_cells] = 1

    return tissue


@register_stage("dendritic_attenuate")
class DendriticAttenuateStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        if not params:
            return 0, 0
        bytes_cost = E * 4 * 2
        if params.get("dendrite_velocity") is not None:
            bytes_cost += E * 4 * 2

        ops_cost = E * 5
        if params.get("dendrite_velocity") is not None:
            ops_cost += E * 3

        return bytes_cost, ops_cost

    def run(
        self,
        tissue: Tissue,
        params: Dict[str, Any],
        genome: Dict[str, Any],
        fields: Dict[str, Any],
        rng: np.random.Generator,
    ) -> Tissue:
        if not params:
            return tissue

        length_constant = params.get("length_constant", 100.0)
        dendrite_velocity = params.get("dendrite_velocity", None)
        distal_threshold = params.get("distal_compartment_threshold", None)

        return apply_dendritic_attenuation(
            tissue=tissue,
            length_constant=length_constant,
            dendrite_velocity=dendrite_velocity,
            genome=genome,
            fields=fields,
            distal_compartment_threshold=distal_threshold,
        )
