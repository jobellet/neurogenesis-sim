import numpy as np
from typing import Dict, Any, Type, Union
from .core import Field, register_field, field_from_dict, GridField

@register_field('Add')
class Add(Field):
    def __init__(self, a: Union[Field, float], b: Union[Field, float]):
        self.a = a
        self.b = b

    def sample(self, points: np.ndarray) -> np.ndarray:
        val_a = self.a.sample(points) if isinstance(self.a, Field) else self.a
        val_b = self.b.sample(points) if isinstance(self.b, Field) else self.b
        return val_a + val_b

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'Add',
            'a': self.a.to_dict() if isinstance(self.a, Field) else self.a,
            'b': self.b.to_dict() if isinstance(self.b, Field) else self.b
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        a = field_from_dict(d['a']) if isinstance(d['a'], dict) else d['a']
        b = field_from_dict(d['b']) if isinstance(d['b'], dict) else d['b']
        return cls(a, b)


@register_field('Threshold')
class Threshold(Field):
    def __init__(self, base_field: Field, threshold: float, value_below: float = 0.0, value_above: float = 1.0):
        self.base_field = base_field
        self.threshold = threshold
        self.value_below = value_below
        self.value_above = value_above

    def sample(self, points: np.ndarray) -> np.ndarray:
        vals = self.base_field.sample(points)
        return np.where(vals >= self.threshold, self.value_above, self.value_below)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'Threshold',
            'base_field': self.base_field.to_dict(),
            'threshold': self.threshold,
            'value_below': self.value_below,
            'value_above': self.value_above
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(field_from_dict(d['base_field']), d['threshold'], d.get('value_below', 0.0), d.get('value_above', 1.0))


@register_field('GaussianSmooth')
class GaussianSmooth(Field):
    def __init__(self, base_field: GridField, sigma: float):
        if not isinstance(base_field, GridField):
            raise ValueError("GaussianSmooth requires a GridField as input.")
        self.base_field = base_field
        self.sigma = sigma
        self.smoothed_data = self._smooth(base_field.data, sigma / np.array(base_field.spacing))
        self.smoothed_field = GridField(self.smoothed_data, base_field.origin, base_field.spacing, base_field.method)

    def _smooth(self, data: np.ndarray, sigmas: np.ndarray) -> np.ndarray:
        from scipy.ndimage import gaussian_filter
        return gaussian_filter(data, sigma=sigmas)

    def sample(self, points: np.ndarray) -> np.ndarray:
        return self.smoothed_field.sample(points)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'GaussianSmooth',
            'base_field': self.base_field.to_dict(),
            'sigma': self.sigma
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(field_from_dict(d['base_field']), d['sigma'])


@register_field('DistanceTransform')
class DistanceTransform(Field):
    def __init__(self, bounds: tuple, spacing: Union[float, list], target_points: np.ndarray):
        self.bounds = bounds
        self.spacing = spacing
        self.target_points = target_points
        self.grid_field = self._compute_distance_field()
        
    def _compute_distance_field(self) -> GridField:
        from scipy.spatial import cKDTree
        from .maps import regular_points
        
        points = regular_points(self.bounds, self.spacing)
        tree = cKDTree(self.target_points)
        distances, _ = tree.query(points)
        
        min_b, max_b = self.bounds
        if isinstance(self.spacing, (float, int)):
            spacing = np.array([self.spacing] * len(min_b))
        else:
            spacing = np.array(self.spacing)
            
        grid_shape = np.ceil((max_b - min_b) / spacing).astype(int)
        dist_grid = distances.reshape(*grid_shape)
        
        return GridField(dist_grid, min_b, spacing, method='trilinear')

    def sample(self, points: np.ndarray) -> np.ndarray:
        return self.grid_field.sample(points)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': 'DistanceTransform',
            'bounds': [b.tolist() for b in self.bounds],
            'spacing': self.spacing.tolist() if isinstance(self.spacing, np.ndarray) else self.spacing,
            'target_points': self.target_points.tolist()
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        bounds = (np.array(d['bounds'][0]), np.array(d['bounds'][1]))
        return cls(bounds, d['spacing'], np.array(d['target_points']))

