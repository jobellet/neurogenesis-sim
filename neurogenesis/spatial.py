import numpy as np
import math
from typing import Tuple, Optional, Union

class CellList:
    """
    Fast O(N) 3D neighbour queries in float64 using CSR-style cell-list binning.
    Vectorized cell-by-cell queries without Python loops over query points.
    Never builds a dense N x N distance matrix.
    No scipy dependency.
    """
    def __init__(self, positions: np.ndarray, cutoff: float, box: Optional[Tuple[np.ndarray, np.ndarray]] = None):
        positions = np.asarray(positions, dtype=np.float64)
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError("positions must be a (N, 3) array")
            
        self.n_points = positions.shape[0]
        self.cutoff = float(cutoff)
        if self.cutoff <= 0:
            raise ValueError("cutoff must be positive")
            
        if box is None:
            if self.n_points > 0:
                self.box_min = positions.min(axis=0)
                self.box_max = positions.max(axis=0)
                pad = 1e-5 * max(1.0, float(np.max(self.box_max - self.box_min)))
                self.box_min -= pad
                self.box_max += pad
            else:
                self.box_min = np.zeros(3, dtype=np.float64)
                self.box_max = np.ones(3, dtype=np.float64)
        else:
            self.box_min = np.asarray(box[0], dtype=np.float64)
            self.box_max = np.asarray(box[1], dtype=np.float64)

        self.box_size = self.box_max - self.box_min
        self.box_size = np.maximum(self.box_size, 1e-8)
        
        # Grid dimensions: each cell has width >= cutoff
        self.grid_shape = np.maximum(1, np.floor(self.box_size / self.cutoff).astype(np.int32))
        self.positions = positions
        
        n_cells = int(self.grid_shape[0] * self.grid_shape[1] * self.grid_shape[2])
        if self.n_points > 0:
            rel_pos = positions - self.box_min
            cell_indices = np.floor(rel_pos / self.box_size * self.grid_shape).astype(np.int32)
            cell_indices = np.clip(cell_indices, 0, self.grid_shape - 1)
            
            self.cell_1d = (
                cell_indices[:, 0] * (self.grid_shape[1] * self.grid_shape[2]) +
                cell_indices[:, 1] * self.grid_shape[2] +
                cell_indices[:, 2]
            )
            
            self.sort_idx = np.argsort(self.cell_1d)
            self.sorted_cell_1d = self.cell_1d[self.sort_idx]
            self.sorted_positions = self.positions[self.sort_idx]
            
            counts = np.bincount(self.sorted_cell_1d, minlength=n_cells)
            self.cell_ptr = np.zeros(n_cells + 1, dtype=np.int32)
            self.cell_ptr[1:] = np.cumsum(counts)
        else:
            self.sort_idx = np.zeros(0, dtype=np.int32)
            self.sorted_cell_1d = np.zeros(0, dtype=np.int32)
            self.sorted_positions = np.zeros((0, 3), dtype=np.float64)
            self.cell_ptr = np.zeros(n_cells + 1, dtype=np.int32)

    def query_radius(self, query_points: np.ndarray, radius: float, return_distances: bool = False):
        query_points = np.asarray(query_points, dtype=np.float64)
        if query_points.ndim != 2 or query_points.shape[1] != 3:
            raise ValueError("query_points must be a (M, 3) array")
            
        n_queries = query_points.shape[0]
        if n_queries == 0 or self.n_points == 0:
            if return_distances:
                return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.float64)
            else:
                return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32)

        rel_pos = query_points - self.box_min
        q_cell_indices = np.floor(rel_pos / self.box_size * self.grid_shape).astype(np.int32)
        q_cell_indices = np.clip(q_cell_indices, 0, self.grid_shape - 1)
        
        # 1D cell index for each query point
        q_cell_1d = (
            q_cell_indices[:, 0] * (self.grid_shape[1] * self.grid_shape[2]) +
            q_cell_indices[:, 1] * self.grid_shape[2] +
            q_cell_indices[:, 2]
        )
        
        # Sort queries by cell index to group them into blocks
        q_sort_idx = np.argsort(q_cell_1d)
        sorted_q_cell_1d = q_cell_1d[q_sort_idx]
        sorted_queries = query_points[q_sort_idx]
        
        # Unique query cells and their counts
        unique_q_cells, q_starts, q_counts = np.unique(sorted_q_cell_1d, return_index=True, return_counts=True)
        
        # Search radius in terms of grid cell steps
        cell_size = self.box_size / self.grid_shape
        rx = max(1, int(np.ceil(radius / cell_size[0]))) if self.grid_shape[0] > 1 else 1
        ry = max(1, int(np.ceil(radius / cell_size[1]))) if self.grid_shape[1] > 1 else 1
        rz = max(1, int(np.ceil(radius / cell_size[2]))) if self.grid_shape[2] > 1 else 1
        
        # Precompute relative offsets for 3D stencil
        dx_vals = np.arange(-rx, rx + 1, dtype=np.int32)
        dy_vals = np.arange(-ry, ry + 1, dtype=np.int32)
        dz_vals = np.arange(-rz, rz + 1, dtype=np.int32)
        grid_dx, grid_dy, grid_dz = np.meshgrid(dx_vals, dy_vals, dz_vals, indexing='ij')
        stencil_offsets = np.stack([grid_dx.flatten(), grid_dy.flatten(), grid_dz.flatten()], axis=1)

        src_chunks = []
        dst_chunks = []
        dist_chunks = []
        radius_sq = radius * radius

        # Iterate over unique non-empty query cells (order of hundreds/thousands of cells, NOT N queries!)
        for q_cell, q_start, q_len in zip(unique_q_cells, q_starts, q_counts):
            # Coordinates of this query cell
            cz = q_cell % self.grid_shape[2]
            cy = (q_cell // self.grid_shape[2]) % self.grid_shape[1]
            cx = q_cell // (self.grid_shape[1] * self.grid_shape[2])
            
            # Target neighbour cell coordinates
            target_coords = np.array([cx, cy, cz], dtype=np.int32) + stencil_offsets
            valid_target_mask = (
                (target_coords[:, 0] >= 0) & (target_coords[:, 0] < self.grid_shape[0]) &
                (target_coords[:, 1] >= 0) & (target_coords[:, 1] < self.grid_shape[1]) &
                (target_coords[:, 2] >= 0) & (target_coords[:, 2] < self.grid_shape[2])
            )
            valid_targets = target_coords[valid_target_mask]
            
            target_1d = (
                valid_targets[:, 0] * (self.grid_shape[1] * self.grid_shape[2]) +
                valid_targets[:, 1] * self.grid_shape[2] +
                valid_targets[:, 2]
            )
            
            # Collect points in all valid target cells
            target_starts = self.cell_ptr[target_1d]
            target_ends = self.cell_ptr[target_1d + 1]
            non_empty_targets = target_ends > target_starts
            
            if not np.any(non_empty_targets):
                continue
                
            slice_starts = target_starts[non_empty_targets]
            slice_ends = target_ends[non_empty_targets]
            
            # Concatenate index ranges into an array of sorted indices
            cand_sorted_indices = np.concatenate([np.arange(s, e, dtype=np.int32) for s, e in zip(slice_starts, slice_ends)])
            cand_points = self.sorted_positions[cand_sorted_indices]
            cand_orig_indices = self.sort_idx[cand_sorted_indices]
            
            # Vectorized pairwise computation between all query points in this cell and candidates
            cell_q_pts = sorted_queries[q_start:q_start + q_len]  # (Q, 3)
            cell_q_orig_indices = q_sort_idx[q_start:q_start + q_len]  # (Q,)
            
            # diff shape: (Q, C, 3)
            diff = cell_q_pts[:, np.newaxis, :] - cand_points[np.newaxis, :, :]
            d2 = np.sum(diff * diff, axis=-1)  # (Q, C)
            
            q_matches, c_matches = np.nonzero(d2 <= radius_sq)
            if len(q_matches) > 0:
                src_chunks.append(cell_q_orig_indices[q_matches])
                dst_chunks.append(cand_orig_indices[c_matches])
                if return_distances:
                    dist_chunks.append(np.sqrt(d2[q_matches, c_matches]))

        if not src_chunks:
            if return_distances:
                return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.float64)
            return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32)

        src_indices = np.concatenate(src_chunks)
        dst_indices = np.concatenate(dst_chunks)
        
        # Sort deterministically by (src_idx, dst_idx)
        sort_order = np.lexsort((dst_indices, src_indices))
        src_indices = src_indices[sort_order]
        dst_indices = dst_indices[sort_order]
        
        if return_distances:
            distances = np.concatenate(dist_chunks)[sort_order]
            return src_indices, dst_indices, distances
        return src_indices, dst_indices

    def query_knn(self, query_points: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        query_points = np.asarray(query_points, dtype=np.float64)
        n_queries = query_points.shape[0]
        
        if n_queries == 0:
            return np.zeros((0, k), dtype=np.int32), np.zeros((0, k), dtype=np.float64)
            
        res_idx = np.full((n_queries, k), -1, dtype=np.int32)
        res_dist = np.full((n_queries, k), np.inf, dtype=np.float64)
        
        if self.n_points == 0:
            return res_idx, res_dist
            
        V = max(1e-8, float(np.prod(self.box_size)))
        density = self.n_points / V
        initial_radius = max(self.cutoff, float((k * 3 / (4 * np.pi * max(1e-8, density)))**(1/3)) * 1.5)
        
        # Batch knn search with doubling radius
        radius = initial_radius
        remaining_queries = np.arange(n_queries, dtype=np.int32)
        
        while len(remaining_queries) > 0 and radius < 2.0 * float(np.max(self.box_size)):
            curr_q_pts = query_points[remaining_queries]
            src, dst, dists = self.query_radius(curr_q_pts, radius, return_distances=True)
            
            still_need = []
            if len(src) > 0:
                # Group matches by query index
                unique_src, src_starts, src_counts = np.unique(src, return_index=True, return_counts=True)
                for s, start, count in zip(unique_src, src_starts, src_counts):
                    orig_q_idx = remaining_queries[s]
                    if count >= k or count == self.n_points:
                        # Enough found for this query
                        d_sub = dists[start:start + count]
                        dst_sub = dst[start:start + count]
                        # Sort by distance, breaking ties deterministically by ascending cell index
                        order = np.lexsort((dst_sub, d_sub))
                        n_take = min(k, count)
                        res_idx[orig_q_idx, :n_take] = dst_sub[order[:n_take]]
                        res_dist[orig_q_idx, :n_take] = d_sub[order[:n_take]]
                    else:
                        still_need.append(orig_q_idx)
                        
                found_set = set(remaining_queries[unique_src[src_counts >= k]])
                still_need = [q for q in remaining_queries if q not in found_set]
            else:
                still_need = list(remaining_queries)
                
            remaining_queries = np.array(still_need, dtype=np.int32)
            radius *= 2.0
            
        # Fallback for any leftover queries that couldn't find k (e.g. edge of box)
        for q_idx in remaining_queries:
            # Query entire set
            diff = self.positions - query_points[q_idx]
            dists = np.linalg.norm(diff, axis=-1)
            order = np.lexsort((np.arange(len(dists)), dists))
            n_take = min(k, len(dists))
            res_idx[q_idx, :n_take] = order[:n_take]
            res_dist[q_idx, :n_take] = dists[order[:n_take]]
            
        return res_idx, res_dist

    @classmethod
    def declared_cost(cls, n_points: int, n_queries: int, mean_neighbours: float) -> Tuple[int, int]:
        bytes_cost = int(
            n_points * 3 * 8 * 2 +  # positions, sorted_positions (float64)
            n_points * 4 * 2 +      # sort_idx, cell_1d
            n_queries * mean_neighbours * 8 * 3  # result arrays
        )
        ops_cost = int(
            n_points * (math.log2(max(2, n_points))) + 
            n_queries * mean_neighbours * 27
        )
        return bytes_cost, ops_cost
