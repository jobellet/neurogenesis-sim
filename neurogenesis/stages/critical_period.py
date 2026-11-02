"""Critical-period gate (C23): opens and closes synaptic plasticity through the per-synapse `plastic` mask (K6)."""
from typing import Any, Dict, Tuple

import numpy as np

from neurogenesis.params import resolve
from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue


def inhibitory_maturity(tissue: Tissue, source_type, target, measure: str = "mean") -> float:
    """Maturity of inhibition from cells of `source_type` (int or list of cell types) onto the `target` cells (bool
    mask (N,)): the mean |w| of their inhibitory (w < 0) synapses ("mean"), or the mean over target cells of the summed
    |w| each receives ("sum"). 0 when there are no such synapses. O(E)."""
    c = tissue.connectivity
    if len(c.pre) == 0:
        return 0.0
    sel = np.isin(tissue.cell_type[c.pre], np.asarray(source_type).ravel()) & target[c.post] & (c.weight < 0)
    total = float(np.abs(c.weight[sel].astype(np.float64)).sum())
    if measure == "sum":
        n = int(np.count_nonzero(target))
        return total / n if n else 0.0
    if measure != "mean":
        raise ValueError(f"critical_period_gate: unknown measure {measure!r} (use 'mean' or 'sum')")
    n = int(np.count_nonzero(sel))
    return total / n if n else 0.0


@register_stage("critical_period_gate")
class CriticalPeriodGate:
    """Critical period of activity-dependent plasticity: the window opens when inhibition from a chosen (e.g. fast-
    spiking) cell type has matured and closes later, as the maturation of parvalbumin-cell inhibition opens and the
    perineuronal nets around those cells close the ocular-dominance critical period (Hensch 2005, Nat Rev Neurosci;
    Hubel & Wiesel 1970, J Physiol); removing the nets with chondroitinase ABC reopens it (Pizzorusso et al. 2002,
    Science). The stage only sets `tissue.connectivity.plastic` on the gated synapses (onto `target_type` cells, all
    by default): False before opening, True while open, False after closing. Call it before each plasticity stage
    (`refine_by_activity`, `prune`, `scale`, `neuromodulate`); its state (phase, gate calls since opening) is kept on
    the tissue as `_critical_period`. Synapses added later are plastic until the next call."""

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        if not cls._active(params):
            return 0, 0
        return N + E * 8, N * 2 + E * 12

    @staticmethod
    def _active(params: Dict[str, Any]) -> bool:
        return any(params.get(k) is not None for k in ("open_threshold", "open", "close", "reopen"))

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        if not self._active(params):
            return tissue
        r = lambda k, d=None: d if params.get(k) is None else resolve(params[k], genome, fields)
        N = len(tissue.alive)
        target_type = r("target_type")
        target = np.ones(N, dtype=bool) if target_type is None else np.isin(tissue.cell_type, np.asarray(target_type).ravel())

        def maturity() -> float:
            if params.get("maturity") is not None:
                return float(r("maturity"))
            if params.get("source_type") is None:
                raise ValueError("critical_period_gate: a threshold needs 'source_type' or 'maturity'")
            return inhibitory_maturity(tissue, r("source_type"), target, str(r("measure", "mean")))

        st = dict(getattr(tissue, "_critical_period", None) or {"phase": "pre", "age": 0, "reopened": False})
        if bool(r("reopen", False)):
            st = {"phase": "open", "age": 0, "reopened": True}
        elif bool(r("close", False)):
            st["phase"] = "closed"
        elif st["phase"] == "pre":
            thr = r("open_threshold")
            if bool(r("open", False)) or (thr is not None and maturity() >= float(thr)):
                st.update(phase="open", age=0)
        elif st["phase"] == "open":
            st["age"] += 1
            after, thr = r("close_after"), r("close_threshold")
            if (after is not None and st["age"] >= int(after)) or \
                    (thr is not None and not st["reopened"] and maturity() >= float(thr)):
                st["phase"] = "closed"
        tissue._critical_period = st

        c = tissue.connectivity
        if len(c.pre):
            gated = target[c.post]
            plastic = c.plastic_mask().copy()
            plastic[gated] = st["phase"] == "open"
            c.plastic = plastic
        return tissue
