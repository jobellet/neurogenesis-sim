import numpy as np
from typing import Dict, Any, Union, Optional

from ..geometry.voxel import VoxelMaskGeometry
from ..fields.core import Field
from ..fields.maps import PointSetField
from .importer import transform_positions

def roi_mask_geometry(mask: np.ndarray, units: Dict[str, Any], region_id: Optional[int] = None) -> VoxelMaskGeometry:
    """ROI mask as a VoxelMaskGeometry in physical units, derived from a voxel volume.

    `mask` can be a 3D boolean array (True for inside the ROI) or a label array.
    If it's a label array, `region_id` must be provided to select the correct region.
    `units` is a dict with `voxel_size`, `origin`, and optionally `mirror` axes,
    as expected by `transform_positions`.
    """
    if mask.ndim != 3:
        raise ValueError("roi_mask_geometry requires a 3D mask array")

    if region_id is not None:
        mask = (mask == region_id)
    else:
        mask = np.asarray(mask, dtype=bool)

    voxel_size = np.asarray(units.get("voxel_size", [1.0, 1.0, 1.0]), dtype=np.float64)
    pitch = voxel_size.copy()

    mirror = units.get("mirror", [])
    for ax in mirror:
        ax = int(ax)
        mask = np.flip(mask, axis=ax)

    # To ensure perfect alignment with `transform_positions`, compute the bounding box
    # of the volume in raw voxel coordinates, transform it, and use the minimum values as origin.
    # A voxel grid of shape (N_x, N_y, N_z) spans from [0, 0, 0] to [N_x, N_y, N_z] in raw voxel space.
    # The bounding box corners are:
    shape = mask.shape
    corners_raw = np.array([
        [0, 0, 0],
        [shape[0], 0, 0],
        [0, shape[1], 0],
        [shape[0], shape[1], 0],
        [0, 0, shape[2]],
        [shape[0], 0, shape[2]],
        [0, shape[1], shape[2]],
        [shape[0], shape[1], shape[2]]
    ], dtype=np.float64)

    corners_physical = transform_positions(corners_raw, units)
    transformed_origin = np.min(corners_physical, axis=0)

    return VoxelMaskGeometry(mask, transformed_origin, pitch)

def column_coordinates_field(centers: np.ndarray, units: Dict[str, Any]) -> Field:
    """Column centers mapped to a Field (PointSetField) in physical units.

    `centers` is an (N, 3) array of column centers in raw voxel coordinates.
    `units` is a dict with `voxel_size`, `origin`, and `mirror` axes.
    """
    centers = np.asarray(centers, dtype=np.float64)
    if centers.ndim != 2 or centers.shape[1] != 3:
        raise ValueError("column_coordinates_field requires an (N, 3) array of centers")

    physical_centers = transform_positions(centers, units)
    return PointSetField(points=physical_centers)
