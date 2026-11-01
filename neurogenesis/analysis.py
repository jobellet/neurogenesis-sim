"""Measures on grown networks."""
from __future__ import annotations

import numpy as np


def nearest_neighbour_regularity(xy) -> float:
    """Nearest-neighbour regularity index of a cell mosaic: mean / s.d. of each cell's distance to its nearest neighbour
    (about 1.9 for random positions; larger for regular mosaics, e.g. retinal cell types)."""
    xy = np.asarray(xy, float)
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1)) + np.diag(np.full(len(xy), np.inf))
    nn = d.min(1)
    return float(nn.mean() / max(nn.std(), 1e-12))
