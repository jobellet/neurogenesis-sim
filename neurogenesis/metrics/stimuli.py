"""In-silico stimulus bank: deterministic spatio-temporally correlated natural movies and receptive field currents (M3).

Reference paradigm: Sensorium competition natural video test banks.
Provides deterministic natural-movie input currents for driver regions through spatial receptive fields.
Same movie + same seed produces identical currents. No network downloads.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np


def generate_natural_movie(n_frames: int, height: int = 32, width: int = 32,
                           seed: int = 0, tau_temp: float = 6.0,
                           sigma_spat: float = 2.5) -> np.ndarray:
    """Generates a deterministic spatio-temporally correlated random natural-movie bank in [0, 1].

    - Temporal AR(1) autoregression with time constant `tau_temp` frames.
    - Spatial Gaussian convolution with scale `sigma_spat`.
    Returns array of shape (n_frames, height, width) with float32 values.
    """
    rng = np.random.default_rng(seed)
    alpha = float(np.exp(-1.0 / max(tau_temp, 1e-4)))

    # Spatial kernel
    rad = max(1, int(np.ceil(3.0 * sigma_spat)))
    ax = np.arange(-rad, rad + 1)
    kx = np.exp(-0.5 * (ax / sigma_spat) ** 2)
    kx /= np.sum(kx)

    frames = np.zeros((n_frames, height, width), dtype=np.float32)
    state = rng.standard_normal((height, width))

    for t in range(n_frames):
        noise = rng.standard_normal((height, width))
        state = alpha * state + np.sqrt(1.0 - alpha ** 2) * noise
        # 2D separable Gaussian smoothing
        pad_y = np.pad(state, ((rad, rad), (0, 0)), mode="reflect")
        conv_y = sum(kx[i] * pad_y[i:i + height, :] for i in range(len(kx)))
        pad_x = np.pad(conv_y, ((0, 0), (rad, rad)), mode="reflect")
        conv_xy = sum(kx[j] * pad_x[:, j:j + width] for j in range(len(kx)))
        frames[t] = conv_xy.astype(np.float32)

    # Normalize to [0, 1]
    lo, hi = float(np.percentile(frames, 1)), float(np.percentile(frames, 99))
    if hi > lo:
        frames = np.clip((frames - lo) / (hi - lo), 0.0, 1.0)
    else:
        frames = np.full_like(frames, 0.5)
    return frames.astype(np.float32)


def movie_input_currents(movie: np.ndarray, cell_positions: np.ndarray,
                         rf_sigma: float = 0.08, gain: float = 300.0,
                         bounds: Tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0)
                         ) -> np.ndarray:
    """Projects natural movie frames onto cells through 2D Gaussian receptive fields.

    `movie`: (T, H, W) float array in [0, 1].
    `cell_positions`: (N, 2) or (N, 3) spatial coordinates mapped into [x_min, x_max, y_min, y_max].
    `rf_sigma`: standard deviation of receptive fields in spatial units.
    `gain`: scaling factor converting pixel intensities to integer/float toolbox input currents.
    Returns (T, N) float32 input currents.
    """
    T, H, W = movie.shape
    pos = np.asarray(cell_positions, dtype=np.float64)
    N = len(pos)
    if N == 0 or T == 0:
        return np.zeros((T, N), dtype=np.float32)

    x_min, x_max, y_min, y_max = bounds
    # If positions exceed [0, 1] range and default bounds were given, infer bounds
    if bounds == (0.0, 1.0, 0.0, 1.0) and (np.max(pos[:, 0]) > 1.0 or np.max(pos[:, 1]) > 1.0):
        x_min, x_max = float(np.min(pos[:, 0])), float(np.max(pos[:, 0]))
        y_min, y_max = float(np.min(pos[:, 1])), float(np.max(pos[:, 1]))
        if rf_sigma < 1.0:
            rf_sigma = (x_max - x_min) * 0.15
    # Grid coordinates
    xs = np.linspace(x_min, x_max, W)
    ys = np.linspace(y_min, y_max, H)
    grid_x, grid_y = np.meshgrid(xs, ys)  # (H, W)
    flat_gx = grid_x.ravel()
    flat_gy = grid_y.ravel()

    # Cell RF centers
    cell_x = pos[:, 0, None]
    cell_y = pos[:, 1, None]

    # Precompute Receptive Field weights: (N, H * W)
    dx = flat_gx[None, :] - cell_x
    dy = flat_gy[None, :] - cell_y
    rf_sq = dx ** 2 + dy ** 2
    rf_weights = np.exp(-0.5 * rf_sq / max(rf_sigma ** 2, 1e-8))
    rf_norm = np.sum(rf_weights, axis=1, keepdims=True)
    rf_weights = np.divide(rf_weights, rf_norm, out=np.zeros_like(rf_weights), where=rf_norm > 1e-12)

    # Fast matrix multiply: (T, H * W) @ (H * W, N) -> (T, N)
    movie_flat = movie.reshape(T, H * W).astype(np.float64)
    currents = movie_flat @ rf_weights.T * gain
    return currents.astype(np.float32)
