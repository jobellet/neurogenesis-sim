"""Cell lists (D1): O(N) fixed-radius neighbour queries without a dense distance matrix.

`CellList` bins points in cubes of side `cutoff` (CSR layout) and answers radius and k-nearest queries by scanning the
neighbouring cells, vectorised in chunks of bounded memory (Allen, 1987, Computer Simulation of Liquids). No scipy.
The default backend is NumPy; `backend="jax"` runs the same queries on the default JAX device in float64, with
identical indices and distances within floating-point tolerance.
"""
import numpy as np
import math
from typing import Tuple, Optional

# Memory budget of one distance chunk: at most CHUNK_PAIRS (query, candidate) pairs are held at once,
# each costing about _BYTES_PER_PAIR bytes of temporaries (indices, coordinates, squared distances).
CHUNK_PAIRS = 1 << 16
_BYTES_PER_PAIR = 48


def _argsort_stable(xp, a):
    """Stable argsort, portable across NumPy (`kind=`) and JAX (`stable=`)."""
    if xp is np:
        return xp.argsort(a, kind='stable')
    return xp.argsort(a, stable=True)


def _concat_ranges(starts, lengths, xp=np):
    """The ranges [starts[i], starts[i] + lengths[i]) concatenated into one int64 array."""
    ends = xp.cumsum(lengths)
    total = int(ends[-1]) if len(ends) else 0
    return xp.arange(total, dtype=xp.int64) + xp.repeat(starts - (ends - lengths), lengths)


