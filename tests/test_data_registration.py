import numpy as np
import pytest

from neurogenesis.data.registration import roi_mask_geometry, column_coordinates_field
from neurogenesis.geometry.voxel import VoxelMaskGeometry

def test_roi_mask_geometry():
    # 2x2x2 cube boolean mask
    mask = np.ones((2, 2, 2), dtype=bool)

    # Simple units
    units = {
        "voxel_size": [2.0, 2.0, 2.0],
        "origin": [10.0, 20.0, 30.0],
        "mirror": []
    }

    geom = roi_mask_geometry(mask, units)
    assert isinstance(geom, VoxelMaskGeometry)
    assert np.allclose(geom.origin, [10.0, 20.0, 30.0])
    assert np.allclose(geom.pitch, [2.0, 2.0, 2.0])
    assert np.all(geom.mask == mask)

    # Mirroring along axis 0
    units_mirror = {
        "voxel_size": [2.0, 2.0, 2.0],
        "origin": [10.0, 20.0, 30.0],
        "mirror": [0]
    }

    # We test with a mask that isn't symmetric
    mask_asym = np.zeros((2, 2, 2), dtype=bool)
    mask_asym[0, :, :] = True

    geom_mirror = roi_mask_geometry(mask_asym, units_mirror)

    # Original extent on axis 0: 10 to 14.
    # After mirror, this becomes -14 to -10.
    # The new origin should be -14.0 (the minimum coordinate)
    assert np.allclose(geom_mirror.origin, [-14.0, 20.0, 30.0])

    # Since we flipped the mask, the original 0th slice (which was at x=10 to x=12)
    # is now at the END of the flipped mask (index 1), which maps to -12 to -10.
    assert geom_mirror.mask[1, 0, 0] == True
    assert geom_mirror.mask[0, 0, 0] == False

def test_roi_mask_geometry_label_array():
    # 2x2x2 label array
    labels = np.zeros((2, 2, 2), dtype=int)
    labels[0, :, :] = 5
    labels[1, :, :] = 10

    units = {
        "voxel_size": [1.0, 1.0, 1.0],
        "origin": [0.0, 0.0, 0.0],
        "mirror": []
    }

    geom = roi_mask_geometry(labels, units, region_id=10)
    assert isinstance(geom, VoxelMaskGeometry)
    assert geom.mask[0, 0, 0] == False
    assert geom.mask[1, 0, 0] == True

def test_column_coordinates_field():
    # simple hexagonal columns
    centers = np.array([
        [0, 0, 0],
        [1, 0, 0],
        [0.5, np.sqrt(3)/2, 0],
        [1.5, np.sqrt(3)/2, 0],
        [0, np.sqrt(3), 0],
        [1, np.sqrt(3), 0]
    ])

    units = {
        "voxel_size": [2.0, 3.0, 4.0],
        "origin": [10.0, 20.0, 30.0],
        "mirror": [1]
    }

    field = column_coordinates_field(centers, units)

    pts = field.points
    assert np.allclose(pts[0], [10.0, -20.0, 30.0])
    assert np.allclose(pts[2], [11.0, -(np.sqrt(3)/2 * 3 + 20.0), 30.0])
