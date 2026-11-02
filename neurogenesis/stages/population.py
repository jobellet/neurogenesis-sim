from __future__ import annotations

import numpy as np
from typing import Dict, Any, Tuple

from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue
from neurogenesis.params import resolve, Param, worst_case
from neurogenesis.geometry import Geometry
from neurogenesis.spatial import CellList


@register_stage("seed_cells")
class SeedCells:
    """Seeds initial cell population into tissue geometries.

    Linear O(N) allocation and sampling.
    """
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        M = int(worst_case(params.get("N"), 100))
        bytes_cost = M * 128
        ops_cost = M * 15
        return bytes_cost, ops_cost

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N_param = params.get("N", 0)
        N = int(resolve(N_param, genome, fields))
        
        if N <= 0:
            return tissue

        # Get geometry
        geom_param = params.get("geometry", None)
        if geom_param is not None:
            resolved_geom = resolve(geom_param, genome, fields)
            if isinstance(resolved_geom, str):
                if resolved_geom not in fields:
                    raise ValueError(f"Geometry {resolved_geom!r} not found in project geometry/fields.")
                geometry = fields[resolved_geom]
            elif isinstance(resolved_geom, Geometry):
                geometry = resolved_geom
            else:
                raise TypeError(f"Expected geometry name or Geometry object, got {type(resolved_geom).__name__}.")
            
            if not isinstance(geometry, Geometry):
                raise TypeError(f"Object {geom_param!r} is of type {type(geometry).__name__}, expected Geometry with sample_points().")
            positions = geometry.sample_points(N, rng).astype(np.float64)
        elif "position" in params:
            pos_param = params.get("position", [0.0, 0.0, 0.0])
            pos = resolve(pos_param, genome, fields)
            if isinstance(pos, (list, tuple, np.ndarray)):
                pos = np.array(pos, dtype=np.float64)
            else:
                pos = np.array([0.0, 0.0, 0.0], dtype=np.float64)
            positions = np.tile(pos, (N, 1))
        else:
            raise ValueError("seed_cells requires either 'geometry' or 'position' parameter.")
            
        region_param = params.get("region", 0)
        region = int(resolve(region_param, genome, fields))
        
        cell_type_param = params.get("cell_type", 0)
        cell_type = int(resolve(cell_type_param, genome, fields))
        
        # We might want to allow jitter for positions?
        jitter_param = params.get("jitter", 0.0)
        jitter = float(resolve(jitter_param, genome, fields))
        if jitter > 0.0:
            positions += rng.standard_normal(positions.shape) * jitter

        tissue.add_cells(
            N,
            positions=positions,
            region=np.full(N, region, dtype=np.int32),
            cell_type=np.full(N, cell_type, dtype=np.int32)
        )
        return tissue

