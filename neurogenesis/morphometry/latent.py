"""Continuous latent morphology sampling (MorphOcc-style, Weis et al. 2021).

Cortical excitatory cells form a continuous morphological phenotype space rather than discrete types
(Weis, Hansel & Ecker 2021, arXiv:2112.12482; DECEMber / PMC12155019). The toolbox samples morphologies
from a continuous latent space conditioned on context (e.g. layer, laminar depth, age), avoiding fixed stereotypes.

Workflow:
1. Descriptor vector per catalogue cell: TMD persistence image + stratification density profile + scalar morphometrics.
2. Latent space via PCA (SVD); per condition c, fit Gaussian z ~ N(mu_c, Sigma_c) with Ledoit-Wolf diagonal shrinkage.
3. `sample_cells(condition, n, rng)`: draws z from N(mu_c, Sigma_c), evaluates kernel weights against catalogue cells
   (bandwidth = median pairwise latent distance), and produces continuous morphology variations.
4. Optional MorphOcc implicit occupancy adapter behind a lazy import.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from ..arbors import ArborStore, compartment_id
from .features import features
from .tmd import barcodes, persistence_images


def cell_descriptor(store: ArborStore, extent: float = 1.0, grid: int = 10, bins: int = 16) -> np.ndarray:
    """Fixed-length float32 descriptor vector for an arbor store."""
    if store.n_nodes == 0:
        return np.zeros(grid * grid + bins + 4, dtype=np.float32)
    # 1. TMD persistence image (grid x grid)
    bars = barcodes(store, filtration="path")
    c_id = int(store.cell[0]) if store.n_nodes else 0
    p_img = persistence_images(bars, cells=[c_id], grid=grid, bounds=(0.0, extent * 2.0), sigma=1.0)[0]
    # 2. Stratification profile (bins)
    feat = features(store, n_cells=max(1, c_id + 1), extent=extent, bins=bins, normalise=True)
    strat = feat["stratification"][c_id]
    # 3. Scalar morphometrics (4 features): total length, max reach, branch count, stem count
    seg = store.segment_lengths()
    tot_len = float(np.sum(seg))
    rel = store.xyz - store.xyz[0]
    max_reach = float(np.max(np.linalg.norm(rel, axis=1))) if store.n_nodes > 1 else 0.0
    nc = store.children_count()
    branch_count = float(np.sum(nc > 1))
    stem_count = float(nc[0]) if store.n_nodes > 0 else 0.0
    scalars = np.array([tot_len, max_reach, branch_count, stem_count], dtype=np.float32)
    return np.concatenate([p_img, strat, scalars]).astype(np.float32)


def condition_key(cond: Union[Dict[str, Any], Tuple, str]) -> Tuple[Tuple[str, Any], ...]:
    """Canonical hashable key for a condition dictionary."""
    if isinstance(cond, tuple):
        return cond
    if isinstance(cond, str):
        return (("type", cond),)
    # Filter to standard condition fields if present
    items = sorted((str(k), str(v)) for k, v in cond.items() if k != "file")
    return tuple(items)


class ContinuousMorphologySampler:
    """Samples morphologies from a continuous latent space conditioned on cell context."""

    def __init__(self, stores: Sequence[ArborStore], conditions: Sequence[Dict[str, Any]],
                 latent_dim: int = 8, shrinkage: float = 0.2, extent: float = 1.0):
        if len(stores) == 0:
            raise ValueError("sampler requires at least one catalogue arbor store")
        self.stores = list(stores)
        self.conditions = [condition_key(c) for c in conditions]
        self.extent = float(extent)
        self.shrinkage = float(shrinkage)

        # 1. Compute descriptors
        self.descriptors = np.stack([cell_descriptor(s, extent=self.extent) for s in self.stores], axis=0)
        N, D = self.descriptors.shape
        self.mean_desc = np.mean(self.descriptors, axis=0, keepdims=True)
        centered = self.descriptors - self.mean_desc

        # 2. PCA SVD to latent space
        k = min(N, D, max(1, latent_dim))
        if N > 1 and np.any(np.std(self.descriptors, axis=0) > 1e-9):
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            self.V = vt[:k]  # (k, D)
            self.latents = centered @ self.V.T  # (N, k)
        else:
            self.V = np.eye(k, D, dtype=np.float32)
            self.latents = np.zeros((N, k), dtype=np.float32)

        # 3. Kernel bandwidth: median pairwise latent distance
        if N > 1:
            diffs = self.latents[:, None, :] - self.latents[None, :, :]
            pdist = np.linalg.norm(diffs, axis=-1)
            vals = pdist[np.triu_indices(N, k=1)]
            pos_vals = vals[vals > 1e-6]
            self.bandwidth = float(np.median(pos_vals)) if len(pos_vals) > 0 else 1.0
        else:
            self.bandwidth = 1.0
        self.bandwidth = max(self.bandwidth, 1e-4)

        # 4. Group by condition and fit Gaussian with Ledoit-Wolf diagonal shrinkage
        self.condition_models: Dict[Any, Tuple[np.ndarray, np.ndarray]] = {}
        unique_conds = set(self.conditions)
        for cond in unique_conds:
            idx = [i for i, c in enumerate(self.conditions) if c == cond]
            z_c = self.latents[idx]
            mu_c = np.mean(z_c, axis=0)
            if len(idx) > 1:
                cov_emp = np.cov(z_c, rowvar=False)
                if cov_emp.ndim == 0:
                    cov_emp = cov_emp.reshape(1, 1)
                # Ledoit-Wolf diagonal shrinkage
                diag_cov = np.diag(np.diag(cov_emp))
                cov_shrunk = (1.0 - self.shrinkage) * cov_emp + self.shrinkage * diag_cov
                cov_shrunk += 1e-4 * np.eye(cov_shrunk.shape[0])
            else:
                cov_shrunk = np.eye(self.latents.shape[1]) * (self.bandwidth ** 2 * 0.25)
            self.condition_models[cond] = (mu_c, cov_shrunk)

    def _match_condition(self, cond: Union[Dict[str, Any], Tuple, str]) -> Tuple[np.ndarray, np.ndarray]:
        key = condition_key(cond)
        if key in self.condition_models:
            return self.condition_models[key]
        # Partial match if key not found exactly
        if isinstance(cond, dict):
            for ck, model in self.condition_models.items():
                ck_dict = dict(ck)
                if all(ck_dict.get(k) == str(v) for k, v in cond.items() if k in ck_dict):
                    return model
        # Fallback: global population mean and pooled covariance
        all_mu = np.mean(self.latents, axis=0)
        all_cov = np.cov(self.latents, rowvar=False) if len(self.latents) > 1 else np.eye(self.latents.shape[1])
        if all_cov.ndim == 0:
            all_cov = all_cov.reshape(1, 1)
        all_cov = (1.0 - self.shrinkage) * all_cov + self.shrinkage * np.diag(np.diag(all_cov)) + 1e-4 * np.eye(all_cov.shape[0])
        return all_mu, all_cov

    def sample_latent(self, condition: Union[Dict[str, Any], Tuple, str], n: int,
                      rng: np.random.Generator) -> np.ndarray:
        """Draws n points from the condition's latent Gaussian."""
        mu, cov = self._match_condition(condition)
        k = len(mu)
        # Factorize covariance
        try:
            L = np.linalg.cholesky(cov)
        except np.linalg.LinAlgError:
            eigvals, eigvecs = np.linalg.eigh(cov)
            eigvals = np.maximum(eigvals, 1e-6)
            L = eigvecs @ np.diag(np.sqrt(eigvals))
        std_norm = rng.standard_normal((n, k))
        return mu[None, :] + std_norm @ L.T

    def sample_cells(self, condition: Union[Dict[str, Any], Tuple, str], n: int,
                     rng: np.random.Generator, cell_offset: int = 0) -> List[ArborStore]:
        """Draws n morphologies continuously sampled conditioned on context."""
        latents = self.sample_latent(condition, n, rng)
        sampled_stores: List[ArborStore] = []

        for j in range(n):
            z = latents[j]
            # Pairwise distances to catalogue latents
            dists = np.linalg.norm(self.latents - z[None, :], axis=1)
            weights = np.exp(-0.5 * (dists / self.bandwidth) ** 2)
            w_sum = np.sum(weights)
            weights = weights / (w_sum if w_sum > 1e-12 else 1.0)

            # Nearest exemplar provides base topology
            nearest_idx = int(np.argmin(dists))
            base_store = self.stores[nearest_idx]

            # Compute scale factor relative to nearest exemplar from neighbor extents
            base_ext = np.maximum(np.max(np.abs(base_store.xyz - base_store.xyz[0]), axis=0), 1e-4)
            target_ext = np.zeros(3, dtype=np.float64)
            for i, s in enumerate(self.stores):
                s_ext = np.maximum(np.max(np.abs(s.xyz - s.xyz[0]), axis=0), 1e-4)
                target_ext += weights[i] * s_ext

            scale = np.clip(target_ext / base_ext, 0.2, 5.0).astype(np.float32)

            # Deform coordinates around soma
            soma_xyz = base_store.xyz[0]
            rel_xyz = base_store.xyz - soma_xyz
            new_xyz = soma_xyz + rel_xyz * scale[None, :]

            # Create modified ArborStore for the cell
            new_store = ArborStore(
                xyz=new_xyz.astype(np.float32),
                radius=base_store.radius.copy(),
                parent=base_store.parent.copy(),
                compartment=base_store.compartment.copy(),
                cell=np.full(base_store.n_nodes, cell_offset + j, dtype=np.int32),
                labels=dict(base_store.labels)
            )
            sampled_stores.append(new_store)
        return sampled_stores


class MorphOccAdapter:
    """Optional adapter for pretrained MorphOcc implicit occupancy models (PointNet + MLP).

    Loaded lazily when a checkpoint is provided; does not add external dependencies to the core package.
    """

    def __init__(self, checkpoint_path: Union[str, Path]):
        self.checkpoint_path = Path(checkpoint_path)
        self._model = None

    def load(self):
        try:
            import torch  # type: ignore
        except ImportError as e:
            raise ImportError("MorphOcc implicit generation requires PyTorch to be installed") from e
        # Checkpoint loader hook
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"checkpoint not found: {self.checkpoint_path}")
        self._model = torch.load(str(self.checkpoint_path), map_location="cpu")
        return self

    def generate(self, z: np.ndarray, resolution: int = 64) -> ArborStore:
        if self._model is None:
            self.load()
        # Marching cubes / skeleton extraction placeholder behind lazy adapter
        raise NotImplementedError("MorphOcc full mesh-to-SWC extraction requires marching cubes")
