import numpy as np
from typing import Dict, Any, Type, Union, Optional
from .core import Field, register_field, field_from_dict, GridField

MAX_PAIRS = 1 << 20  # largest dense block (pairs of grid points) held at once by the distance ops


def _gaussian_filter(data: np.ndarray, sigmas: np.ndarray) -> np.ndarray:
    """Separable Gaussian smoothing over the first len(sigmas) axes (sigmas in grid cells).

    Matches ``scipy.ndimage.gaussian_filter`` defaults (kernel truncated at 4 sigma, mirror
    boundary 'reflect' = numpy 'symmetric'); sigma 0 leaves an axis unchanged.
    """
    out = np.asarray(data, dtype=float)
    for axis, s in enumerate(np.atleast_1d(sigmas)):
        if s <= 0:
            continue
        r = int(4.0 * s + 0.5)
        k = np.arange(-r, r + 1)
        w = np.exp(-0.5 * (k / s) ** 2)
        w /= w.sum()
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r, r)
        padded = np.pad(out, pad, mode='symmetric')
        n = out.shape[axis]
        acc = np.zeros_like(out)
        for i, wi in enumerate(w):
            acc += wi * np.take(padded, np.arange(i, i + n), axis=axis)
        out = acc
    return out


def _edt_sq(seeds: np.ndarray, spacing: np.ndarray) -> np.ndarray:
    """Squared Euclidean distance from every grid node to the nearest True node of ``seeds``.

    Separable exact transform (Saito & Toriwaki 1994, Pattern Recognition): along each axis,
    d2(x) = min_y [d2(y) + ((x - y) h)^2], evaluated as dense (lines, n, n) min-plus blocks of
    at most MAX_PAIRS entries; O(N * n) operations for N nodes and n nodes per axis. Nodes
    farther than the grid from any seed (or all nodes if there are none) get inf.
    """
    d2 = np.where(seeds, 0.0, np.inf)
    for axis, h in enumerate(spacing):
        moved = np.moveaxis(d2, axis, -1)
        shape = moved.shape
        lines = moved.reshape(-1, shape[-1])
        n = shape[-1]
        idx = np.arange(n)
        D = ((idx[:, None] - idx[None, :]) * float(h)) ** 2  # (x, y)
        out = np.empty_like(lines)
        step = max(1, MAX_PAIRS // (n * n))
        for i in range(0, len(lines), step):
            out[i:i + step] = np.min(lines[i:i + step, None, :] + D[None], axis=-1)
        d2 = np.moveaxis(out.reshape(shape), -1, axis)
    return d2


def _grid_nodes(bounds, spacing):
    """Nodes origin + i * spacing covering [min, max] (inclusive); returns (nodes (N, D), shape, spacing)."""
    lo, hi = np.asarray(bounds[0], dtype=float), np.asarray(bounds[1], dtype=float)
    spacing = np.broadcast_to(np.asarray(spacing, dtype=float), lo.shape).copy()
    shape = tuple(int(np.floor((hi[i] - lo[i]) / spacing[i] + 1e-9)) + 1 for i in range(len(lo)))
    axes = [lo[i] + np.arange(shape[i]) * spacing[i] for i in range(len(lo))]
    nodes = np.stack([m.ravel() for m in np.meshgrid(*axes, indexing='ij')], axis=-1)
    return nodes, shape, spacing

@register_field('Add')
class Add(Field):
    def __init__(self, a: Union[Field, float], b: Union[Field, float]):
        self.a = a
        self.b = b

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        a = self.a.bind(genome) if isinstance(self.a, Field) else self.a
        b = self.b.bind(genome) if isinstance(self.b, Field) else self.b
        return self if a is self.a and b is self.b else Add(a, b)

    def values(self, points: np.ndarray) -> np.ndarray:
        val_a = self.a.values(points) if isinstance(self.a, Field) else self.a
        val_b = self.b.values(points) if isinstance(self.b, Field) else self.b
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

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        base = self.base_field.bind(genome)
        return self if base is self.base_field else Threshold(base, self.threshold, self.value_below, self.value_above)

    def values(self, points: np.ndarray) -> np.ndarray:
        vals = self.base_field.values(points)
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

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        base = self.base_field.bind(genome)
        return self if base is self.base_field else GaussianSmooth(base, self.sigma)

    def _smooth(self, data: np.ndarray, sigmas: np.ndarray) -> np.ndarray:
        return _gaussian_filter(data, sigmas)

    def values(self, points: np.ndarray) -> np.ndarray:
        return self.smoothed_field.values(points)

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
        """Exact nearest-target distance at each grid node, O(G * T) in blocks of MAX_PAIRS pairs."""
        from .maps import _regular_axes, regular_points

        points = regular_points(self.bounds, self.spacing)
        targets = np.asarray(self.target_points, dtype=float)
        distances = np.empty(len(points))
        step = max(1, MAX_PAIRS // max(1, len(targets)))
        for i in range(0, len(points), step):
            diff = points[i:i + step, None, :] - targets[None, :, :]
            distances[i:i + step] = np.sqrt(np.min(np.sum(diff * diff, axis=-1), axis=1))
        
        min_b = self.bounds[0]
        if isinstance(self.spacing, (float, int)):
            spacing = np.array([self.spacing] * len(min_b))
        else:
            spacing = np.array(self.spacing)
            
        grid_shape = [len(a) for a in _regular_axes(self.bounds, self.spacing)]
        dist_grid = distances.reshape(*grid_shape)
        
        return GridField(dist_grid, min_b, spacing, method='trilinear')

    def values(self, points: np.ndarray) -> np.ndarray:
        return self.grid_field.values(points)

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



@register_field('Gradient')
class Gradient(Field):
    """Spatial gradient of a scalar field; values have shape (..., D) for D-dimensional points.

    A GridField base is differentiated on its grid (``np.gradient``: second-order central
    differences inside, one-sided at the edges) and sampled with the base's interpolation;
    any other field by central differences (f(x + h e_i) - f(x - h e_i)) / 2h with h = ``step``.
    """

    def __init__(self, base_field: Field, step: float = 1e-3):
        self.base_field = base_field
        self.step = float(step)
        self._grid = None
        if isinstance(base_field, GridField):
            b = base_field
            if b.data.ndim != len(b.spacing):
                raise ValueError("Gradient needs a scalar GridField")
            g = np.gradient(b.data.astype(float), *b.spacing)
            g = g if isinstance(g, (list, tuple)) else [g]
            self._grid = GridField(np.stack(g, axis=-1), b.origin, b.spacing, b.method)

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        base = self.base_field.bind(genome)
        return self if base is self.base_field else Gradient(base, self.step)

    def values(self, points: np.ndarray) -> np.ndarray:
        if self._grid is not None:
            return self._grid.values(points)
        points = np.asarray(points, dtype=float)
        out = np.empty(points.shape, dtype=float)
        for i in range(points.shape[-1]):
            dp = np.zeros(points.shape[-1])
            dp[i] = self.step
            out[..., i] = (self.base_field.values(points + dp) - self.base_field.values(points - dp)) / (2 * self.step)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'Gradient', 'base_field': self.base_field.to_dict(), 'step': self.step}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(field_from_dict(d['base_field']), d.get('step', 1e-3))


@register_field('DistanceToBoundary')
class DistanceToBoundary(Field):
    """Distance to the boundary of a region, on a grid and sampled trilinearly.

    The region is a Geometry (inside = ``contains``) or a Field with ``label`` (inside =
    ``values == label``, e.g. a LabelField region). Grid nodes are origin + i * spacing over
    ``bounds``; each node's distance is the exact Euclidean distance to the nearest node on
    the other side (``_edt_sq``) minus half the smallest spacing (the boundary lies between
    nodes), so errors are below one spacing. ``signed``: positive inside, negative outside.
    Nodes with no node on the other side within the grid get inf.
    """

    def __init__(self, region: Any, bounds: tuple, spacing: Union[float, list],
                 label: Optional[int] = None, signed: bool = False):
        self.region = region
        self.bounds = (np.asarray(bounds[0], dtype=float), np.asarray(bounds[1], dtype=float))
        self.spacing = spacing
        self.label = label
        self.signed = bool(signed)
        nodes, shape, sp = _grid_nodes(self.bounds, spacing)
        if isinstance(region, Field):
            if label is None:
                raise ValueError("DistanceToBoundary of a field region needs a label")
            inside = np.asarray(region.values(nodes)) == label
        else:
            pts = nodes if nodes.shape[1] == 3 else np.pad(nodes, ((0, 0), (0, 3 - nodes.shape[1])))
            inside = np.asarray(region.contains(pts), dtype=bool)
        inside = inside.reshape(shape)
        d_in = np.sqrt(_edt_sq(~inside, sp))
        d_out = np.sqrt(_edt_sq(inside, sp))
        dist = np.maximum(np.where(inside, d_in, d_out) - 0.5 * float(np.min(sp)), 0.0)
        if self.signed:
            dist = np.where(inside, dist, -dist)
        self.grid_field = GridField(dist, self.bounds[0], sp, method='trilinear')

    def bind(self, genome: Dict[str, Any]) -> 'Field':
        if not isinstance(self.region, Field):
            return self
        region = self.region.bind(genome)
        return self if region is self.region else DistanceToBoundary(region, self.bounds, self.spacing, self.label,
                                                                     self.signed)

    def values(self, points: np.ndarray) -> np.ndarray:
        return self.grid_field.values(np.asarray(points, dtype=float)[..., :len(self.bounds[0])])

    def to_dict(self) -> Dict[str, Any]:
        is_field = isinstance(self.region, Field)
        d = {
            'type': 'DistanceToBoundary',
            'region': self.region.to_dict(),
            'region_kind': 'field' if is_field else 'geometry',
            'bounds': [b.tolist() for b in self.bounds],
            'spacing': np.asarray(self.spacing).tolist(),
            'signed': self.signed,
        }
        if self.label is not None:
            d['label'] = self.label
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        if d.get('region_kind', 'geometry') == 'field':
            region = field_from_dict(d['region'])
        else:
            from ..geometry import geometry_from_dict
            region = geometry_from_dict(d['region'])
        return cls(region, d['bounds'], d['spacing'], d.get('label'), d.get('signed', False))
