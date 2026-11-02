"""Geometry primitives (B1): the `Geometry` interface (`contains`, `sample_points`, `to_dict`), `Box`, `Sphere`,
`Ellipsoid`, `Cylinder`, `Sheet2D`, `CurvedSheet`, the set operations `Union` and `Difference`, and the JSON registry
(`register_geometry`, `geometry_from_dict`).
"""
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Type, Callable, Any, Tuple, Optional, List
from neurogenesis.expressions import eval_expr

_GEOMETRY_REGISTRY: Dict[str, Type] = {}

def register_geometry(type_name: str) -> Callable[[Type], Type]:
    """Decorator to register geometry types for dynamic serialization/deserialization."""
    def decorator(cls: Type) -> Type:
        _GEOMETRY_REGISTRY[type_name] = cls
        return cls
    return decorator

def geometry_from_dict(d: dict) -> 'Geometry':
    """Instantiate a Geometry from a dictionary with a registered 'type' field."""
    type_name = d.get("type")
    if not type_name:
        raise ValueError("Geometry dictionary missing required 'type' field")
    if type_name not in _GEOMETRY_REGISTRY:
        raise ValueError(f"Unknown geometry type: {type_name}. Available: {list(_GEOMETRY_REGISTRY.keys())}")
    cls = _GEOMETRY_REGISTRY[type_name]
    return cls.from_dict(d)

class Geometry(ABC):
    @abstractmethod
    def contains(self, points: np.ndarray) -> np.ndarray:
        pass

    @abstractmethod
    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        pass

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """Backward compatibility alias for sample_points."""
        return self.sample_points(n, rng)

    @abstractmethod
    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        pass

    @abstractmethod
    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        pass

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        raise NotImplementedError



@register_geometry('Box')
@register_geometry('box')
class Box(Geometry):
    def __init__(self, center: np.ndarray, size: np.ndarray):
        self.center = np.array(center, dtype=np.float32)
        self.size = np.array(size, dtype=np.float32)

    def contains(self, points: np.ndarray) -> np.ndarray:
        half_size = self.size / 2.0
        return np.all(np.abs(points - self.center) <= half_size, axis=-1)

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        return self.center + self.size * (rng.random((n, 3), dtype=np.float32) - 0.5)

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        half_size = self.size / 2.0
        return self.center - half_size, self.center + half_size

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        return (points - self.center) / self.size + 0.5

    def to_dict(self) -> dict:
        return {
            'type': 'Box',
            'center': self.center.tolist(),
            'size': self.size.tolist()
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d['center'], d['size'])

@register_geometry('Sphere')
@register_geometry('sphere')
class Sphere(Geometry):
    def __init__(self, center: np.ndarray, radius: float):
        self.center = np.array(center, dtype=np.float32)
        self.radius = float(radius)

    def contains(self, points: np.ndarray) -> np.ndarray:
        return np.sum((points - self.center)**2, axis=-1) <= self.radius**2

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        u = rng.random(n, dtype=np.float32)
        v = rng.normal(size=(n, 3)).astype(np.float32)
        v /= np.linalg.norm(v, axis=-1, keepdims=True)
        r = self.radius * u**(1.0/3.0)
        return self.center + v * r[:, np.newaxis]

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        r = np.array([self.radius, self.radius, self.radius], dtype=np.float32)
        return self.center - r, self.center + r

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        return (points - self.center) / (2.0 * self.radius) + 0.5

    def to_dict(self) -> dict:
        return {
            'type': 'Sphere',
            'center': self.center.tolist(),
            'radius': self.radius
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d['center'], d['radius'])

@register_geometry('Ellipsoid')
@register_geometry('ellipsoid')
class Ellipsoid(Geometry):
    def __init__(self, center: np.ndarray, radii: np.ndarray):
        self.center = np.array(center, dtype=np.float32)
        self.radii = np.array(radii, dtype=np.float32)

    def contains(self, points: np.ndarray) -> np.ndarray:
        return np.sum(((points - self.center) / self.radii)**2, axis=-1) <= 1.0

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        u = rng.random(n, dtype=np.float32)
        v = rng.normal(size=(n, 3)).astype(np.float32)
        v /= np.linalg.norm(v, axis=-1, keepdims=True)
        r = u**(1.0/3.0)
        return self.center + v * r[:, np.newaxis] * self.radii

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        return self.center - self.radii, self.center + self.radii

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        return (points - self.center) / (2.0 * self.radii) + 0.5

    def to_dict(self) -> dict:
        return {
            'type': 'Ellipsoid',
            'center': self.center.tolist(),
            'radii': self.radii.tolist()
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d['center'], d['radii'])

