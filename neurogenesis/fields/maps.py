import numpy as np
from typing import Any, Dict, Tuple, List, Union

from .core import Field, register_field

def _regular_axes(bounds: Tuple[np.ndarray, np.ndarray], spacing: Union[float, List[float]]) -> List[np.ndarray]:
    """Node coordinates along each axis, np.arange(min, max, spacing); their lengths are the grid shape."""
    min_b, max_b = bounds
    if isinstance(spacing, (float, int)):
        spacing = [spacing] * len(min_b)
    return [np.arange(min_b[i], max_b[i], spacing[i]) for i in range(len(min_b))]


def regular_points(bounds: Tuple[np.ndarray, np.ndarray], spacing: Union[float, List[float]]) -> np.ndarray:
    grids = _regular_axes(bounds, spacing)
    mesh = np.meshgrid(*grids, indexing='ij')
    points = np.stack([m.flatten() for m in mesh], axis=-1)
    return points

def jittered_points(bounds: Tuple[np.ndarray, np.ndarray], spacing: Union[float, List[float]], jitter: float, rng: np.random.Generator) -> np.ndarray:
    points = regular_points(bounds, spacing)
    if isinstance(spacing, (float, int)):
        spacing = np.array([spacing] * len(bounds[0]))
    else:
        spacing = np.array(spacing)
        
    offsets = rng.uniform(-jitter, jitter, size=points.shape) * spacing
    points += offsets
    
    # Clip to bounds
    min_b, max_b = bounds
    points = np.clip(points, min_b, max_b)
    return points

def poisson_disc_points(bounds: Tuple[np.ndarray, np.ndarray], radius: float, rng: np.random.Generator, k: int = 30) -> np.ndarray:
    min_b, max_b = bounds
    dims = len(min_b)
    cell_size = radius / np.sqrt(dims)
    
    grid_shape = np.ceil((max_b - min_b) / cell_size).astype(int)
    grid = np.full(grid_shape, -1, dtype=int)
    
    points = []
    active = []
    
    # Initial point
    p0 = min_b + rng.random(dims) * (max_b - min_b)
    points.append(p0)
    active.append(0)
    
    idx = ((p0 - min_b) / cell_size).astype(int)
    grid[tuple(idx)] = 0
    
    while active:
        i = rng.integers(0, len(active))
        curr_idx = active[i]
        curr_p = points[curr_idx]
        
        found = False
        for _ in range(k):
            # Generate random point in annulus [r, 2r]
            direction = rng.normal(size=dims)
            direction /= np.linalg.norm(direction)
            r = rng.uniform(radius, 2 * radius)
            new_p = curr_p + direction * r
            
            if np.any(new_p < min_b) or np.any(new_p >= max_b):
                continue
                
            new_idx = ((new_p - min_b) / cell_size).astype(int)
            
            # Check neighborhood
            valid = True
            slice_bounds = []
            for d in range(dims):
                start = max(0, new_idx[d] - 2)
                end = min(grid_shape[d], new_idx[d] + 3)
                slice_bounds.append(slice(start, end))
                
            neighbor_indices = grid[tuple(slice_bounds)]
            for neighbor_idx in neighbor_indices.flatten():
                if neighbor_idx != -1:
                    neighbor_p = points[neighbor_idx]
                    if np.sum((new_p - neighbor_p)**2) < radius**2:
                        valid = False
                        break
                        
            if valid:
                points.append(new_p)
                active.append(len(points) - 1)
                grid[tuple(new_idx)] = len(points) - 1
                found = True
                break
                
        if not found:
            active.pop(i)
            
    return np.array(points)

