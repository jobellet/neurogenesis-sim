import numpy as np
import pytest

from neurogenesis.data.registration import roi_mask_geometry, column_coordinates_field
from neurogenesis.geometry.voxel import VoxelMaskGeometry
from neurogenesis.data.importer import transform_positions

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


@pytest.mark.parametrize("mirror", [[0], [2], [0, 2], [0, 1, 2]])
def test_roi_mask_geometry_matches_transform_positions_when_mirrored(mirror):
    # Every voxel of the geometry must cover the same box in µm as transform_positions gives for the raw voxel's
    # corners (i, j, k) and (i + 1, j + 1, k + 1), with a non-zero origin and anisotropic voxels.
    rng = np.random.default_rng(3)
    mask = rng.random((5, 4, 3)) < 0.4
    mask[0, 0, 0], mask[4, 3, 2] = True, False
    units = {"voxel_size": [16.752, 16.752, 20.0], "origin": [-1500.0, 250.0, 3200.0], "mirror": mirror}
    geom = roi_mask_geometry(mask, units)

    raw = np.argwhere(mask).astype(np.float64)
    a, b = transform_positions(raw, units), transform_positions(raw + 1.0, units)
    expected = np.minimum(a, b)
    got = geom.origin.astype(np.float64) + np.argwhere(geom.mask) * geom.pitch.astype(np.float64)
    order = lambda p: p[np.lexsort(np.round(p, 3).T[::-1])]
    assert np.allclose(order(got), order(expected), atol=1e-2)
    assert geom.contains((a + b) / 2).all()
    lo, hi = np.minimum(transform_positions(np.zeros((1, 3)), units), transform_positions(np.array([mask.shape], float), units)), \
        np.maximum(transform_positions(np.zeros((1, 3)), units), transform_positions(np.array([mask.shape], float), units))
    assert np.allclose(geom.bounding_box()[0], lo[0], atol=1e-2) and np.allclose(geom.bounding_box()[1], hi[0], atol=1e-2)
