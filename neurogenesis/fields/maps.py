import numpy as np
from typing import Tuple, List, Union

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
    
    angles = np.zeros(len(points))
    for p, q in zip(singularities, charges):
        # Contribution from each singularity: q * angle(z - p)
        # Ensure points and p have same shape
        diff = points - p
        angle = np.arctan2(diff[:, 1], diff[:, 0])
        angles += q * angle
        
    angles = angles % np.pi
    
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

