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

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        """Field with its genome-dependent parameters resolved (itself if it has none)."""
        return self

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


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool)


@register_field('LayerStackField')
class LayerStackField(Field):
    """Layer label and relative depth w in [0, 1] within the layer, from a depth field.

    ``thicknesses`` entries are numbers or Params (``Const``, ``Gene``, ``Expr`` objects or
    their dicts); Gene-controlled thicknesses are resolved by ``bind(genome)``, which
    ``run_schedule`` calls with the run's genome.
    """

    def __init__(self, base_field: Field, thicknesses: List[Any], labels: Optional[List[int]] = None):
        self.base_field = base_field
        self.thickness_params = list(thicknesses)
        if labels is None:
            labels = list(range(len(self.thickness_params)))
        self.labels = np.array(labels, dtype=int)
        numeric = [self._const(t) for t in self.thickness_params]
        if all(t is not None for t in numeric):
            self.thicknesses = np.array(numeric, dtype=float)
            self.boundaries = np.concatenate([[0.0], np.cumsum(self.thicknesses)])
        else:
            self.thicknesses = None
            self.boundaries = None

    @staticmethod
    def _const(t: Any) -> Optional[float]:
        from .. import params as P
        if isinstance(t, dict):
            t = P.param_from_dict(t)
        if isinstance(t, P.Const):
            t = t.value
        return float(t) if _is_number(t) else None

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        from .. import params as P
        resolved = [float(P.resolve(t, genome, {})) for t in self.thickness_params]
        return LayerStackField(self.base_field.bind(genome), resolved, self.labels.tolist())

    def values(self, points: np.ndarray) -> np.ndarray:
        if self.thicknesses is None:
            raise ValueError("LayerStackField thicknesses depend on genes; call bind(genome) first")
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
        from .. import params as P
        return {
            'type': 'LayerStackField',
            'base_field': self.base_field.to_dict(),
            'thicknesses': [float(t) if _is_number(t) else (t if isinstance(t, dict) else P.param_to_dict(t))
                            for t in self.thickness_params],
            'labels': self.labels.tolist()
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        labels = d.get('labels', None)
        return cls(field_from_dict(d['base_field']), d['thicknesses'], labels)


@register_field('VectorField')
class VectorField(Field):
    """Vector field whose components are scalar fields; values have shape (..., n_components)."""

    def __init__(self, components: List[Field]):
        self.components = list(components)

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        return VectorField([c.bind(genome) for c in self.components])

    def values(self, points: np.ndarray) -> np.ndarray:
        return np.stack([np.asarray(c.values(points), dtype=float) for c in self.components], axis=-1)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'VectorField', 'components': [c.to_dict() for c in self.components]}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls([field_from_dict(c) for c in d['components']])


@register_field('LabelField')
class LabelField(Field):
    """Integer labels on a 2D / 3D grid; cell (i, j[, k]) spans origin + [i, i+1) * spacing.

    Sampling is nearest-cell (labels are never interpolated); points outside the grid get
    ``background``. ``names`` optionally maps labels to region names.
    """

    def __init__(self, data: Union[np.ndarray, list], origin: Union[List[float], np.ndarray],
                 spacing: Union[List[float], np.ndarray], background: int = -1,
                 names: Optional[Dict[str, str]] = None):
        self.data = np.asarray(data, dtype=np.int32)
        self.origin = np.asarray(origin, dtype=float)
        self.spacing = np.asarray(spacing, dtype=float)
        self.background = int(background)
        self.names = {str(k): v for k, v in (names or {}).items()}
        if self.data.ndim != len(self.spacing):
            raise ValueError("LabelField data must have one axis per spatial dimension")

    def values(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=float)[..., :self.data.ndim]
        idx = np.floor((points - self.origin) / self.spacing).astype(np.int64)
        shape = np.array(self.data.shape)
        inside = np.all((idx >= 0) & (idx < shape), axis=-1)
        idx = np.clip(idx, 0, shape - 1)
        out = self.data[tuple(np.moveaxis(idx, -1, 0))]
        return np.where(inside, out, self.background).astype(np.int32)

    def to_dict(self) -> Dict[str, Any]:
        d = {'type': 'LabelField', 'data': self.data.tolist(), 'origin': self.origin.tolist(),
             'spacing': self.spacing.tolist(), 'background': self.background}
        if self.names:
            d['names'] = dict(self.names)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(d['data'], d['origin'], d['spacing'], d.get('background', -1), d.get('names'))