class CellList:
    """
    Fast O(N) 3D neighbour queries in float64 using CSR-style cell-list binning.
    Queries are vectorised over all query points and stencil cells, in chunks of bounded memory.
    Never builds a dense N x N distance matrix.
    No scipy dependency.  `backend="jax"` keeps the same CSR layout on the default JAX device
    (float64 enabled) and returns plain NumPy arrays.
    """
    def __init__(self, positions: np.ndarray, cutoff: float, box: Optional[Tuple[np.ndarray, np.ndarray]] = None,
                 backend: str = "numpy"):
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
            # coordinate-major copy (fast per-axis gathers); sorted_positions is a view of it
            self.sorted_coords = np.ascontiguousarray(self.positions[self.sort_idx].T)
            self.sorted_positions = self.sorted_coords.T
            
            counts = np.bincount(self.sorted_cell_1d, minlength=n_cells)
            self.cell_ptr = np.zeros(n_cells + 1, dtype=np.int32)
            self.cell_ptr[1:] = np.cumsum(counts)
        else:
            self.sort_idx = np.zeros(0, dtype=np.int32)
            self.sorted_cell_1d = np.zeros(0, dtype=np.int32)
            self.sorted_coords = np.zeros((3, 0), dtype=np.float64)
            self.sorted_positions = self.sorted_coords.T
            self.cell_ptr = np.zeros(n_cells + 1, dtype=np.int32)

        if backend not in ("numpy", "jax"):
            raise ValueError("backend must be 'numpy' or 'jax'")
        self.backend = backend
        if backend == "jax":
            import jax
            import jax.numpy as jnp
            jax.config.update("jax_enable_x64", True)
            self._xp = jnp
            self.positions = jnp.asarray(self.positions)
            self.sorted_coords = jnp.asarray(self.sorted_coords)
            self.sorted_cell_1d = jnp.asarray(self.sorted_cell_1d)
            self.sort_idx = jnp.asarray(self.sort_idx)
            self.cell_ptr = jnp.asarray(self.cell_ptr)
            self.box_min = jnp.asarray(self.box_min)
            self.box_size = jnp.asarray(self.box_size)
        else:
            self._xp = np

    def _cell_coords(self, points) -> np.ndarray:
        """Integer (x, y, z) grid cell of each point, clipped into the grid."""
        xp = self._xp
        cells = xp.floor((points - self.box_min) / self.box_size * self.grid_shape).astype(xp.int32)
        return xp.clip(cells, 0, self.grid_shape - 1)

    def query_radius(self, query_points: np.ndarray, radius: float, return_distances: bool = False):
        """All pairs (query i, point j) with |q_i - p_j| <= radius, sorted by (i, j).

        Returns (src, dst) or (src, dst, distances).  Each query scans the (2r+1)^3 stencil of grid
        cells around its own cell (r = ceil(radius / cell width)), as (2r+1)^2 contiguous runs of sorted
        points computed once per distinct query cell.  Queries are processed in blocks so that at most
        ``CHUNK_PAIRS`` (query, candidate) pairs are materialised at once (about ``_BYTES_PER_PAIR``
        bytes each), whatever N or the radius.  Cost O(distinct query cells * (2r+1)^2 + M * candidates
        per query); no Python loop over queries or cells.
        """
        xp = self._xp
        query_points = xp.asarray(query_points, dtype=xp.float64)
        if query_points.ndim != 2 or query_points.shape[1] != 3:
            raise ValueError("query_points must be a (M, 3) array")

        n_queries = query_points.shape[0]
        empty = (np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.float64))
        if n_queries == 0 or self.n_points == 0:
            return empty if return_distances else empty[:2]

        # Search radius in grid steps, capped at the grid extent (larger offsets never land in the grid)
        gx, gy, gz = (int(g) for g in self.grid_shape)
        cell_size = self.box_size / self.grid_shape
        steps = [min(max(1, int(np.ceil(radius / cell_size[a]))) if g > 1 else 1, g - 1)
                 for a, g in enumerate((gx, gy, gz))]
        dxy = np.stack([g.ravel() for g in np.meshgrid(np.arange(-steps[0], steps[0] + 1),
                                                      np.arange(-steps[1], steps[1] + 1), indexing='ij')], axis=1)

        q_cells = self._cell_coords(query_points).astype(xp.int64)
        cells, q_cell = xp.unique(q_cells @ xp.array([gy * gz, gz, 1], dtype=xp.int64), return_inverse=True)
        q_cell = q_cell.ravel()
        cx, cy, cz = cells // (gy * gz), (cells // gz) % gy, cells % gz
        z_lo, z_hi = xp.maximum(cz - steps[2], 0), xp.minimum(cz + steps[2], gz - 1)

        # For each distinct query cell, the stencil cells of each (dx, dy) column are consecutive along z,
        # hence one contiguous run of sorted points; keep the non-empty runs (CSR over distinct cells)
        run_start, run_len, n_runs = [], [], []
        block = max(1, CHUNK_PAIRS // len(dxy))
        for c0 in range(0, len(cells), block):
            x = cx[c0:c0 + block, None] + dxy[:, 0]
            y = cy[c0:c0 + block, None] + dxy[:, 1]
            valid = (x >= 0) & (x < gx) & (y >= 0) & (y < gy)
            column = xp.where(valid, x * (gy * gz) + y * gz, 0)
            start = self.cell_ptr[column + z_lo[c0:c0 + block, None]].astype(xp.int64)
            length = xp.where(valid, self.cell_ptr[column + z_hi[c0:c0 + block, None] + 1] - start, 0)
            run_start.append(start[length > 0])
            run_len.append(length[length > 0])
            n_runs.append(xp.count_nonzero(length, axis=1))
        run_start, run_len, n_runs = (xp.concatenate(v) for v in (run_start, run_len, n_runs))
        run_ptr = xp.cumsum(n_runs) - n_runs
        run_cum = xp.concatenate([xp.zeros(1, dtype=run_len.dtype), xp.cumsum(run_len)])
        per_query = (run_cum[run_ptr + n_runs] - run_cum[run_ptr])[q_cell]
        cum = xp.cumsum(per_query)

        # Distances for consecutive query blocks holding at most CHUNK_PAIRS candidates (or one query)
        radius_sq = radius * radius
        src_chunks, dst_chunks, d2_chunks = [], [], []
        lo = 0
        while lo < n_queries:
            done_before = cum[lo - 1] if lo else 0
            hi = max(lo + 1, int(xp.searchsorted(cum, done_before + CHUNK_PAIRS, side='right')))
            if cum[hi - 1] > done_before:
                runs = _concat_ranges(run_ptr[q_cell[lo:hi]], n_runs[q_cell[lo:hi]], xp)
                cand = _concat_ranges(run_start[runs], run_len[runs], xp)
                q = xp.repeat(xp.arange(lo, hi, dtype=xp.int64), per_query[lo:hi])
                for axis in range(3):  # same arithmetic as sum((q - p)**2): (dx² + dy²) + dz²
                    d = xp.repeat(query_points[lo:hi, axis], per_query[lo:hi])
                    d -= self.sorted_coords[axis].take(cand)
                    d *= d
                    if axis == 0:
                        d2 = d
                    else:
                        d2 += d
                keep = d2 <= radius_sq
                src_chunks.append(q[keep])
                dst_chunks.append(self.sort_idx[cand[keep]])
                d2_chunks.append(d2[keep])
            lo = hi

        src_indices = xp.concatenate(src_chunks) if src_chunks else xp.zeros(0, dtype=xp.int64)
        if len(src_indices) == 0:
            return empty if return_distances else empty[:2]
        dst_indices = xp.concatenate(dst_chunks)

        # src is already non-decreasing; order deterministically by (src_idx, dst_idx)
        sort_order = _argsort_stable(xp, src_indices * self.n_points + dst_indices)
        src_indices = np.asarray(src_indices[sort_order])
        dst_indices = np.asarray(dst_indices[sort_order])
        if return_distances:
            return src_indices, dst_indices, np.asarray(xp.sqrt(xp.concatenate(d2_chunks)[sort_order]))
        return src_indices, dst_indices

    def query_knn(self, query_points: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """k nearest points of each query, ordered by (distance, index); missing slots are -1 / inf.

        The search radius starts at the expected k-neighbour radius and doubles for the queries
        that still have fewer than k points inside it (each pass is one vectorised ``query_radius``).
        Queries left after the radius reaches twice the box (fewer than k points overall, or queries
        far outside the box) fall back to brute force over all points, in blocks of at most
        ``CHUNK_PAIRS`` (query, point) pairs, so no dense M x N array is ever built.
        """
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
        remaining = np.arange(n_queries, dtype=np.int64)

        while len(remaining) > 0 and radius < 2.0 * float(np.max(self.box_size)):
            src, dst, dists = self.query_radius(query_points[remaining], radius, return_distances=True)
            counts = np.bincount(src, minlength=len(remaining))
            # Every point within the radius is found, so these queries already hold their exact k nearest
            found = (counts >= k) | (counts == self.n_points)
            # Pairs come sorted by (query, index): pad each found query's distances into a row and
            # stable-sort the rows, which orders them by (distance, index), in blocks of CHUNK_PAIRS
            found_q = np.flatnonzero(found)
            if len(found_q):
                pair_start = np.cumsum(counts) - counts
                width = int(counts[found_q].max())
                cols = np.arange(width)
                rows_per_block = max(1, CHUNK_PAIRS // width)
                for f0 in range(0, len(found_q), rows_per_block):
                    fq = found_q[f0:f0 + rows_per_block]
                    in_row = cols[None, :] < counts[fq, None]
                    pair = np.where(in_row, pair_start[fq, None] + cols[None, :], 0)
                    rows = np.where(in_row, dists[pair], np.inf)
                    order = np.argsort(rows, axis=1, kind='stable')[:, :k]
                    taken = np.take_along_axis(in_row, order, axis=1)
                    pair = np.take_along_axis(pair, order, axis=1)
                    r, c = np.nonzero(taken)
                    res_idx[remaining[fq[r]], c] = dst[pair[r, c]]
                    res_dist[remaining[fq[r]], c] = dists[pair[r, c]]
            remaining = remaining[~found]
            radius *= 2.0

        # Fallback for any leftover queries that couldn't find k (e.g. far outside the box)
        positions = np.asarray(self.positions)
        n_take = min(k, self.n_points)
        block = max(1, CHUNK_PAIRS // self.n_points)
        for b0 in range(0, len(remaining), block):
            q_idx = remaining[b0:b0 + block]
            diff = positions[None, :, :] - query_points[q_idx, None, :]
            dists = np.linalg.norm(diff, axis=-1)
            order = np.argsort(dists, axis=1, kind='stable')[:, :n_take]
            res_idx[q_idx, :n_take] = order
            res_dist[q_idx, :n_take] = np.take_along_axis(dists, order, axis=1)

        return res_idx, res_dist

    @classmethod
    def declared_cost(cls, n_points: int, n_queries: int, mean_neighbours: float) -> Tuple[int, int]:
        """(bytes, operations) of building the list and one radius query at radius = cutoff.

        Candidates scanned: the 27-cell stencil holds about 27 / (4/3 pi) = 6.4 times the neighbours
        within the radius; at most CHUNK_PAIRS of them are held at once.
        """
        n_pairs = n_queries * mean_neighbours
        n_candidates = 6.4 * n_pairs
        bytes_cost = int(
            n_points * 8 * 8 +      # positions and sorted coordinates (float64 x 3), sort_idx, cell ids
            n_queries * 8 * 8 +     # query cells, distinct-cell inverse, per-query candidate counts
            n_pairs * 8 * 8 +       # results and their sort (src, dst, key, order, distances)
            min(n_candidates, CHUNK_PAIRS) * _BYTES_PER_PAIR  # one distance chunk
        )
        ops_cost = int(
            n_points * (math.log2(max(2, n_points))) + 
            n_queries * mean_neighbours * 27
        )
        return bytes_cost, ops_cost
