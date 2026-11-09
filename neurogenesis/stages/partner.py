"""Partner selection by recognition channels (C18) and by a bilinear rule on expression profiles (C25)."""
from typing import Dict, Any, Tuple
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve, worst_case


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


@register_stage("bilinear_select")
class BilinearSelectStage:
    """Keeps a candidate synapse with a probability set by the expression profiles of its two cells through a low-rank
    bilinear rule, the genetic model of connectivity (Kovacs, Barabasi & Barabasi 2020, PNAS 117:3285; bilinear
    pre / post form: Barabasi & Barabasi 2020, Neuron 108:1057; Taylor et al. 2023, eLife):

        p(i -> j) = sigmoid(gain * x_i^T A B^T x_j + bias)

    with x the cells' expression vectors (`tissue.expression`, K channels), A (K x k) and B (K x k) `Param` matrices
    (k the rank, a few dimensions), `gain` (default 1) and `bias` (default 0). `pre_channels` / `post_channels` (lists
    of expression column names or indices) restrict x_i / x_j to those columns (A, B then have that many rows). A
    symmetric rule (e.g. gap-junction partners, x_i^T O x_j with O = A B^T symmetric) is A = B. A virtual knockout of a
    gene (`express(knockout=[...])`) zeroes its column and so removes its term. Applies to the synapses present (from
    `grow_axons`, `arbor_synapses`, `connect_by_hand`); `partner_select` is the special case of one-hot channels.
    Neutral default: no `A` or no `B` = no-op. One uniform draw per synapse from the stage's stream; O(N K k + E k).
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        """K and k from a constant `A` (default K = 32, k = 8 when A is a gene, field or formula)."""
        if params.get("A") is None or params.get("B") is None:
            return 0, 0
        shape = np.shape(np.atleast_2d(np.asarray(worst_case(params["A"], np.zeros((32, 8))), dtype=float)))
        K, k = int(shape[0]), int(shape[1])
        return E * (40 + 16 * k) + N * 8 * (K + 2 * k), E * (12 + 2 * k) + N * 2 * K * k

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        conn = tissue.connectivity
        if params.get("A") is None or params.get("B") is None or conn is None or len(conn.pre) == 0:
            return tissue
        X = tissue.expression
        if X is None or X.shape[1] == 0:
            raise ValueError("bilinear_select: needs expression channels (run `express` first)")
        X = np.asarray(X, np.float64)

        def columns(key):
            sel = params.get(key)
            if sel is None:
                return X
            sel = resolve(sel, genome, fields)
            idx = []
            for s in (sel if isinstance(sel, (list, tuple)) else [sel]):
                if isinstance(s, str):
                    if s not in tissue.expression_names:
                        raise ValueError(f"bilinear_select: {s!r} is not in expression_names")
                    idx.append(tissue.expression_names.index(s))
                else:
                    idx.append(int(s))
            return X[:, idx]

        Xp, Xq = columns("pre_channels"), columns("post_channels")
        A = np.atleast_2d(np.asarray(resolve(params["A"], genome, fields), np.float64))
        B = np.atleast_2d(np.asarray(resolve(params["B"], genome, fields), np.float64))
        if A.shape[0] != Xp.shape[1] or B.shape[0] != Xq.shape[1] or A.shape[1] != B.shape[1]:
            raise ValueError(f"bilinear_select: A must be ({Xp.shape[1]} x k) and B ({Xq.shape[1]} x k) with the same k; "
                             f"got {A.shape} and {B.shape}")
        U, V = Xp @ A, Xq @ B                                   # (N, k) each
        s = np.einsum("ek,ek->e", U[conn.pre], V[conn.post])
        gain = float(resolve(params.get("gain", 1.0), genome, fields))
        bias = float(resolve(params.get("bias", 0.0), genome, fields))
        p = 0.5 * (1.0 + np.tanh(0.5 * (gain * s + bias)))      # sigmoid, without overflow
        keep = rng.random(len(conn.pre)) < p
        if not keep.all():
            tissue.connectivity = conn.take(keep)
        return tissue
