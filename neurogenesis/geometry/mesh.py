import numpy as np
from typing import Dict, Type, Callable, Any, Tuple, Optional, List
from .primitives import Geometry, register_geometry, Box
from .voxel import VoxelMaskGeometry

@register_geometry("mesh")
@register_geometry("Mesh")
class MeshGeometry(Geometry):
    def __init__(self, vertices: np.ndarray, faces: np.ndarray):
        self.vertices = np.array(vertices, dtype=np.float32)
        self.faces = np.array(faces, dtype=np.int32)
        
        # Calculate bounding box
        self._min_bounds = np.min(self.vertices, axis=0)
        self._max_bounds = np.max(self.vertices, axis=0)
        
        self._build_voxel_cache()

    def _build_voxel_cache(self, resolution=32):
        self.voxel_res = resolution
        pitch = (self._max_bounds - self._min_bounds) / resolution
        self.voxel_pitch = np.where(pitch == 0, 1.0, pitch)
        
        x = np.arange(resolution) * self.voxel_pitch[0] + self._min_bounds[0] + self.voxel_pitch[0]/2
        y = np.arange(resolution) * self.voxel_pitch[1] + self._min_bounds[1] + self.voxel_pitch[1]/2
        z = np.arange(resolution) * self.voxel_pitch[2] + self._min_bounds[2] + self.voxel_pitch[2]/2
        
        xv, yv, zv = np.meshgrid(x, y, z, indexing='ij')
        centers = np.stack([xv.flatten(), yv.flatten(), zv.flatten()], axis=-1).astype(np.float32)
        
        # Fast parity for centers:
        ray_dir = np.array([0.7384, 0.4281, 0.5193], dtype=np.float32)
        ray_dir /= np.linalg.norm(ray_dir)
        
        intersections = np.zeros(len(centers), dtype=np.int32)
        v0 = self.vertices[self.faces[:, 0]]
        v1 = self.vertices[self.faces[:, 1]]
        v2 = self.vertices[self.faces[:, 2]]
        
        for i in range(len(self.faces)):
            edge1 = v1[i] - v0[i]
            edge2 = v2[i] - v0[i]
            h = np.cross(ray_dir, edge2)
            a = np.dot(edge1, h)
            if np.abs(a) < 1e-7: continue
                
            f = 1.0 / a
            s = centers - v0[i]
            u = f * np.sum(s * h, axis=-1)
            valid_u = (u >= 0.0) & (u <= 1.0)
            
            q = np.cross(s, edge1)
            v = f * np.sum(q * ray_dir, axis=-1)
            
            valid_v = (v >= 0.0) & (u + v <= 1.0)
            
            t = f * np.sum(edge2 * q, axis=-1)
            
            intersect = valid_u & valid_v & (t > 1e-7)
            intersections[intersect] += 1
            
        mask = (intersections % 2 == 1).reshape((resolution, resolution, resolution))
        self.voxel_cache = VoxelMaskGeometry(mask, self._min_bounds, self.voxel_pitch)

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
        # We can use the voxel cache as a fast-path for points clearly inside or outside.
        # But voxel cache is just a boolean array at `resolution`. It has aliasing at the boundary.
        # For an exact result, we can either do full ray-cast for points that fall near the boundary 
        # (e.g. check a dilated version of the boundary), or just use the ray cast.
        # Wait, the prompt says "Bounding box and occupancy voxel cache." 
        # It does not explicitly mandate using the voxel cache for *everything*, but it should be a cache.
        # Let's just use the voxel cache as an approximation or just use full ray-casting if we need exact.
        # If we need exact containment, we should use ray-casting.
        # To make it fast, we do full ray-casting for all points. If the user has thousands of points, it's ok.
        # Let's do bounding box first.
        in_box = np.all(points >= self._min_bounds, axis=-1) & np.all(points <= self._max_bounds, axis=-1)
        
        ray_dir = np.array([0.7384, 0.4281, 0.5193], dtype=np.float32)
        ray_dir /= np.linalg.norm(ray_dir)
        
        pts_in_box = points[in_box]
        if len(pts_in_box) == 0:
            return in_box
            
        intersections = np.zeros(len(pts_in_box), dtype=np.int32)
        
        v0 = self.vertices[self.faces[:, 0]]
        v1 = self.vertices[self.faces[:, 1]]
        v2 = self.vertices[self.faces[:, 2]]
        
        for i in range(len(self.faces)):
            edge1 = v1[i] - v0[i]
            edge2 = v2[i] - v0[i]
            h = np.cross(ray_dir, edge2)
            a = np.dot(edge1, h)
            if np.abs(a) < 1e-7: continue
                
            f = 1.0 / a
            s = pts_in_box - v0[i]
            u = f * np.sum(s * h, axis=-1)
            valid_u = (u >= 0.0) & (u <= 1.0)
            
            q = np.cross(s, edge1)
            v = f * np.sum(q * ray_dir, axis=-1)
            valid_v = (v >= 0.0) & (u + v <= 1.0)
            
            t = f * np.sum(edge2 * q, axis=-1)
            
            intersect = valid_u & valid_v & (t > 1e-7)
            intersections[intersect] += 1
            
        result = in_box.copy()
        result[in_box] = (intersections % 2) == 1
        return result

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        # Uniform sampling inside the mesh (rejection sampling from bounding box)
        box_size = self._max_bounds - self._min_bounds
        box_center = self._min_bounds + box_size / 2.0
        
        samples = []
        collected = 0
        max_attempts = 100
        attempts = 0
        
        while collected < n:
            attempts += 1
            if attempts > max_attempts:
                raise RuntimeError("Sampling Mesh exceeded max iterations; geometry may be empty.")
            
            # Since sampling is slow, we can use the voxel cache to speed up rejection sampling!
            # Sample from the voxel cache first, then verify with ray-casting!
            c_samples = self.voxel_cache.sample(n * 2, rng)
            mask = self.contains(c_samples)
            valid = c_samples[mask]
            if len(valid) > 0:
                samples.append(valid)
                collected += len(valid)
                
        return np.concatenate(samples, axis=0)[:n]

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
            "faces": self.faces.tolist()
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d["vertices"], d["faces"])