@register_geometry('Cylinder')
@register_geometry('cylinder')
class Cylinder(Geometry):
    def __init__(self, p0: np.ndarray, p1: np.ndarray, radius: float):
        self.p0 = np.array(p0, dtype=np.float32)
        self.p1 = np.array(p1, dtype=np.float32)
        self.radius = float(radius)
        self.axis = self.p1 - self.p0
        self.length = np.linalg.norm(self.axis)
        if self.length > 0:
            self.axis_dir = self.axis / self.length
        else:
            self.axis_dir = np.array([0., 0., 1.], dtype=np.float32)

    def contains(self, points: np.ndarray) -> np.ndarray:
        vec = points - self.p0
        h = np.dot(vec, self.axis_dir)
        proj = vec - np.outer(h, self.axis_dir)
        d_sq = np.sum(proj**2, axis=-1)
        return (h >= 0.0) & (h <= self.length) & (d_sq <= self.radius**2)

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        h = rng.random(n, dtype=np.float32) * self.length
        theta = rng.random(n, dtype=np.float32) * 2.0 * np.pi
        r = self.radius * np.sqrt(rng.random(n, dtype=np.float32))
        
        # Create arbitrary basis orthogonal to axis_dir
        if abs(self.axis_dir[0]) > 0.5:
            u = np.array([0, 1, 0], dtype=np.float32)
        else:
            u = np.array([1, 0, 0], dtype=np.float32)
        u -= np.dot(u, self.axis_dir) * self.axis_dir
        u /= np.linalg.norm(u)
        v = np.cross(self.axis_dir, u)
        
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        
        return self.p0 + np.outer(h, self.axis_dir) + np.outer(x, u) + np.outer(y, v)

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        # Bounding box of cylinder:
        # A point is p(t) + r*u(theta) + r*v(theta)
        # Bounding box can be found by evaluating the min/max in each coordinate
        # For each coordinate i, max_i is max_t(p(t)_i) + r * sqrt(1 - axis_dir_i**2)
        t_bounds = np.array([self.p0, self.p1], dtype=np.float32)
        mins = np.min(t_bounds, axis=0) - self.radius * np.sqrt(1.0 - self.axis_dir**2)
        maxs = np.max(t_bounds, axis=0) + self.radius * np.sqrt(1.0 - self.axis_dir**2)
        return mins, maxs

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        vec = points - self.p0
        h = np.dot(vec, self.axis_dir)
        proj = vec - np.outer(h, self.axis_dir)
        d = np.linalg.norm(proj, axis=-1)
        # u is along length (0 to 1)
        # v is radius (0 to 1)
        # w is angle (0 to 1)
        # We need an arbitrary reference vector for angle.
        if abs(self.axis_dir[0]) > 0.5:
            ref = np.array([0, 1, 0], dtype=np.float32)
        else:
            ref = np.array([1, 0, 0], dtype=np.float32)
        ref -= np.dot(ref, self.axis_dir) * self.axis_dir
        ref /= np.linalg.norm(ref)
        ref_v = np.cross(self.axis_dir, ref)
        
        x = np.dot(proj, ref)
        y = np.dot(proj, ref_v)
        angle = np.arctan2(y, x)
        angle = np.where(angle < 0, angle + 2*np.pi, angle)
        
        u = h / self.length if self.length > 0 else np.zeros_like(h)
        v = d / self.radius if self.radius > 0 else np.zeros_like(d)
        w = angle / (2.0 * np.pi)
        
        return np.stack([u, v, w], axis=-1)

    def to_dict(self) -> dict:
        return {
            'type': 'Cylinder',
            'p0': self.p0.tolist(),
            'p1': self.p1.tolist(),
            'radius': self.radius
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d['p0'], d['p1'], d['radius'])

