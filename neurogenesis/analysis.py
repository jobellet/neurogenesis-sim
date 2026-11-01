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


def fi_curve(currents, shift_v=5, shift_s=4, threshold=1024, refractory=3, ticks=1000, model="lif_int"):
    """Firing probability per tick of one isolated neuron for each constant external current (added every tick), each
    current applied to a fresh copy of the neuron starting from rest (models with bistability, such as Hodgkin-Huxley,
    would otherwise depend on the order of the currents): the frequency-current curve of a cell type."""
    from .spiking.batch import simulate_counts
    from .spiking.network import NeuronData, SNNNetwork
    cur = np.asarray(currents, np.int32)
    nets = [SNNNetwork(neurons=[NeuronData(id=0, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, shift_v=shift_v,
                                           shift_s=shift_s, base_weight=1, conn_radius=0.0, conn_prob=0.0, refractory=refractory,
                                           threshold=threshold)], synapses=[]) for _ in cur]
    counts = simulate_counts(nets, [np.asarray([[c]], np.int32) for c in cur], ticks=ticks, model=model)
    return counts[:, 0, 0] / ticks
