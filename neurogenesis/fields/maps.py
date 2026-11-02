import numpy as np
from typing import Any, Dict, Tuple, List, Union

from .core import Field, register_field

def regular_points(bounds: Tuple[np.ndarray, np.ndarray], spacing: Union[float, List[float]]) -> np.ndarray:
    min_b, max_b = bounds
    if isinstance(spacing, (float, int)):
        spacing = [spacing] * len(min_b)
        
    grids = []
    for i in range(len(min_b)):
        grids.append(np.arange(min_b[i], max_b[i], spacing[i]))
        
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
    min_b, max_b = bounds
    points = regular_points(bounds, spacing)
    angles = PinwheelField(singularities, charges).values(points)
    
    grid_shape = np.ceil((max_b - min_b) / spacing).astype(int)
    angles_grid = angles.reshape(*grid_shape)
    points_grid = points.reshape(*grid_shape, len(min_b))
    
    return points_grid, angles_grid, singularities

def bandpass_pinwheels(bounds: Tuple[np.ndarray, np.ndarray], spacing: float, k0: float, sigma: float, rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """Generates an orientation map using bandpass filtered noise.
    Returns points grid and angle field.
    """
    min_b, max_b = bounds
    grid_shape = np.ceil((max_b - min_b) / spacing).astype(int)
    
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
