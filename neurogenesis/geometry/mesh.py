import numpy as np
from typing import Dict, Type, Callable, Any, Tuple, Optional, List
from .primitives import Geometry, register_geometry, Box
from .voxel import VoxelMaskGeometry

@register_geometry("mesh")
@register_geometry("Mesh")
class MeshGeometry(Geometry):
    """Closed triangle mesh: exact point-in-mesh by ray parity plus an occupancy voxel cache.

    Ray parity is vectorised over faces: for a fixed ray direction d, the Moller-Trumbore
    coordinates u, v, t of every (point, face) pair are linear in the point, so they are
    computed as (P, 3) @ (3, F) products. Point and face blocks are chunked so that at most
    ``MAX_PAIRS`` (point, face) pairs are held at once (a few float64 arrays of that size,
    about 8 MB each); cost is O(P * F) operations and O(MAX_PAIRS) memory.
    """

    MAX_PAIRS = 1 << 20
    _RAY_DIR = np.array([0.7384, 0.4281, 0.5193]) / np.linalg.norm([0.7384, 0.4281, 0.5193])

    def __init__(self, vertices: np.ndarray, faces: np.ndarray, resolution: int = 32):
        self.vertices = np.array(vertices, dtype=np.float32)
        self.faces = np.array(faces, dtype=np.int32)

        # Calculate bounding box
        self._min_bounds = np.min(self.vertices, axis=0)
        self._max_bounds = np.max(self.vertices, axis=0)

        self._prepare_faces()
        self._build_voxel_cache(resolution)

    def _prepare_faces(self):
        v = self.vertices.astype(np.float64)
        v0, v1, v2 = v[self.faces[:, 0]], v[self.faces[:, 1]], v[self.faces[:, 2]]
        e1, e2 = v1 - v0, v2 - v0
        d = self._RAY_DIR
        h = np.cross(d, e2)
        a = np.sum(e1 * h, axis=-1)
        keep = np.abs(a) >= 1e-12  # faces parallel to the ray never count
        f = 1.0 / a[keep]
        v0, e1, e2, h = v0[keep], e1[keep], e2[keep], h[keep]
        # u = f (p - v0).h, v = f (p - v0).(e1 x d), t = f (p - v0).(e1 x e2)
        A = np.stack([h, np.cross(e1, d), np.cross(e1, e2)], axis=0) * f[None, :, None]  # (3, F, 3)
        self._lin = np.ascontiguousarray(A.transpose(0, 2, 1))  # (3, 3, F)
        self._off = np.einsum('kfj,fj->kf', A, v0)  # (3, F)

    def _ray_parity(self, points: np.ndarray) -> np.ndarray:
        """True where a ray from each point crosses the surface an odd number of times."""
        pts = np.asarray(points, dtype=np.float64)
        n_faces = self._off.shape[1]
        crossings = np.zeros(len(pts), dtype=np.int64)
        if n_faces == 0 or len(pts) == 0:
            return crossings.astype(bool)
        fb = max(1, min(n_faces, self.MAX_PAIRS // max(1, min(len(pts), self.MAX_PAIRS))))
        pb = max(1, self.MAX_PAIRS // fb)
        for p0 in range(0, len(pts), pb):
            P = pts[p0:p0 + pb]
            for f0 in range(0, n_faces, fb):
                sl = slice(f0, f0 + fb)
                u = P @ self._lin[0][:, sl] - self._off[0, sl]
                v = P @ self._lin[1][:, sl] - self._off[1, sl]
                t = P @ self._lin[2][:, sl] - self._off[2, sl]
                hit = (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (t > 1e-9)
                crossings[p0:p0 + pb] += hit.sum(axis=1)
        return crossings % 2 == 1

    def _build_voxel_cache(self, resolution=32):
        """Occupancy cache: voxel centres inside the mesh, and voxels the surface may cross.

        ``surface_voxels`` marks every voxel overlapping the axis-aligned bounding box of a
        face (a superset of the voxels the surface crosses), built in O(F + resolution**3)
        with a 3D difference array. A voxel partly inside the mesh is either a surface voxel
        or wholly inside (then its centre is inside), so ``mask | surface_voxels`` covers the
        whole volume; ``mask & ~surface_voxels`` voxels are wholly inside.
        """
        self.voxel_res = resolution
        pitch = (self._max_bounds - self._min_bounds) / resolution
        self.voxel_pitch = np.where(pitch == 0, 1.0, pitch).astype(np.float32)

        axes = [(np.arange(resolution) + 0.5) * self.voxel_pitch[i] + self._min_bounds[i] for i in range(3)]
        xv, yv, zv = np.meshgrid(*axes, indexing='ij')
        centers = np.stack([xv.ravel(), yv.ravel(), zv.ravel()], axis=-1)
        mask = self._ray_parity(centers).reshape((resolution,) * 3)
        self.voxel_cache = VoxelMaskGeometry(mask, self._min_bounds, self.voxel_pitch)

        tri = self.vertices[self.faces].astype(np.float64)  # (F, 3, 3)
        pitch64 = self.voxel_pitch.astype(np.float64)
        eps = 1e-6
        lo = np.floor((tri.min(axis=1) - self._min_bounds) / pitch64 - eps).astype(np.int64)
        hi = np.floor((tri.max(axis=1) - self._min_bounds) / pitch64 + eps).astype(np.int64) + 1
        lo, hi = np.clip(lo, 0, resolution), np.clip(hi, 0, resolution)
        diff = np.zeros((resolution + 1,) * 3, dtype=np.int64)
        for cx in (0, 1):
            for cy in (0, 1):
                for cz in (0, 1):
                    sign = (-1) ** (cx + cy + cz)
                    ix = np.where(cx, hi[:, 0], lo[:, 0])
                    iy = np.where(cy, hi[:, 1], lo[:, 1])
                    iz = np.where(cz, hi[:, 2], lo[:, 2])
                    np.add.at(diff, (ix, iy, iz), sign)
        cover = diff.cumsum(0).cumsum(1).cumsum(2)[:resolution, :resolution, :resolution]
        self.surface_voxels = cover > 0

    @classmethod
    def from_obj(cls, filepath: str) -> 'MeshGeometry':
        vertices = []
        faces = []
        with open(filepath, 'r') as f:
            for line in f:
                if line.startswith('v '):
                    vertices.append([float(x) for x in line.strip().split()[1:]])
                elif line.startswith('f '):
                    face = []
                    for part in line.strip().split()[1:]:
                        idx = int(part.split('/')[0])
                        if idx < 0:
                            idx = len(vertices) + idx
                        else:
                            idx -= 1
                        face.append(idx)
                    for i in range(1, len(face) - 1):
                        faces.append([face[0], face[i], face[i+1]])
                        
        return cls(np.array(vertices, dtype=np.float32), np.array(faces, dtype=np.int32))

    @classmethod
    def from_stl(cls, filepath: str) -> 'MeshGeometry':
        # Pure numpy STL parser
        # STL can be ascii or binary. Let's do binary as it is more common.
        with open(filepath, 'rb') as f:
            header = f.read(80)
            if header.startswith(b'solid'):
                # ASCII
                f.seek(0)
                vertices = []
                faces = []
                v_cache = {}
                for line in f:
                    line = line.decode('ascii').strip()
                    if line.startswith('vertex'):
                        parts = line.split()
                        v = (float(parts[1]), float(parts[2]), float(parts[3]))
                        if v not in v_cache:
                            v_cache[v] = len(vertices)
                            vertices.append(v)
                        
                        if len(faces) == 0 or len(faces[-1]) == 3:
                            faces.append([v_cache[v]])
                        else:
                            faces[-1].append(v_cache[v])
                return cls(np.array(vertices, dtype=np.float32), np.array(faces, dtype=np.int32))
            else:
                # Binary
                num_triangles = np.frombuffer(f.read(4), dtype=np.uint32)[0]
                dt = np.dtype([
                    ('normal', np.float32, (3,)),
                    ('v1', np.float32, (3,)),
                    ('v2', np.float32, (3,)),
                    ('v3', np.float32, (3,)),
                    ('attr', np.uint16)
                ])
                data = np.frombuffer(f.read(), dtype=dt)
                
                # To efficiently create vertices and faces from raw triangles:
                # We can just flatten the vertices and create sequential faces.
                # Or use np.unique for compactness.
                all_v = np.vstack([data['v1'], data['v2'], data['v3']])
                vertices, inv = np.unique(all_v, axis=0, return_inverse=True)
                faces = inv.reshape(3, -1).T
                return cls(vertices, faces)

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Exact point-in-mesh test by ray parity (bounding-box prefilter)."""
        points = np.asarray(points)
        in_box = np.all(points >= self._min_bounds, axis=-1) & np.all(points <= self._max_bounds, axis=-1)
        result = in_box.copy()
        if np.any(in_box):
            result[in_box] = self._ray_parity(points[in_box])
        return result

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """Uniform samples in the mesh volume.

        Draws uniform points in voxels of the cache that are inside or crossed by the
        surface (all voxels have the same volume) and keeps those passing the exact
        point-in-mesh test; points in voxels wholly inside are kept without testing.
        """
        candidates = self.voxel_cache.mask | self.surface_voxels
        idx = np.argwhere(candidates)
        if len(idx) == 0 or n <= 0:
            return np.zeros((0, 3), dtype=np.float32)
        interior = (self.voxel_cache.mask & ~self.surface_voxels)[tuple(idx.T)]
        origin, pitch = self._min_bounds, self.voxel_pitch
        samples, collected, accept = [], 0, max(0.05, float(np.mean(interior)))
        for _ in range(1000):
            m = int(np.ceil((n - collected) / accept * 1.2)) + 16
            k = rng.integers(0, len(idx), size=m)
            pts = origin + (idx[k] + rng.random((m, 3), dtype=np.float32)) * pitch
            keep = interior[k].copy()
            if not np.all(keep):
                keep[~keep] = self.contains(pts[~keep])
            accept = max(0.01, float(np.mean(keep)))
            samples.append(pts[keep].astype(np.float32))
            collected += int(keep.sum())
            if collected >= n:
                return np.concatenate(samples, axis=0)[:n]
        raise RuntimeError("Sampling Mesh exceeded max iterations; geometry may be empty.")

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        return self._min_bounds, self._max_bounds

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        size = self._max_bounds - self._min_bounds
        size = np.where(size == 0, 1.0, size)
        return (points - self._min_bounds) / size

    def to_dict(self) -> dict:
        return {
            "type": "mesh",
            "vertices": self.vertices.tolist(),
            "faces": self.faces.tolist(),
            "resolution": self.voxel_res,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d["vertices"], d["faces"], d.get("resolution", 32))