def pinwheel_map(bounds: Tuple[np.ndarray, np.ndarray], spacing: float, singularities: np.ndarray, charges: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generates an orientation map from singularities.
    Returns: points grid, angle field (N, M), and pinwheel positions.
    """
    min_b = bounds[0]
    points = regular_points(bounds, spacing)
    angles = PinwheelField(singularities, charges).values(points)
    
    grid_shape = [len(a) for a in _regular_axes(bounds, spacing)]
    angles_grid = angles.reshape(*grid_shape)
    points_grid = points.reshape(*grid_shape, len(min_b))
    
    return points_grid, angles_grid, singularities

def find_pinwheels(angles: np.ndarray, origin: Union[np.ndarray, list], spacing: Union[float, list]) -> Tuple[np.ndarray, np.ndarray]:
    """Pinwheels of an orientation grid (angles in [0, pi) on a regular 2D grid, axis 0 = x): (positions (K, 2), charges).

    For each grid square, the steps of 2 theta around its four corners are wrapped to (-pi, pi] and summed; a winding of
    +-2 pi is a pinwheel of charge +-1/2 placed at the square's centre. O(grid size), no loops.
    """
    a = 2.0 * np.asarray(angles, dtype=float)
    if a.ndim != 2:
        raise ValueError("find_pinwheels needs a 2D angle grid")
    sp = np.broadcast_to(np.asarray(spacing, dtype=float), (2,))
    o = np.asarray(origin, dtype=float)[:2]
    corners = [a[:-1, :-1], a[1:, :-1], a[1:, 1:], a[:-1, 1:]]
    wrap = lambda d: (d + np.pi) % (2 * np.pi) - np.pi
    winding = sum(wrap(corners[(k + 1) % 4] - corners[k]) for k in range(4))
    q = np.round(winding / (2 * np.pi)).astype(int)
    ii, jj = np.nonzero(q)
    pos = o + (np.stack([ii, jj], axis=1) + 0.5) * sp
    return pos.reshape(-1, 2), q[ii, jj] * 0.5


def bandpass_pinwheels(bounds: Tuple[np.ndarray, np.ndarray], spacing: float, k0: float, sigma: float, rng: np.random.Generator,
                       return_pinwheels: bool = False):
    """Generates an orientation map using bandpass filtered noise.
    Returns points grid and angle field; with return_pinwheels (2D bounds only) also the pinwheel positions and
    charges found by `find_pinwheels`.
    """
    min_b = bounds[0]
    grid_shape = [len(a) for a in _regular_axes(bounds, spacing)]
    
    # Generate white noise in frequency domain
    noise1 = rng.normal(size=grid_shape)
    noise2 = rng.normal(size=grid_shape)
    
    fft1 = np.fft.fftn(noise1)
    fft2 = np.fft.fftn(noise2)
    
    # Create frequency grid
    freqs = []
    for d in range(len(grid_shape)):
        freqs.append(np.fft.fftfreq(grid_shape[d], d=spacing))
    freq_grid = np.meshgrid(*freqs, indexing='ij')
    
    k = np.sqrt(sum(f**2 for f in freq_grid))
    
    # Bandpass filter (Gaussian ring)
    filter_kernel = np.exp(-(k - k0)**2 / (2 * sigma**2))
    
    filtered1 = np.fft.ifftn(fft1 * filter_kernel).real
    filtered2 = np.fft.ifftn(fft2 * filter_kernel).real
    
    # Combine into complex field z(r)
    z = filtered1 + 1j * filtered2
    
    # Angles in [0, pi)
    angles = np.angle(z) / 2
    angles = angles % np.pi
    
    points = regular_points(bounds, spacing)
    points_grid = points.reshape(*grid_shape, len(min_b))
    if return_pinwheels:
        pos, q = find_pinwheels(angles, min_b, spacing)
        return points_grid, angles, pos, q
    return points_grid, angles



@register_field('PinwheelField')
class PinwheelField(Field):
    """Orientation angle in [0, pi) around hand-placed pinwheel singularities.

    theta(x) = phase + sum_k q_k atan2(y - y_k, x - x_k) (mod pi), using the first two
    coordinates of the points; a singularity of charge q = +-1/2 rotates the orientation by
    +-pi around it. Orientation maps with pinwheels: Swindale 1996 (Network: Computation in
    Neural Systems); pinwheel density and statistics: Kaschube et al. 2010 (Science).
    """

    def __init__(self, singularities: Union[np.ndarray, list], charges: Union[np.ndarray, list], phase: float = 0.0):
        self.singularities = np.asarray(singularities, dtype=float).reshape(-1, 2)
        self.charges = np.asarray(charges, dtype=float).reshape(-1)
        self.phase = float(phase)
        if len(self.singularities) != len(self.charges):
            raise ValueError("one charge per singularity is required")

    def values(self, points: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=float)
        angles = np.full(points.shape[:-1], self.phase)
        for p, q in zip(self.singularities, self.charges):  # few singularities: loop is O(K * N)
            angles = angles + q * np.arctan2(points[..., 1] - p[1], points[..., 0] - p[0])
        return np.mod(angles, np.pi)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'PinwheelField', 'singularities': self.singularities.tolist(),
                'charges': self.charges.tolist(), 'phase': self.phase}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(d['singularities'], d['charges'], d.get('phase', 0.0))


def pinwheel_charges(field: Field, centres: np.ndarray, radius: float, n_samples: int = 64) -> np.ndarray:
    """Charge of the orientation field around each centre: winding of 2 theta on a circle / (4 pi).

    The circle of ``radius`` around each centre (in the first two coordinates) is sampled at
    ``n_samples`` points; steps of 2 theta are wrapped to (-pi, pi] and summed.
    """
    centres = np.asarray(centres, dtype=float).reshape(-1, 2)
    phi = np.linspace(0.0, 2 * np.pi, n_samples, endpoint=False)
    ring = radius * np.stack([np.cos(phi), np.sin(phi)], axis=-1)
    pts = centres[:, None, :] + ring[None]  # (K, n, 2)
    two_theta = 2.0 * np.asarray(field.values(pts), dtype=float)
    steps = np.diff(np.concatenate([two_theta, two_theta[:, :1]], axis=1), axis=1)
    steps = (steps + np.pi) % (2 * np.pi) - np.pi
    return steps.sum(axis=1) / (4 * np.pi)


@register_field('PointSetField')
class PointSetField(Field):
    """A point set (B4) as a field: `values` is the distance from each query point to the nearest point of the set.

    Points are given (`points`, (M, d) with d <= 3, missing coordinates 0) or generated deterministically from a
    pattern: `pattern` "regular", "jittered" or "poisson_disc" with `bounds`, `spacing` / `jitter` / `radius` and
    `seed`. `seed_cells` accepts it as `points`; e.g. blob centres or pinwheel centres. Nearest-point search through
    the cell list (O(M + queries)).
    """

    def __init__(self, points: Any = None, pattern: str = None, bounds: Any = None, spacing: Any = None,
                 jitter: float = 0.0, radius: float = None, seed: int = 0):
        self.pattern, self.bounds, self.spacing, self.jitter, self.radius, self.seed = pattern, bounds, spacing, jitter, radius, seed
        if points is None:
            if pattern is None:
                raise ValueError("PointSetField needs points or a pattern")
            rng = np.random.default_rng(seed)
            b = (np.asarray(bounds[0], dtype=float), np.asarray(bounds[1], dtype=float))
            if pattern == "regular":
                points = regular_points(b, spacing)
            elif pattern == "jittered":
                points = jittered_points(b, spacing, jitter, rng)
            elif pattern == "poisson_disc":
                points = poisson_disc_points(b, radius, rng)
            else:
                raise ValueError(f"unknown point pattern {pattern!r}")
            self._generated = True
        else:
            self._generated = False
        pts = np.atleast_2d(np.asarray(points, dtype=float))
        if pts.size and pts.shape[1] < 3:
            pts = np.concatenate([pts, np.zeros((len(pts), 3 - pts.shape[1]))], axis=1)
        self.points = pts.reshape(-1, 3)

    def values(self, points: np.ndarray) -> np.ndarray:
        from neurogenesis.spatial import CellList
        q = np.asarray(points, dtype=float)
        shape = q.shape[:-1]
        q = q.reshape(-1, q.shape[-1])
        if q.shape[1] < 3:
            q = np.concatenate([q, np.zeros((len(q), 3 - q.shape[1]))], axis=1)
        if len(self.points) == 0:
            return np.full(shape, np.inf)
        lo, hi = self.points.min(0), self.points.max(0)
        cutoff = max(float(np.max(hi - lo)) / max(1.0, len(self.points) ** (1 / 3)), 1e-6)
        _, d = CellList(self.points, cutoff).query_knn(q, 1)
        return d[:, 0].reshape(shape)

    def to_dict(self) -> Dict[str, Any]:
        if self._generated:
            d = {'type': 'PointSetField', 'pattern': self.pattern, 'bounds': np.asarray(self.bounds, dtype=float).tolist(),
                 'seed': self.seed}
            for k in ('spacing', 'jitter', 'radius'):
                v = getattr(self, k)
                if v is not None:
                    d[k] = v
            return d
        return {'type': 'PointSetField', 'points': self.points.tolist()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Field':
        return cls(points=d.get('points'), pattern=d.get('pattern'), bounds=d.get('bounds'), spacing=d.get('spacing'),
                   jitter=d.get('jitter', 0.0), radius=d.get('radius'), seed=d.get('seed', 0))
