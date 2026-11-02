"""Geometries (B1-B2): primitives, set operations, triangle meshes and voxel masks, with a JSON registry."""
from .primitives import (
    Geometry,
    Box,
    Sphere,
    Ellipsoid,
    Cylinder,
    Sheet2D,
    CurvedSheet,
    Union,
    Difference,
    geometry_from_dict,
    register_geometry,
    _GEOMETRY_REGISTRY,
)
from .mesh import MeshGeometry
from .voxel import VoxelMaskGeometry

__all__ = [
    "Geometry",
    "Box",
    "Sphere",
    "Ellipsoid",
    "Cylinder",
    "Sheet2D",
    "CurvedSheet",
    "Union",
    "Difference",
    "MeshGeometry",
    "VoxelMaskGeometry",
    "geometry_from_dict",
    "register_geometry",
    "_GEOMETRY_REGISTRY",
]