@register_stage("proliferate")
class Proliferate:
    """Cell division: each alive cell divides with probability `prob` (a `Param`, per cell).

    The parent row stays in place as one daughter; the other daughter is appended, displaced by Gaussian `jitter`
    (space units), with `parent_id`, `clone_id` and the parent's state. Both daughters get `generation` + 1. The
    appended daughter's `birth_stage` is the `birth_stage` Param, or by default one more than the latest
    `birth_stage` of the alive cells, so later-born cells sort after earlier ones (birth order).

    Options (neutral defaults reproduce the plain symmetric division):
    - `max_cells`: upper bound on alive cells; if all divisions would exceed it, a random subset divides so the
      bound holds exactly (a safety bound, not a mechanism).
    - `asymmetric_prob`, `daughter_type`: with probability `asymmetric_prob` a division is asymmetric and the
      appended daughter takes `cell_type = daughter_type`, while the parent row keeps its (progenitor) type, as in
      asymmetric neurogenic divisions of neural progenitors (Götz & Huttner, 2005, Nat Rev Mol Cell Biol).
    - `expression_noise`: std of Gaussian noise added to both daughters' expression channels, clipped at 0.
    - `new_type`: cell type of every appended daughter of a symmetric division.

    Linear O(N) work and allocation, no loops over cells.
    """
    BYTES_PER_CELL = 136

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        M = int(N * min(1.0, float(worst_case(params.get("prob"), 0.5))))
        max_cells = worst_case(params.get("max_cells"), None)
        if max_cells is not None:
            M = min(M, max(0, int(max_cells) - N))
        M = max(1, M)
        # add_cells reallocates every per-cell array (N + M rows); measured peak is 1.1-1.7x this.
        bytes_cost = (N + M) * cls.BYTES_PER_CELL
        ops_cost = N * 10 + M * 20
        return bytes_cost, ops_cost

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0:
            return tissue

        prob_param = params.get("prob", 0.0)
        prob = resolve(prob_param, genome, fields, positions=tissue.positions)
        if np.isscalar(prob):
            prob = np.full(N, prob)
        else:
            prob = np.asarray(prob)

        dividing = (rng.random(N) < prob) & tissue.alive
        div_indices = np.where(dividing)[0]

        max_cells_param = params.get("max_cells", None)
        if max_cells_param is not None:
            room = max(0, int(resolve(max_cells_param, genome, fields)) - int(np.sum(tissue.alive)))
            if len(div_indices) > room:
                div_indices = np.sort(rng.choice(div_indices, size=room, replace=False))

        M = len(div_indices)
        if M == 0:
            return tissue

        parent_positions = tissue.positions[div_indices]
        parent_ids = tissue.cell_id[div_indices]
        parent_clones = tissue.clone_id[div_indices]
        generation = tissue.generation[div_indices] + 1
        birth_param = params.get("birth_stage", None)
        if birth_param is None:
            birth_stage = np.full(M, int(np.max(tissue.birth_stage[tissue.alive])) + 1, dtype=np.int32)
        else:
            birth_stage = np.full(M, int(resolve(birth_param, genome, fields)), dtype=np.int32)

        jitter_param = params.get("jitter", 0.1)
        jitter = resolve(jitter_param, genome, fields, positions=parent_positions)
        if np.isscalar(jitter):
            jitter = np.full((M, 1), jitter)
        elif len(np.asarray(jitter).shape) == 1:
            jitter = np.asarray(jitter)[:, np.newaxis]

        daughter_positions = parent_positions + rng.standard_normal((M, 3)) * jitter

        cell_type = tissue.cell_type[div_indices].copy()
        new_type_param = params.get("new_type", None)
        if new_type_param is not None:
             new_type = resolve(new_type_param, genome, fields, positions=daughter_positions)
             if np.isscalar(new_type):
                 cell_type = np.full(M, int(new_type), dtype=np.int32)
             else:
                 cell_type = np.asarray(new_type, dtype=np.int32)

        asym = resolve(params.get("asymmetric_prob", 0.0), genome, fields, positions=parent_positions)
        if np.any(np.asarray(asym) > 0):
            daughter_type_param = params.get("daughter_type", None)
            if daughter_type_param is None:
                raise ValueError("proliferate: asymmetric_prob > 0 requires daughter_type.")
            daughter_type = np.broadcast_to(np.asarray(
                resolve(daughter_type_param, genome, fields, positions=daughter_positions), dtype=np.int32), (M,))
            asymmetric = rng.random(M) < asym
            cell_type = np.where(asymmetric, daughter_type, cell_type).astype(np.int32)

        K = tissue.expression.shape[1]
        expression = tissue.expression[div_indices].copy() if K > 0 else np.zeros((M, 0), dtype=np.float32)
        noise = float(resolve(params.get("expression_noise", 0.0), genome, fields))
        if noise > 0.0 and K > 0:
            eps = (rng.standard_normal((2, M, K)) * noise).astype(np.float32)
            tissue.expression[div_indices] = np.maximum(expression + eps[0], 0.0)
            expression = np.maximum(expression + eps[1], 0.0)

        tissue.generation[div_indices] = generation

        tissue.add_cells(
            M,
            positions=daughter_positions,
            parent_ids=parent_ids,
            clone_id=parent_clones,
            birth_stage=birth_stage,
            generation=generation,
            cell_type=cell_type,
            region=tissue.region[div_indices].copy(),
            expression=expression,
            sign=tissue.sign[div_indices].copy(),
            mode=tissue.mode[div_indices].copy(),
            shift_v=tissue.shift_v[div_indices].copy(),
            shift_s=tissue.shift_s[div_indices].copy(),
            base_weight=tissue.base_weight[div_indices].copy(),
            conn_radius=tissue.conn_radius[div_indices].copy(),
            conn_prob=tissue.conn_prob[div_indices].copy(),
            burst_period=tissue.burst_period[div_indices].copy(),
            burst_duty=tissue.burst_duty[div_indices].copy(),
            poisson_hz=tissue.poisson_hz[div_indices].copy(),
            refractory=tissue.refractory[div_indices].copy(),
            role=tissue.role[div_indices].copy(),
            compartment=tissue.compartment[div_indices].copy(),
            threshold=tissue.threshold[div_indices].copy()
        )
        return tissue

