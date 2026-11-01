from abc import ABC, abstractmethod
import numpy as np
from typing import Dict, Any, Type, Optional, List, Union

from ..expressions import eval_expr

_FIELD_REGISTRY: Dict[str, Type['Field']] = {}

def register_field(name: str):
    def decorator(cls: Type['Field']):
        _FIELD_REGISTRY[name] = cls
        _FIELD_REGISTRY[name.lower()] = cls
        return cls
    return decorator

class Field(ABC):
    @abstractmethod
    def values(self, points: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def __call__(self, points: np.ndarray) -> np.ndarray:
        return self.values(points)

    def sample(self, points: np.ndarray) -> np.ndarray:
        """Backward compatibility alias for values."""
        return self.values(points)

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        raise NotImplementedError


def field_from_dict(d: Dict[str, Any]) -> Field:
    t = d['type']
    if t not in _FIELD_REGISTRY:
        if t.lower() in _FIELD_REGISTRY:
            t = t.lower()
        else:
            raise ValueError(f"Unknown field type: {t}")
    return _FIELD_REGISTRY[t].from_dict(d)


@register_field('GridField')
class GridField(Field):
    def __init__(self, data: Union[np.ndarray, list], origin: Union[List[float], np.ndarray], spacing: Union[List[float], np.ndarray], method: str = 'nearest'):
        self.data = np.asarray(data)
        self.origin = np.asarray(origin, dtype=float)
        self.spacing = np.asarray(spacing, dtype=float)
        self.method = method

    def values(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points)
        coords = (points - self.origin) / self.spacing
        
        spatial_dims = len(self.spacing)
        
        if self.method == 'nearest':
            indices = np.round(coords).astype(int)
            for i in range(spatial_dims):
                indices[..., i] = np.clip(indices[..., i], 0, self.data.shape[i] - 1)
            
            if spatial_dims == 2:
                return self.data[indices[..., 0], indices[..., 1]]
            elif spatial_dims == 3:
                return self.data[indices[..., 0], indices[..., 1], indices[..., 2]]
            else:
                raise NotImplementedError(f"Nearest sampling not implemented for {spatial_dims}D")
                
        elif self.method in ('trilinear', 'bilinear', 'linear'):
            # Clip coords to valid range
            for i in range(spatial_dims):
                coords[..., i] = np.clip(coords[..., i], 0, self.data.shape[i] - 1)
            
            c0 = np.floor(coords).astype(int)
            c1 = c0 + 1
            for i in range(spatial_dims):
                c1[..., i] = np.clip(c1[..., i], 0, self.data.shape[i] - 1)
                
            d = coords - c0
            
            if spatial_dims == 2:
                x0, y0 = c0[..., 0], c0[..., 1]
                x1, y1 = c1[..., 0], c1[..., 1]
                dx, dy = d[..., 0], d[..., 1]
                
                if self.data.ndim > 2:
                    dx, dy = dx[..., None], dy[..., None]
                
                v00 = self.data[x0, y0]
                v10 = self.data[x1, y0]
                v01 = self.data[x0, y1]
                v11 = self.data[x1, y1]
                
                v0 = v00 * (1 - dx) + v10 * dx
                v1 = v01 * (1 - dx) + v11 * dx
                return v0 * (1 - dy) + v1 * dy
                
            elif spatial_dims == 3:
                x0, y0, z0 = c0[..., 0], c0[..., 1], c0[..., 2]
                x1, y1, z1 = c1[..., 0], c1[..., 1], c1[..., 2]
                dx, dy, dz = d[..., 0], d[..., 1], d[..., 2]
                
                if self.data.ndim > 3:
                    dx, dy, dz = dx[..., None], dy[..., None], dz[..., None]
                
                c000 = self.data[x0, y0, z0]
                c100 = self.data[x1, y0, z0]
                c010 = self.data[x0, y1, z0]
                c110 = self.data[x1, y1, z0]
                c001 = self.data[x0, y0, z1]
                c101 = self.data[x1, y0, z1]
                c011 = self.data[x0, y1, z1]
                c111 = self.data[x1, y1, z1]

                c00 = c000 * (1 - dx) + c100 * dx
                c10 = c010 * (1 - dx) + c110 * dx
                c01 = c001 * (1 - dx) + c101 * dx
                c11 = c011 * (1 - dx) + c111 * dx

                c0 = c00 * (1 - dy) + c10 * dy
                c1 = c01 * (1 - dy) + c11 * dy

                return c0 * (1 - dz) + c1 * dz
            else:
                raise NotImplementedError(f"Linear sampling not implemented for {spatial_dims}D")
        else:
            raise ValueError(f"Unknown sampling method: {self.method}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'GridField',
            'data': self.data.tolist(),
            'origin': self.origin.tolist(),
            'spacing': self.spacing.tolist(),
            'method': self.method
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(d['data'], d['origin'], d['spacing'], d.get('method', 'nearest'))


@register_field('AnalyticField')
class AnalyticField(Field):
    def __init__(self, expr: str):
        self.expr = expr
        
    def values(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points)
        x = points[..., 0]
        y = points[..., 1] if points.shape[-1] > 1 else np.zeros_like(x)
        z = points[..., 2] if points.shape[-1] > 2 else np.zeros_like(x)
        env = {"x": x, "y": y, "z": z, "np": np, "exp": np.exp, "sin": np.sin, "cos": np.cos, "pi": np.pi}
        res = eval_expr(self.expr, env)
        if np.isscalar(res):
            return np.full(points.shape[:-1], res, dtype=float)
        return np.asarray(res, dtype=float)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'AnalyticField', 'expr': self.expr}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(d['expr'])


@register_field('LayerStackField')
class LayerStackField(Field):
    def __init__(self, base_field: Field, thicknesses: List[float], labels: Optional[List[int]] = None):
        self.base_field = base_field
        self.thicknesses = np.array(thicknesses, dtype=float)
        self.boundaries = np.concatenate([[0.0], np.cumsum(self.thicknesses)])
        if labels is None:
            labels = list(range(len(thicknesses)))
        self.labels = np.array(labels, dtype=int)
        
    def values(self, points: np.ndarray) -> np.ndarray:
        depth = self.base_field.values(points)
        
        idx = np.digitize(depth, self.boundaries) - 1
        idx = np.clip(idx, 0, len(self.thicknesses) - 1)
        
        layer_start = self.boundaries[idx]
        layer_thickness = self.thicknesses[idx]
        
        label = self.labels[idx]
        w = np.zeros_like(depth)
        mask = layer_thickness > 0
        w[mask] = (depth[mask] - layer_start[mask]) / layer_thickness[mask]
        w = np.clip(w, 0.0, 1.0)
        
        return np.stack([label, w], axis=-1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'LayerStackField',
            'base_field': self.base_field.to_dict(),
            'thicknesses': self.thicknesses.tolist(),
            'labels': self.labels.tolist()
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        labels = d.get('labels', None)
        return cls(field_from_dict(d['base_field']), d['thicknesses'], labels)