@register_geometry('Sheet2D')
@register_geometry('sheet2d')
class Sheet2D(Geometry):
    def __init__(self, center: np.ndarray, u_vec: np.ndarray, v_vec: np.ndarray, thickness: float):
        self.center = np.array(center, dtype=np.float32)
        self.u_vec = np.array(u_vec, dtype=np.float32)
        self.v_vec = np.array(v_vec, dtype=np.float32)
        self.thickness = float(thickness)
        
        self.n_vec = np.cross(self.u_vec, self.v_vec)
        n_len = np.linalg.norm(self.n_vec)
        if n_len > 0:
            self.n_vec /= n_len
            
        self.u_len = np.linalg.norm(self.u_vec)
        self.v_len = np.linalg.norm(self.v_vec)

    def contains(self, points: np.ndarray) -> np.ndarray:
        vec = points - self.center
        u_proj = np.dot(vec, self.u_vec) / (self.u_len**2)
        v_proj = np.dot(vec, self.v_vec) / (self.v_len**2)
        w_proj = np.dot(vec, self.n_vec)
        
        return (np.abs(u_proj) <= 0.5) & (np.abs(v_proj) <= 0.5) & (np.abs(w_proj) <= self.thickness / 2.0)

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        u = rng.random(n, dtype=np.float32) - 0.5
        v = rng.random(n, dtype=np.float32) - 0.5
        w = rng.random(n, dtype=np.float32) - 0.5
        
        return self.center + np.outer(u, self.u_vec) + np.outer(v, self.v_vec) + np.outer(w * self.thickness, self.n_vec)

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        corners = np.array([
            self.center + 0.5*self.u_vec + 0.5*self.v_vec + 0.5*self.thickness*self.n_vec,
            self.center + 0.5*self.u_vec + 0.5*self.v_vec - 0.5*self.thickness*self.n_vec,
            self.center + 0.5*self.u_vec - 0.5*self.v_vec + 0.5*self.thickness*self.n_vec,
            self.center + 0.5*self.u_vec - 0.5*self.v_vec - 0.5*self.thickness*self.n_vec,
            self.center - 0.5*self.u_vec + 0.5*self.v_vec + 0.5*self.thickness*self.n_vec,
            self.center - 0.5*self.u_vec + 0.5*self.v_vec - 0.5*self.thickness*self.n_vec,
            self.center - 0.5*self.u_vec - 0.5*self.v_vec + 0.5*self.thickness*self.n_vec,
            self.center - 0.5*self.u_vec - 0.5*self.v_vec - 0.5*self.thickness*self.n_vec,
        ], dtype=np.float32)
        return np.min(corners, axis=0), np.max(corners, axis=0)

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        vec = points - self.center
        u_proj = np.dot(vec, self.u_vec) / (self.u_len**2)
        v_proj = np.dot(vec, self.v_vec) / (self.v_len**2)
        w_proj = np.dot(vec, self.n_vec)
        
        u = u_proj + 0.5
        v = v_proj + 0.5
        w = w_proj / self.thickness + 0.5 if self.thickness > 0 else np.full_like(w_proj, 0.5)
        
        return np.stack([u, v, w], axis=-1)

    def to_dict(self) -> dict:
        return {
            'type': 'Sheet2D',
            'center': self.center.tolist(),
            'u_vec': self.u_vec.tolist(),
            'v_vec': self.v_vec.tolist(),
            'thickness': self.thickness
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d['center'], d['u_vec'], d['v_vec'], d['thickness'])

