"""Voxel-mask geometries (B2): `VoxelMaskGeometry`, a boolean occupancy grid with an origin and a voxel pitch."""
import numpy as np
from typing import Dict, Type, Callable, Any, Tuple, Optional, List
from .primitives import Geometry, register_geometry, Box

@register_geometry("voxel_mask")
@register_geometry("VoxelMask")
class VoxelMaskGeometry(Geometry):
    """Occupancy mask on an axis-aligned voxel grid; voxel (i, j, k) spans origin + [i, i+1) * pitch."""

    def __init__(self, mask: np.ndarray, origin: np.ndarray, pitch: np.ndarray, source: Optional[str] = None):
        self.source = source
        self.mask = np.array(mask, dtype=bool)
        self.origin = np.array(origin, dtype=np.float32)
        self.pitch = np.array(pitch, dtype=np.float32)
        
        # Dimensions
        self.shape = np.array(self.mask.shape, dtype=np.int32)
        
        # Bounding box
        self._min_bounds = self.origin
        self._max_bounds = self.origin + self.shape * self.pitch

    def contains(self, points: np.ndarray) -> np.ndarray:
        # Map points to voxel indices
        # Vectorized array check
        idx = np.floor((points - self.origin) / self.pitch).astype(np.int32)
        
        # Check bounds
        valid = (idx[:, 0] >= 0) & (idx[:, 0] < self.shape[0]) & \
                (idx[:, 1] >= 0) & (idx[:, 1] < self.shape[1]) & \
                (idx[:, 2] >= 0) & (idx[:, 2] < self.shape[2])
                
        # Return mask value for valid indices, False otherwise
        result = np.zeros(len(points), dtype=bool)
        
        if np.any(valid):
            v_idx = idx[valid]
            result[valid] = self.mask[v_idx[:, 0], v_idx[:, 1], v_idx[:, 2]]
            
        return result

    def sample_points(self, n: int, rng: np.random.Generator) -> np.ndarray:
        # Rejection sampling or sample directly from true voxels
        # Let's use direct sampling from True voxels for efficiency,
        # then uniformly sample within the voxel.
        
        true_indices = np.argwhere(self.mask)
        if len(true_indices) == 0:
            raise RuntimeError("Voxel mask is empty, cannot sample.")
            
        # Choose n random voxels with replacement
        chosen_indices = rng.choice(len(true_indices), size=n, replace=True)
        chosen_voxels = true_indices[chosen_indices]
        
        # Base positions of chosen voxels
        base_pos = self.origin + chosen_voxels * self.pitch
        
        # Uniform jitter within each voxel
        jitter = rng.random((n, 3), dtype=np.float32) * self.pitch
        
        return base_pos + jitter

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        return self._min_bounds, self._max_bounds

    def local_coordinates(self, points: np.ndarray) -> np.ndarray:
        size = self._max_bounds - self._min_bounds
        size = np.where(size == 0, 1.0, size)
        return (points - self._min_bounds) / size

    @classmethod
    def from_npz(cls, path: str) -> 'VoxelMaskGeometry':
        """Load a mask from a ``.npz`` file.

        Keys: ``mask`` (3D array, nonzero = inside) and either ``affine`` (4 x 4 voxel-index to
        space transform, axis-aligned: diagonal = voxel size, last column = origin of voxel
        (0, 0, 0)'s corner) or ``origin`` and ``voxel_size`` (3-vectors; ``pitch`` accepted).
        """
        with np.load(path) as z:
            mask = np.asarray(z["mask"]) != 0
            if "affine" in z:
                affine = np.asarray(z["affine"], dtype=np.float64)
                lin = affine[:3, :3]
                if affine.shape != (4, 4) or np.any(lin != np.diag(np.diag(lin))):
                    raise ValueError("Only axis-aligned (diagonal) 4 x 4 affines are supported")
                origin, pitch = affine[:3, 3], np.diag(lin)
            else:
                origin = z["origin"]
                pitch = z["voxel_size"] if "voxel_size" in z else z["pitch"]
        if mask.ndim != 3:
            raise ValueError(f"mask must be 3D, got shape {mask.shape}")
        return cls(mask, origin, pitch, source=str(path))

    def save_npz(self, path: str) -> None:
        """Write the mask, origin and voxel size to ``path`` (readable by ``from_npz``)."""
        np.savez_compressed(path, mask=self.mask, origin=self.origin, voxel_size=self.pitch)

    def to_dict(self) -> dict:
        if self.source is not None:
            return {"type": "voxel_mask", "npz": self.source}
        return {
            "type": "voxel_mask",
            "mask": self.mask.tolist(), # Storing boolean array as list. 
                                        # Note: Large arrays would typically use .npz sidecars,
                                        # but the project schema logic (A1) handles extraction.
                                        # Here we just dump as list for simplicity/tests.
            "origin": self.origin.tolist(),
            "pitch": self.pitch.tolist()
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Geometry':
        if "npz" in d:
            return cls.from_npz(d["npz"])
        return cls(d["mask"], d["origin"], d["pitch"])

