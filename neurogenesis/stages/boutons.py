"""Connection multiplicity (C19)."""

import numpy as np
from typing import Dict, Any

from neurogenesis.tissue import Tissue
from neurogenesis.params import Param, resolve
from neurogenesis.stages.base import register_stage


@register_stage("cluster_boutons")
class ClusterBoutons:
    """Connection multiplicity is cell-type specific (e.g. basket-cell innervation).

    Draws a contact count per synapse from a per (pre type, post type) distribution,
    stored as a per-synapse `contacts` field. Weights are scaled linearly by `contacts`.
    This is a linear scaling rule, not a measured physiological distribution.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> tuple[int, int]:
        return E * 4, E * 10

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        E = len(tissue.connectivity.pre)
        if E == 0:
            return tissue

        contacts_param = resolve(params.get("contacts"), genome, fields)
        if contacts_param is None:
            return tissue

        pre_types = tissue.cell_type[tissue.connectivity.pre]
        post_types = tissue.cell_type[tissue.connectivity.post]

        contacts = np.ones(E, dtype=np.int32)

        # contacts_param is expected to be a dict of {(pre, post): distribution}
        # where distribution is either a fixed integer, or {"type": "truncated_poisson", "mean": x} or list of probabilities

        for (pre_type, post_type), dist in contacts_param.items():
            if isinstance(pre_type, str):
                try:
                    pre_type = int(pre_type)
                except ValueError:
                    pass
            if isinstance(post_type, str):
                try:
                    post_type = int(post_type)
                except ValueError:
                    pass

            mask = (pre_types == pre_type) & (post_types == post_type)
            count = np.sum(mask)
            if count == 0:
                continue

            if isinstance(dist, (int, float)):
                contacts[mask] = int(dist)
            elif isinstance(dist, dict) and dist.get("type") == "truncated_poisson":
                mean = dist.get("mean", 1.0)
                if mean <= 0:
                    raise ValueError("truncated_poisson mean must be > 0")
                # Simple rejection sampling for truncated poisson (>= 1)
                vals = rng.poisson(mean, size=count)
                while True:
                    invalid = vals < 1
                    if not np.any(invalid):
                        break
                    vals[invalid] = rng.poisson(mean, size=np.sum(invalid))
                contacts[mask] = vals.astype(np.int32)
            elif isinstance(dist, list):
                # Probabilities table (0-indexed contact counts)
                probs = np.array(dist, dtype=np.float32)
                probs /= np.sum(probs)
                vals = rng.choice(len(probs), p=probs, size=count)
                contacts[mask] = np.maximum(1, vals).astype(np.int32)

        tissue.connectivity.contacts = contacts
        tissue.connectivity.weight = (tissue.connectivity.weight * contacts).astype(tissue.connectivity.weight.dtype)

        if tissue.morphology is not None:
            pass # Morphology not fully integrated yet, per ROADMAP C19 after N2/N3

        return tissue