@register_geometry('CurvedSheet')
@register_geometry('curvedsheet')
class CurvedSheet(Geometry):
    def __init__(self, x_expr: str, y_expr: str, z_expr: str, thickness: float):
        self.x_expr = x_expr
        self.y_expr = y_expr
        self.z_expr = z_expr
        self.thickness = float(thickness)
        
        # Grid for surface evaluation to approximate closest points
        u_grid, v_grid = np.meshgrid(np.linspace(0, 1, 50), np.linspace(0, 1, 50))
        u_flat = u_grid.flatten()
        v_flat = v_grid.flatten()
        self.surface_u = u_flat
        self.surface_v = v_flat
        self.surface_points = self._eval_surface(u_flat, v_flat)
        self.surface_normals = self._eval_normals(u_flat, v_flat)

    def _eval_surface(self, u, v):
        env = {"u": u, "v": v, "np": np}
        x = eval_expr(self.x_expr, env)
        y = eval_expr(self.y_expr, env)
        z = eval_expr(self.z_expr, env)
        return np.stack([np.broadcast_to(x, u.shape), 
                         np.broadcast_to(y, u.shape), 
                         np.broadcast_to(z, u.shape)], axis=-1).astype(np.float32)

    def _eval_normals(self, u, v, eps=1e-4):
        du_points = (self._eval_surface(u + eps, v) - self._eval_surface(u - eps, v)) / (2*eps)
        dv_points = (self._eval_surface(u, v + eps) - self._eval_surface(u, v - eps)) / (2*eps)
        n = np.cross(du_points, dv_points)
        n_len = np.linalg.norm(n, axis=-1, keepdims=True)
        return np.where(n_len > 0, n / n_len, np.array([0, 0, 1], dtype=np.float32))

    # Bytes of the (chunk, M, 3) difference array in _closest_points; peak temporary memory stays below
    # 3 x this bound (difference, its square, distances) whatever the number of points.
    _CLOSEST_CHUNK_BYTES = 8 << 20

    def _closest_points(self, points):
        """Index of the nearest surface sample (of M) for each of N points, in chunks of points: O(N M) operations,
        temporary memory below 3 x _CLOSEST_CHUNK_BYTES plus the N indices."""
        points = np.asarray(points)
        M = len(self.surface_points)
        itemsize = np.result_type(points.dtype, self.surface_points.dtype).itemsize
        chunk = max(1, self._CLOSEST_CHUNK_BYTES // (M * 3 * itemsize))
        closest_idx = np.empty(len(points), dtype=np.intp)
        for start in range(0, len(points), chunk):
            diff = points[start:start + chunk, np.newaxis, :] - self.surface_points[np.newaxis, :, :]
            closest_idx[start:start + chunk] = np.argmin(np.sum(diff**2, axis=-1), axis=-1)
        return closest_idx

    def contains(self, points: np.ndarray) -> np.ndarray:
        closest_idx = self._closest_points(points)
        closest_p = self.surface_points[closest_idx]
        closest_n = self.surface_normals[closest_idx]
        vec = points - closest_p
        
        # Check thickness
        w_proj = np.sum(vec * closest_n, axis=-1)
        thickness_cond = np.abs(w_proj) <= self.thickness / 2.0
        
        # We consider it contains if the distance to the surface is approximately just the normal distance.
        # So we check if the tangential distance is small enough (heuristic for being "inside" the boundaries).
        # Actually since u,v are in [0,1], if it maps to the boundary, tangential dist might just be distance to boundary.
        # But a robust way is checking the distance squared is approx equal to normal distance squared.
        tangent_dist_sq = np.sum(vec**2, axis=-1) - w_proj**2
        
        # To be robust, let's just use the nearest u, v. If the nearest u,v are on the exact boundary (0 or 1), 
        # and tangential distance is larger than a small epsilon, we might be outside.
        # A simpler robust approximation: it is contained if tangent_dist_sq is small (less than grid spacing squared)
        grid_spacing = 1.0 / 50.0 * max(1.0, np.max(np.linalg.norm(self.surface_points[0] - self.surface_points[-1])))
        # Note: True containment for parametric surfaces requires Newton-Raphson. 
        # We will use a simplified bounding based on the grid.
        
        return thickness_cond & (tangent_dist_sq < (grid_spacing * 5)**2)

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        u = rng.random(n, dtype=np.float32)
        v = rng.random(n, dtype=np.float32)
        w = rng.random(n, dtype=np.float32) - 0.5
        p = self._eval_surface(u, v)
        n_vec = self._eval_normals(u, v)
        return p + n_vec * (w * self.thickness)[:, np.newaxis]

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        # Approximate using the grid + thickness
        p_plus = self.surface_points + self.surface_normals * (self.thickness / 2.0)
        p_minus = self.surface_points - self.surface_normals * (self.thickness / 2.0)
        all_p = np.concatenate([p_plus, p_minus], axis=0)
        return np.min(all_p, axis=0), np.max(all_p, axis=0)

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        closest_idx = self._closest_points(points)
        u = self.surface_u[closest_idx]
        v = self.surface_v[closest_idx]
        
        closest_p = self.surface_points[closest_idx]
        closest_n = self.surface_normals[closest_idx]
        vec = points - closest_p
        w_proj = np.sum(vec * closest_n, axis=-1)
        w = w_proj / self.thickness + 0.5 if self.thickness > 0 else np.full_like(w_proj, 0.5)
        
        return np.stack([u, v, w], axis=-1)

    def to_dict(self) -> dict:
        return {
            'type': 'CurvedSheet',
            'x_expr': self.x_expr,
            'y_expr': self.y_expr,
            'z_expr': self.z_expr,
            'thickness': self.thickness
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(d['x_expr'], d['y_expr'], d['z_expr'], d['thickness'])

@register_geometry('Union')
@register_geometry('union')
class Union(Geometry):
    def __init__(self, a: Geometry, b: Geometry):
        self.a = a
        self.b = b

    def contains(self, points: np.ndarray) -> np.ndarray:
        return self.a.contains(points) | self.b.contains(points)

    def sample_points(self, n: int, rng: np.random.Generator, max_attempts: int = 100) -> np.ndarray:
        # Rejection sampling from bounding box
        mins, maxs = self.bounding_box()
        box = Box((mins + maxs) / 2.0, maxs - mins)
        
        samples = []
        collected = 0
        attempts = 0
        while collected < n:
            attempts += 1
            if attempts > max_attempts:
                raise RuntimeError(f"Sampling Union exceeded {max_attempts} iterations; geometry may be empty.")
            # We sample more to compensate for rejection
            c_samples = box.sample_points(n, rng)
            mask = self.contains(c_samples)
            valid = c_samples[mask]
            if len(valid) > 0:
                samples.append(valid)
                collected += len(valid)
            
        return np.concatenate(samples, axis=0)[:n]

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        a_min, a_max = self.a.bounding_box()
        b_min, b_max = self.b.bounding_box()
        return np.minimum(a_min, b_min), np.maximum(a_max, b_max)

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        # Fallback for CSG: Just use bounding box local coordinates
        mins, maxs = self.bounding_box()
        box = Box((mins + maxs) / 2.0, maxs - mins)
        return box.local_coordinates(points)

    def to_dict(self) -> dict:
        return {
            'type': 'Union',
            'a': self.a.to_dict(),
            'b': self.b.to_dict()
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(geometry_from_dict(d['a']), geometry_from_dict(d['b']))

@register_geometry('Difference')
@register_geometry('difference')
class Difference(Geometry):
    def __init__(self, a: Geometry, b: Geometry):
        self.a = a
        self.b = b

    def contains(self, points: np.ndarray) -> np.ndarray:
        return self.a.contains(points) & ~self.b.contains(points)

    def sample_points(self, n: int, rng: np.random.Generator, max_attempts: int = 100) -> np.ndarray:
        # Rejection sampling from 'a'
        samples = []
        collected = 0
        attempts = 0
        while collected < n:
            attempts += 1
            if attempts > max_attempts:
                raise RuntimeError(f"Sampling Difference exceeded {max_attempts} iterations; geometry may be empty.")
            c_samples = self.a.sample_points(n, rng)
            mask = ~self.b.contains(c_samples)
            valid = c_samples[mask]
            if len(valid) > 0:
                samples.append(valid)
                collected += len(valid)
            
        return np.concatenate(samples, axis=0)[:n]

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        return self.a.bounding_box()

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        return self.a.local_coordinates(points)

    def to_dict(self) -> dict:
        return {
            'type': 'Difference',
            'a': self.a.to_dict(),
            'b': self.b.to_dict()
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        return cls(geometry_from_dict(d['a']), geometry_from_dict(d['b']))