@register_stage("apoptosis")
class Apoptosis:
    """Density-dependent, trophic, and stochastic cell death.

    Uses CellList for O(N) density-dependent neighbor searches.
    Dense N x N distance matrix is only used as a fast path below documented threshold (N <= 2048).
    """
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        bytes_cost = N * 16
        ops_cost = N * 10
        if "density_radius" in params:
            ops_cost += N * 50
        if "min_inputs" in params or "min_outputs" in params:
            ops_cost += E * 2
        return bytes_cost, ops_cost

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0:
            return tissue

        dying = np.zeros(N, dtype=bool)

        # 1. Random probability
        prob_param = params.get("prob", None)
        if prob_param is not None:
            prob = resolve(prob_param, genome, fields, positions=tissue.positions)
            if np.isscalar(prob):
                prob = np.full(N, prob)
            else:
                prob = np.asarray(prob)
            dying = dying | (rng.random(N) < prob)

        # 2. Density-based
        density_radius_param = params.get("density_radius", None)
        if density_radius_param is not None:
            radius = resolve(density_radius_param, genome, fields, positions=tissue.positions)
            max_density_param = params.get("max_density", 10)
            max_density = resolve(max_density_param, genome, fields, positions=tissue.positions)
            
            r_scalar = float(radius) if np.isscalar(radius) else float(np.max(radius))
            if r_scalar > 0:
                if N <= 2048 and np.isscalar(radius):
                    # Fast vector path below documented threshold (N <= 2048)
                    diff = tissue.positions[:, np.newaxis, :] - tissue.positions[np.newaxis, :, :]
                    dist_sq = np.sum(diff**2, axis=-1)
                    neighbors = np.sum(dist_sq < radius**2, axis=-1) - 1
                else:
                    # O(N) CellList search without dense N x N matrix
                    cl = CellList(tissue.positions, cutoff=r_scalar)
                    src_idx, dst_idx, dists = cl.query_radius(tissue.positions, r_scalar, return_distances=True)
                    if len(src_idx) > 0:
                        if np.isscalar(radius):
                            valid = dists < radius
                        else:
                            valid = dists < np.asarray(radius)[src_idx]
                        non_self = valid & (src_idx != dst_idx)
                        neighbors = np.bincount(src_idx[non_self], minlength=N)
                    else:
                        neighbors = np.zeros(N, dtype=np.int32)

                dying = dying | (neighbors > max_density)

        # 3. Trophic support (based on connectivity)
        min_inputs_param = params.get("min_inputs", None)
        min_outputs_param = params.get("min_outputs", None)
        
        if min_inputs_param is not None or min_outputs_param is not None:
            inputs = np.zeros(N, dtype=np.int32)
            outputs = np.zeros(N, dtype=np.int32)
            
            if len(tissue.connectivity.pre) > 0:
                pre = tissue.connectivity.pre
                post = tissue.connectivity.post
                np.add.at(outputs, pre, 1)
                np.add.at(inputs, post, 1)
                
            if min_inputs_param is not None:
                min_in = resolve(min_inputs_param, genome, fields, positions=tissue.positions)
                dying = dying | (inputs < min_in)
                
            if min_outputs_param is not None:
                min_out = resolve(min_outputs_param, genome, fields, positions=tissue.positions)
                dying = dying | (outputs < min_out)
        
        if np.any(dying):
            tissue.kill(dying)
            tissue.compact()

        return tissue