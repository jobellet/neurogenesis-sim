"""Fields (B3-B5): scalar, vector and label fields over space, point patterns and maps, and field operations."""
from .core import Field, GridField, AnalyticField, LayerStackField, VectorField, LabelField, register_field, field_from_dict, _FIELD_REGISTRY
from .maps import regular_points, jittered_points, poisson_disc_points, pinwheel_map, bandpass_pinwheels, PinwheelField, pinwheel_charges, find_pinwheels, PointSetField
from .ops import Add, Subtract, Multiply, Threshold, GaussianSmooth, DistanceTransform, Gradient, DistanceToBoundary

__all__ = [
    'Field',
    'GridField',
    'AnalyticField',
    'LayerStackField',
    'VectorField',
    'LabelField',
    'register_field',
    'field_from_dict',
    '_FIELD_REGISTRY',
    'regular_points',
    'jittered_points',
    'poisson_disc_points',
    'pinwheel_map',
    'bandpass_pinwheels',
    'PinwheelField',
    'pinwheel_charges',
    'find_pinwheels',
    'PointSetField',
    'Subtract',
    'Multiply',
    'Add',
    'Threshold',
    'GaussianSmooth',
    'DistanceTransform',
    'Gradient',
    'DistanceToBoundary',
]
