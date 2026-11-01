import numpy as np
import math

class CellList:
    """
    Fast O(N) 3D neighbour queries in float32 using CSR-style cell-list binning.
    Never builds a dense N x N distance matrix.
    No scipy dependency.
    """
    def __init__(self, positions: np.ndarray, cutoff: float, box: tuple | None = None):
        positions = np.asarray(positions, dtype=np.float32)
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
                # add a tiny padding
                pad = 1e-5 * max(1.0, float(np.max(self.box_max - self.box_min)))
                self.box_min -= pad
                self.box_max += pad
            else:
                self.box_min = np.zeros(3, dtype=np.float32)
                self.box_max = np.ones(3, dtype=np.float32)
        else:
            self.box_min = np.asarray(box[0], dtype=np.float32)
            self.box_max = np.asarray(box[1], dtype=np.float32)

        self.box_size = self.box_max - self.box_min
        # Handle degenerate boxes
        self.box_size = np.maximum(self.box_size, 1e-8)
        
        # Grid dimensions
        self.grid_shape = np.maximum(1, np.floor(self.box_size / self.cutoff).astype(np.int32))
        
        # Store original positions
        self.positions = positions
        
        if self.n_points > 0:
            # Map points to grid cells
            rel_pos = positions - self.box_min
            cell_indices = np.floor(rel_pos / self.box_size * self.grid_shape).astype(np.int32)
            cell_indices = np.clip(cell_indices, 0, self.grid_shape - 1)
            
            # Linear 1D cell index
            self.cell_1d = (
                cell_indices[:, 0] * (self.grid_shape[1] * self.grid_shape[2]) +
                cell_indices[:, 1] * self.grid_shape[2] +
                cell_indices[:, 2]
            )
            
            # Sort points by cell index (this provides spatial locality)
            self.sort_idx = np.argsort(self.cell_1d)
            self.sorted_cell_1d = self.cell_1d[self.sort_idx]
            self.sorted_positions = self.positions[self.sort_idx]
            
            # CSR-like row pointers for cells
            n_cells = self.grid_shape[0] * self.grid_shape[1] * self.grid_shape[2]
            # bincount gives counts per cell
            counts = np.bincount(self.sorted_cell_1d, minlength=n_cells)
            self.cell_ptr = np.zeros(n_cells + 1, dtype=np.int32)
            self.cell_ptr[1:] = np.cumsum(counts)
        else:
            self.sort_idx = np.zeros(0, dtype=np.int32)
            self.sorted_cell_1d = np.zeros(0, dtype=np.int32)
            self.sorted_positions = np.zeros((0, 3), dtype=np.float32)
            n_cells = self.grid_shape[0] * self.grid_shape[1] * self.grid_shape[2]
            self.cell_ptr = np.zeros(n_cells + 1, dtype=np.int32)

    def _get_neighbour_cells(self, cx: int, cy: int, cz: int):
        # yields the linear indices of neighbouring cells, taking care of boundaries
        # Not using periodic boundary conditions based on description, but could easily add
        x_min = max(0, cx - 1)
        x_max = min(self.grid_shape[0] - 1, cx + 1)
        y_min = max(0, cy - 1)
        y_max = min(self.grid_shape[1] - 1, cy + 1)
        z_min = max(0, cz - 1)
        z_max = min(self.grid_shape[2] - 1, cz + 1)
        
        res = []
        for x in range(x_min, x_max + 1):
            x_offset = x * (self.grid_shape[1] * self.grid_shape[2])
            for y in range(y_min, y_max + 1):
                y_offset = x_offset + y * self.grid_shape[2]
                for z in range(z_min, z_max + 1):
                    res.append(y_offset + z)
        return res

    def query_radius(self, query_points: np.ndarray, radius: float, return_distances: bool = False):
        query_points = np.asarray(query_points, dtype=np.float32)
        if query_points.ndim != 2 or query_points.shape[1] != 3:
            raise ValueError("query_points must be a (M, 3) array")
            
        n_queries = query_points.shape[0]
        if n_queries == 0 or self.n_points == 0:
            if return_distances:
                return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.float32)
            else:
                return np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32)
                
        # This implementation uses the original sorting to construct chunks of distance calculations
        # To make it efficient and strictly O(N), we iterate query cells and their neighbours
        
        rel_pos = query_points - self.box_min
        q_cell_indices = np.floor(rel_pos / self.box_size * self.grid_shape).astype(np.int32)
        q_cell_indices = np.clip(q_cell_indices, 0, self.grid_shape - 1)
        
        # radius might be larger than cutoff, we need to search further cells
        # how many cells to search in each direction
        cx_radius = max(1, int(np.ceil(radius / (self.box_size[0] / self.grid_shape[0])))) if self.grid_shape[0] > 1 else 1
        cy_radius = max(1, int(np.ceil(radius / (self.box_size[1] / self.grid_shape[1])))) if self.grid_shape[1] > 1 else 1
        cz_radius = max(1, int(np.ceil(radius / (self.box_size[2] / self.grid_shape[2])))) if self.grid_shape[2] > 1 else 1
        
        # For true efficiency and no O(M*N) matrices, we can do block vectorized distance computations
        src_indices = []
        dst_indices = []
        distances = []
        
        radius_sq = radius * radius
        
        for i in range(n_queries):
            cx, cy, cz = q_cell_indices[i]
            
            x_min = max(0, cx - cx_radius)
            x_max = min(self.grid_shape[0] - 1, cx + cx_radius)
            y_min = max(0, cy - cy_radius)
            y_max = min(self.grid_shape[1] - 1, cy + cy_radius)
            z_min = max(0, cz - cz_radius)
            z_max = min(self.grid_shape[2] - 1, cz + cz_radius)
            
            # collect all points in the neighbour cells
            for x in range(x_min, x_max + 1):
                x_offset = x * (self.grid_shape[1] * self.grid_shape[2])
                for y in range(y_min, y_max + 1):
                    y_offset = x_offset + y * self.grid_shape[2]
                    for z in range(z_min, z_max + 1):
                        cell_idx = y_offset + z
                        
                        start_idx = self.cell_ptr[cell_idx]
                        end_idx = self.cell_ptr[cell_idx + 1]
                        
                        if start_idx < end_idx:
                            # these are indices into the sorted array
                            cell_pts = self.sorted_positions[start_idx:end_idx]
                            
                            # calculate distances
                            diff = cell_pts - query_points[i]
                            dist_sq = np.sum(diff * diff, axis=1)
                            
                            mask = dist_sq <= radius_sq
                            if np.any(mask):
                                matched_local = np.where(mask)[0]
                                matched_sorted = start_idx + matched_local
                                # map back to original indices
                                matched_orig = self.sort_idx[matched_sorted]
                                
                                src_indices.extend([i] * len(matched_orig))
                                dst_indices.extend(matched_orig.tolist())
                                if return_distances:
                                    distances.extend(np.sqrt(dist_sq[mask]).tolist())
                                    
        src_indices = np.array(src_indices, dtype=np.int32)
        dst_indices = np.array(dst_indices, dtype=np.int32)
        
        if len(src_indices) > 0:
            # Sort deterministically by (src_idx, dst_idx)
            sort_order = np.lexsort((dst_indices, src_indices))
            src_indices = src_indices[sort_order]
            dst_indices = dst_indices[sort_order]
            
            if return_distances:
                distances = np.array(distances, dtype=np.float32)
                distances = distances[sort_order]
                return src_indices, dst_indices, distances
            
        if return_distances:
            distances = np.array(distances, dtype=np.float32)
            return src_indices, dst_indices, distances
        return src_indices, dst_indices

    def query_knn(self, query_points: np.ndarray, k: int):
        # Finds k nearest neighbours for each query point.
        # Shape: (M, k)
        query_points = np.asarray(query_points, dtype=np.float32)
        n_queries = query_points.shape[0]
        
        if n_queries == 0:
            return np.zeros((0, k), dtype=np.int32), np.zeros((0, k), dtype=np.float32)
            
        # Start with a search radius based on uniform density assumption
        # Volume of box = V. N points. Density = N/V.
        # Volume of sphere = 4/3 pi r^3. Expected points = (4/3 pi r^3) * (N/V)
        # We want k points, so r = (k * V / N / (4/3 pi))^(1/3)
        if self.n_points == 0:
            # fill with -1 or similar for "no neighbour found"
            res_idx = np.full((n_queries, k), -1, dtype=np.int32)
            res_dist = np.full((n_queries, k), np.inf, dtype=np.float32)
            return res_idx, res_dist
            
        V = max(1e-8, np.prod(self.box_size))
        density = self.n_points / V
        # Initial guess radius, padded a bit
        initial_radius = max(self.cutoff, float((k * 3 / (4 * np.pi * density))**(1/3)) * 1.5)
        
        res_idx = np.full((n_queries, k), -1, dtype=np.int32)
        res_dist = np.full((n_queries, k), np.inf, dtype=np.float32)
        
        for i in range(n_queries):
            radius = initial_radius
            found_enough = False
            
            # exponential backoff if not enough points found
            while not found_enough:
                src, dst, dists = self.query_radius(query_points[i:i+1], radius, return_distances=True)
                
                if len(dst) >= k or len(dst) == self.n_points:
                    # we have enough (or all possible)
                    if len(dst) > 0:
                        # sort by distance
                        sort_idx = np.argsort(dists)
                        n_take = min(k, len(dst))
                        res_idx[i, :n_take] = dst[sort_idx[:n_take]]
                        res_dist[i, :n_take] = dists[sort_idx[:n_take]]
                    found_enough = True
                else:
                    radius *= 2.0  # grow radius and try again
                    
        return res_idx, res_dist

    @classmethod
    def declared_cost(cls, n_points: int, n_queries: int, mean_neighbours: float) -> tuple[int, int]:
        """
        Returns (bytes, ops).
        """
        # Memory:
        # Original positions (N*3*4), sorted positions (N*3*4)
        # sort_idx (N*4), cell_1d (N*4)
        # Cell ptr: depends on grid size, but roughly proportional to N in a well-sized grid
        # Result arrays: roughly n_queries * mean_neighbours * 4 bytes per array (src, dst, dists)
        bytes_cost = int(
            n_points * 3 * 4 * 2 +  # positions, sorted_positions
            n_points * 4 * 2 +      # sort_idx, cell_1d
            n_queries * mean_neighbours * 4 * 3  # result arrays
        )
        
        # Ops:
        # Building grid: N ops
        # Sorting: N log N
        # Queries: n_queries * mean_neighbours (actually more like n_queries * 27 * points_per_cell)
        # Let's say ops = N * log2(N) + n_queries * 27 * mean_neighbours
        ops_cost = int(
            n_points * (math.log2(max(2, n_points))) + 
            n_queries * mean_neighbours * 27
        )
        
        return bytes_cost, ops_cost

