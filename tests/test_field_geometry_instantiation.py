"""Tests for F1: Field and geometry instantiation, registration, interface separation, and end-to-end execution."""
import numpy as np
import pytest

from neurogenesis.geometry import Box, _GEOMETRY_REGISTRY
from neurogenesis.fields import AnalyticField, _FIELD_REGISTRY
from neurogenesis.stages.base import run_schedule, _instantiate_fields
from neurogenesis.tissue import Tissue


def test_geometry_and_field_registration():
    """Mesh and voxel_mask must be registered in geometry registry automatically."""
    assert "mesh" in _GEOMETRY_REGISTRY
    assert "Mesh" in _GEOMETRY_REGISTRY
    assert "voxel_mask" in _GEOMETRY_REGISTRY
    assert "VoxelMask" in _GEOMETRY_REGISTRY
    assert "Box" in _GEOMETRY_REGISTRY

    assert "analyticfield" in _FIELD_REGISTRY or "AnalyticField" in _FIELD_REGISTRY
    assert "gridfield" in _FIELD_REGISTRY or "GridField" in _FIELD_REGISTRY


def test_interface_separation_geometry_and_field():
    """Geometry has sample_points(n, rng) and contains(x); Field has values(x)."""
    rng = np.random.default_rng(42)
    box = Box(center=[0, 0, 0], size=[10, 10, 10])
    
    assert hasattr(box, "sample_points")
    assert hasattr(box, "contains")
    pts = box.sample_points(20, rng)
    assert pts.shape == (20, 3)
    assert np.all(box.contains(pts))
    
    field = AnalyticField("x**2 + y**2")
    assert hasattr(field, "values")
    vals = field.values(pts)
    assert vals.shape == (20,)
    np.testing.assert_allclose(vals, pts[:, 0]**2 + pts[:, 1]**2)


def test_unknown_field_or_geometry_type_raises():
    """Unknown field/geometry types must raise ValueError immediately, never fall back silently."""
    with pytest.raises(ValueError, match="Unknown field or geometry type: 'UnknownShape'"):
        _instantiate_fields({"bad_geom": {"type": "UnknownShape"}})

    with pytest.raises(ValueError, match="missing required 'type' field"):
        _instantiate_fields({"no_type": {"size": [1, 1, 1]}})


def test_seed_cells_missing_or_wrong_geometry_raises():
    """seed_cells must raise ValueError if geometry not found, TypeError if not a Geometry."""
    project_missing = {
        "version": "1.0.0",
        "geometry": {},
        "fields": {},
        "schedule": [
            {
                "operator": "seed_cells",
                "params": {"N": 10, "geometry": "nonexistent_geom"}
            }
        ]
    }
    with pytest.raises(ValueError, match="Geometry 'nonexistent_geom' not found"):
        run_schedule(project_missing, genome={}, seed=1)

    project_wrong_type = {
        "version": "1.0.0",
        "geometry": {},
        "fields": {
            "my_field": {"type": "AnalyticField", "expr": "x + y"}
        },
        "schedule": [
            {
                "operator": "seed_cells",
                "params": {"N": 10, "geometry": "my_field"}
            }
        ]
    }
    with pytest.raises(TypeError, match="expected Geometry"):
        run_schedule(project_wrong_type, genome={}, seed=1)


def test_end_to_end_json_project_box_mesh_analytic_field():
    """End-to-end check: JSON project with a box, a mesh, and an analytic field runs seed_cells -> differentiate."""
    # Simple tetrahedron mesh centered around (20, 20, 20)
    mesh_verts = [
        [20.0, 20.0, 20.0],
        [30.0, 20.0, 20.0],
        [20.0, 30.0, 20.0],
        [20.0, 20.0, 30.0]
    ]
    mesh_faces = [
        [0, 1, 2],
        [0, 2, 3],
        [0, 3, 1],
        [1, 3, 2]
    ]

    project = {
        "version": "1.0.0",
        "geometry": {
            "source_box": {
                "type": "Box",
                "center": [0.0, 0.0, 0.0],
                "size": [10.0, 10.0, 10.0]
            },
            "target_mesh": {
                "type": "mesh",
                "vertices": mesh_verts,
                "faces": mesh_faces
            }
        },
        "fields": {
            "gradient": {
                "type": "AnalyticField",
                "expr": "x"
            }
        },
        "schedule": [
            {
                "name": "seed_in_box",
                "operator": "seed_cells",
                "params": {
                    "N": 40,
                    "geometry": "source_box",
                    "cell_type": 1,
                    "region": 1
                }
            },
            {
                "name": "seed_in_mesh",
                "operator": "seed_cells",
                "params": {
                    "N": 30,
                    "geometry": "target_mesh",
                    "cell_type": 2,
                    "region": 2
                }
            },
            {
                "name": "differentiate_by_field",
                "operator": "differentiate",
                "params": {
                    "types": [
                        {
                            "type_id": 5,
                            "condition": "field_gradient > 22.0",
                            "sign": 1,
                            "base_weight": 200
                        }
                    ]
                }
            }
        ]
    }

    tissue = run_schedule(project, genome={}, seed=123)

    assert isinstance(tissue, Tissue)
    assert len(tissue.alive) == 70
    assert np.all(tissue.alive)

    # Box cells (first 40)
    box_cells = tissue.positions[:40]
    assert np.all(np.abs(box_cells) <= 5.001)
    assert not np.allclose(box_cells, 0.0), "Box cells must not be collapsed at origin"

    # Mesh cells (last 30)
    mesh_cells = tissue.positions[40:]
    assert np.all(mesh_cells >= 19.99)
    assert np.all(mesh_cells <= 30.01)
    assert not np.allclose(mesh_cells, 0.0), "Mesh cells must not be collapsed at origin"

    # Check differentiation by gradient field (x coordinate)
    # Cells with x > 22 should become type 5
    cells_with_high_x = tissue.positions[:, 0] > 22.0
    assert np.any(cells_with_high_x), "Should have cells with x > 22 in mesh"
    assert np.all(tissue.cell_type[cells_with_high_x] == 5)

