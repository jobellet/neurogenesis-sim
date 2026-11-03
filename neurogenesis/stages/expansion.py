"""Tissue expansion (C24): positions dilate as the cell count grows."""
from typing import Dict, Any, Tuple
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve


@register_stage("tissue_expand")
class TissueExpandStage:
    """Dilates the positions of living cells about a centre by `1 + kappa * N_new / N_total` along the chosen axes.

    `N_new` is the number of living cells added since the previous call (`N_total` counts all living cells), so a
    tissue whose count grows by a factor r per cycle stretches by `1 + kappa (1 - 1/r)` per cycle: proliferation
    pushes existing cells outward instead of crowding a fixed box (growth-simulator mechanics such as Zubler &
    Douglas 2009, Front Comput Neurosci 3:25 are replaced by this O(N) rule). The first call only records the cell
    count (nothing to compare with) unless `n_prev` is given, so place one call before the first `proliferate`.
    Local overlaps are left to `migrate` (`min_distance`).

    Params: `kappa` (0 = no-op), `axes` (3 flags, default all axes), `center` (default: centroid of the living cells),
    `n_prev` (cells before the growth step), `recompute_delays` with `conduction_velocity` (delays from the new
    distances; default: synapses keep their delays), `max_delay` as in `grow_axons`.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return N * 24, N * 12 + (E * 12 if params.get("recompute_delays") else 0)

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        kappa = float(resolve(params.get("kappa", 0.0), genome, fields))
        alive = tissue.alive
        n_total = int(alive.sum())
        if kappa == 0.0 or n_total == 0:
            return tissue
        if params.get("n_prev") is not None:
            n_prev = int(resolve(params["n_prev"], genome, fields))
        else:
            n_prev = getattr(tissue, "_expand_n_prev", None)
        tissue._expand_n_prev = n_total
        if n_prev is None or n_total <= n_prev:
            return tissue
        factor = 1.0 + kappa * (n_total - n_prev) / n_total
        axes = np.asarray(resolve(params.get("axes", [1, 1, 1]), genome, fields), dtype=np.float64).reshape(3)
        scale = np.where(axes != 0, factor, 1.0)
        center = params.get("center")
        center = tissue.positions[alive].mean(axis=0) if center is None else np.asarray(resolve(center, genome, fields), dtype=np.float64)
        tissue.positions = (center + (tissue.positions - center) * scale).astype(tissue.positions.dtype)

        conn = tissue.connectivity
        if bool(resolve(params.get("recompute_delays", False), genome, fields)) and conn is not None and len(conn.pre):
            from neurogenesis.tissue import effective_max_delay
            cv = float(resolve(params.get("conduction_velocity", 1.0), genome, fields))
            mx = effective_max_delay(resolve(params["max_delay"], genome, fields) if params.get("max_delay") is not None else None)
            dist = np.linalg.norm(tissue.positions[conn.pre] - tissue.positions[conn.post], axis=1)
            conn.delay = np.clip(np.round(dist / cv), 1, mx).astype(np.int32)
        return tissue
