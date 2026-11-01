from __future__ import annotations

import numpy as np
from typing import Dict, Any, Tuple

from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue
from neurogenesis.params import resolve

@register_stage("seed_cells")
class SeedCells:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        # seed_cells adds M cells. We need to estimate M.
        # If N_seed is a Const, we can use it.
        # If it's a field or gene, we might only know the max or assume it's small.
        # We'll just read it if it's a const, else return a rough estimate.
        M = 0
        if "N" in params:
            from neurogenesis.params import Const
            if isinstance(params["N"], Const):
                M = int(params["N"].value)
            elif isinstance(params["N"], (int, float)):
                M = int(params["N"])
            else:
                M = 1000  # fallback
        elif "density" in params:
            # We don't know geometry volume easily here, fallback
            M = 1000
        
        bytes_cost = M * 200  # Rough estimate of per-cell bytes
        ops_cost = M * 10
        return bytes_cost, ops_cost

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N_param = params.get("N", 0)
        N = int(resolve(N_param, genome, fields))
        
        if N <= 0:
            return tissue

        # Get geometry
        geometry_name = params.get("geometry", None)
        geometry = None
        if geometry_name is not None and isinstance(geometry_name, str):
            geometry = fields.get(geometry_name)
        elif "geometry" in params and hasattr(params["geometry"], "sample"):
            geometry = params["geometry"]

        if geometry is not None and hasattr(geometry, "sample"):
            positions = geometry.sample(N, rng).astype(np.float64)
        else:
            # Check if there is an explicit position given, else (0,0,0)
            pos_param = params.get("position", [0.0, 0.0, 0.0])
            pos = resolve(pos_param, genome, fields)
            if isinstance(pos, (list, tuple, np.ndarray)):
                pos = np.array(pos, dtype=np.float64)
            else:
                pos = np.array([0.0, 0.0, 0.0], dtype=np.float64)
            positions = np.tile(pos, (N, 1))
            
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
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        bytes_cost = N * 200
        ops_cost = N * 50
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

        dividing = rng.random(N) < prob
        M = int(np.sum(dividing))
        
        if M == 0:
            return tissue

        div_indices = np.where(dividing)[0]

        parent_positions = tissue.positions[div_indices]
        parent_ids = tissue.cell_id[div_indices]
        parent_clones = tissue.clone_id[div_indices]
        # Treat birth_stage as generation to increment
        new_birth_stage = tissue.birth_stage[div_indices] + 1
        
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

        tissue.add_cells(
            M,
            positions=daughter_positions,
            parent_ids=parent_ids,
            clone_id=parent_clones,
            birth_stage=new_birth_stage,
            cell_type=cell_type,
            region=tissue.region[div_indices].copy(),
            expression=tissue.expression[div_indices].copy() if tissue.expression.shape[1] > 0 else np.zeros((M, 0), dtype=np.float32),
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
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        bytes_cost = N * 4
        ops_cost = N * 10
        if "density_radius" in params:
            ops_cost += N * N  # brute force density cost
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
            
            # brute force distance
            diff = tissue.positions[:, np.newaxis, :] - tissue.positions[np.newaxis, :, :]
            dist_sq = np.sum(diff**2, axis=-1)
            
            if np.isscalar(radius):
                neighbors = np.sum(dist_sq < radius**2, axis=-1) - 1
            else:
                radius_sq = np.asarray(radius)**2
                neighbors = np.sum(dist_sq < radius_sq[:, np.newaxis], axis=-1) - 1
                
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