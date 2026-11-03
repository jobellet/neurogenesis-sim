"""Partner selection by recognition channels (C18)."""
from typing import Dict, Any, Tuple
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve


@register_stage("partner_select")
class PartnerSelectStage:
    """Keeps a candidate synapse only with the probability its partners' recognition channels allow.

    Proximity is not enough for a synapse to form (a deviation from Peters' rule; Peters & Feldman 1976, J Neurocytol
    5:63-84): transmembrane recognition pairs such as neurexin-neuroligin isoforms bias which partners connect
    (Sudhof 2008, Nature 455:903-911; Graf et al. 2004, Cell 119:1013-1026). Every cell has a recognition channel,
    its `cell_type` (default, `channels: "cell_type"`) or the argmax of its expression (`channels: "expression"`),
    or an explicit per-cell integer list. A synapse from channel i onto channel j survives with probability
    `compat[i][j]` (a `Param` matrix, entries clipped to [0, 1]); the others are removed. Applies to the synapses present
    (from `grow_axons`, `arbor_synapses` or `connect_by_hand`); synapses with a channel outside the matrix are kept.
    Neutral default: no `compat` = no-op. The identity_expression rule of `grow_axons` is the special case of an
    identity matrix. One uniform draw per synapse from the stage's stream; O(E).
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return E * 24 + N * 4, E * 8 + N

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        conn = tissue.connectivity
        if params.get("compat") is None or conn is None or len(conn.pre) == 0:
            return tissue
        compat = np.clip(np.asarray(resolve(params["compat"], genome, fields), dtype=np.float64), 0.0, 1.0)
        if compat.ndim != 2:
            raise ValueError("partner_select: compat must be a (pre channels x post channels) matrix")
        channels = resolve(params.get("channels", "cell_type"), genome, fields)
        if isinstance(channels, str):
            if channels == "cell_type":
                ch = np.asarray(tissue.cell_type, dtype=np.int64)
            elif channels == "expression":
                if tissue.expression is None or tissue.expression.shape[1] == 0:
                    raise ValueError("partner_select: channels 'expression' needs expression channels")
                ch = np.argmax(tissue.expression, axis=1).astype(np.int64)
            else:
                raise ValueError(f"partner_select: unknown channels {channels!r}")
        else:
            ch = np.asarray(channels, dtype=np.int64)
            if ch.shape != (len(tissue.alive),):
                raise ValueError(f"partner_select: channels must have one entry per cell ({len(tissue.alive)})")
        ci, cj = ch[conn.pre], ch[conn.post]
        inside = (ci >= 0) & (ci < compat.shape[0]) & (cj >= 0) & (cj < compat.shape[1])
        p = np.ones(len(conn.pre))
        p[inside] = compat[ci[inside], cj[inside]]
        keep = rng.random(len(conn.pre)) < p
        if not keep.all():
            tissue.connectivity = conn.take(keep)
        return tissue
