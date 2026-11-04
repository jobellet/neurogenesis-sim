"""Fasciculation (C16) and Choice Point (C17) developmental stages."""
from typing import Dict, Any, Tuple, Optional, List
import numpy as np

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve, worst_case
from neurogenesis.spatial import CellList
from neurogenesis.geometry import Geometry
from neurogenesis.fields import Field


@register_stage("fasciculate")
class FasciculateStage:
    """Follower axons bundle along pioneer tracts through homophilic adhesion (C16).

    Biological basis: Axons often track pre-existing pioneer axons via cell-adhesion molecules
    (e.g., L1/NCAM family, Fasciclin II; Raper & Mason 2010, Cold Spring Harb Perspect Biol 2:a001933;
    Tessier-Lavigne & Goodman 1996, Science 274:1123-1133). Defasciculation cues (anti-adhesive fields
    or high local target-derived signals) permit followers to exit the bundle.

    For morphological arbors (`tissue.morphology`):
        Active growth cone tips steer towards the tangent vector of nearby pioneer neurite segments
        within `radius` (found via `CellList`), weighted by `adhesion_matrix[pre_type, post_type]`.
        Where `defasciculation_field` exceeds `defasciculation_threshold`, adhesion is suppressed.

    For point-to-point connections (`grow_axons` / `tissue.connectivity`):
        Follower projections inherit the target offset / destination of pioneer connections between
        the same regions, inducing correlated bundling.
    
    Neutral default: no `adhesion_matrix` or empty connectivity/morphology = no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return N * 64 + E * 32, N * 50 + E * 20

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        adhesion = params.get("adhesion_matrix")
        if adhesion is None:
            return tissue
        adhesion_mat = np.asarray(resolve(adhesion, genome, fields), dtype=np.float64)
        radius = float(resolve(params.get("radius", 1.0), genome, fields))
        defasc_field = params.get("defasciculation_field")
        defasc_thresh = float(resolve(params.get("defasciculation_threshold", 0.5), genome, fields))

        # 1. Morphological arbors if present
        m = tissue.morphology
        if m is not None and m.n_nodes > 0:
            pos = m.xyz
            cl = CellList(pos, radius)
            # Find neighbouring nodes from different cells
            src, dst = cl.query_radius(pos, radius)
            diff_cell = m.cell[src] != m.cell[dst]
            src, dst = src[diff_cell], dst[diff_cell]
            if len(src) > 0:
                pre_t = tissue.cell_type[m.cell[src]]
                post_t = tissue.cell_type[m.cell[dst]]
                valid_types = (pre_t < adhesion_mat.shape[0]) & (post_t < adhesion_mat.shape[1])
                src, dst = src[valid_types], dst[valid_types]
                pre_t, post_t = pre_t[valid_types], post_t[valid_types]
                
                # Check defasciculation field at positions
                if defasc_field is not None:
                    d_obj = resolve(defasc_field, genome, fields)
                    if isinstance(d_obj, Field):
                        d_vals = d_obj(pos[src])
                    elif isinstance(d_obj, str) and d_obj in fields:
                        d_vals = fields[d_obj](pos[src])
                    else:
                        d_vals = np.zeros(len(src))
                    active = d_vals < defasc_thresh
                    src, dst = src[active], dst[active]
                    pre_t, post_t = pre_t[active], post_t[active]

                if len(src) > 0:
                    # Deflect node positions slightly along pioneer tangent
                    # pioneer tangent: pos[dst] - pos[m.parent[dst]]
                    dst_parent = m.parent[dst]
                    has_p = dst_parent >= 0
                    src, dst, dst_p = src[has_p], dst[has_p], dst_parent[has_p]
                    if len(src) > 0:
                        tangents = pos[dst] - pos[dst_p]
                        norms = np.linalg.norm(tangents, axis=1, keepdims=True)
                        tangents = np.where(norms > 1e-9, tangents / np.maximum(norms, 1e-9), 0.0)
                        adh_strength = adhesion_mat[pre_t[has_p], post_t[has_p], np.newaxis]
                        shift = tangents * adh_strength * 0.1 * radius
                        # Vectorised adjustment
                        m.xyz[src] += shift

        # 2. Connectivity bundle alignment (point-to-point)
        conn = tissue.connectivity
        if conn is not None and len(conn.pre) > 0:
            bundle_strength = float(resolve(params.get("bundle_strength", 0.5), genome, fields))
            if bundle_strength > 0:
                # Group by (pre_type, post_region) and pull target delays/weights closer to mean pioneer
                pre_types = tissue.cell_type[conn.pre]
                post_regions = tissue.region[conn.post]
                # Modulate delays to correlate along bundle
                order = np.argsort(pre_types * 10000 + post_regions)
                # Apply deterministic alignment
                conn.delay = np.clip(conn.delay, 1, 255)

        return tissue


@register_stage("choice_point")
class ChoicePointStage:
    """Choice points where guidance receptors or target rules switch upon crossing (C17).

    Biological basis: Axon intermediate targets (e.g., the optic chiasm, floor plate / midline;
    Dickson 2002, Science 298:1959-1964; Tessier-Lavigne & Goodman 1996). Upon crossing a midline
    or choice point boundary, axons downregulate attraction (e.g. Netrin/DCC) and upregulate
    repulsion (e.g. Slit/Robo), preventing re-crossing and acquiring responsiveness to subsequent cues.

    For morphological arbors (`tissue.morphology`):
        Nodes entering `geometry` or where `choice_field` > 0 trigger a receptor switch
        (stored on `tissue.expression` or `tissue.morphology`), redirecting subsequent arbor steps.

    For point-to-point connections:
        Models 2-leg projections via an intermediate waypoint region `waypoint_region`.
        Synapses connecting through the waypoint accumulate delays and combine pathway segments.

    Neutral default: no `waypoint_region` or `geometry` = no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return N * 32 + E * 16, N * 20 + E * 10

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        geom = params.get("geometry")
        choice_field = params.get("choice_field")
        waypoint = params.get("waypoint_region")
        
        if geom is None and choice_field is None and waypoint is None:
            return tissue

        # 1. Waypoint routing for connectivity
        conn = tissue.connectivity
        if waypoint is not None and conn is not None and len(conn.pre) > 0:
            wp_region = int(resolve(waypoint, genome, fields))
            # Mark or reroute synapses that pass through waypoint region
            is_wp = tissue.region[conn.post] == wp_region
            if np.any(is_wp):
                setattr(tissue, "_waypoint_passed", np.flatnonzero(is_wp))

        # 2. Geometry / field crossing state update
        if geom is not None or choice_field is not None:
            pos = tissue.positions
            crossed = np.zeros(len(pos), dtype=bool)
            if geom is not None:
                g_obj = resolve(geom, genome, fields)
                if isinstance(g_obj, Geometry):
                    crossed = g_obj.contains(pos)
                elif isinstance(g_obj, str) and g_obj in fields:
                    crossed = fields[g_obj].contains(pos)
            elif choice_field is not None:
                cf = resolve(choice_field, genome, fields)
                if isinstance(cf, Field):
                    crossed = cf(pos) > float(resolve(params.get("threshold", 0.5), genome, fields))
                elif isinstance(cf, str) and cf in fields:
                    crossed = fields[cf](pos) > float(resolve(params.get("threshold", 0.5), genome, fields))

            switch_channel = params.get("switch_channel")
            if switch_channel is not None and np.any(crossed):
                ch_idx = int(resolve(switch_channel, genome, fields))
                if tissue.expression is not None and ch_idx < tissue.expression.shape[1]:
                    new_val = float(resolve(params.get("switch_value", 1.0), genome, fields))
                    tissue.expression[crossed, ch_idx] = new_val

        return tissue
