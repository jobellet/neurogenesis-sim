import numpy as np
import pytest

from neurogenesis.fields import (
    GridField, AnalyticField, LayerStackField, Add, Threshold,
    regular_points, jittered_points, poisson_disc_points,
    pinwheel_map, field_from_dict
)

def test_analytic_field_sampling():
    field = AnalyticField("x + 2*y")
    points = np.array([[1.0, 2.0, 0.0], [0.0, 0.0, 0.0], [3.0, -1.0, 5.0]])
    vals = field.sample(points)
    np.testing.assert_allclose(vals, [5.0, 0.0, 1.0])

def test_grid_field_sampling():
    data = np.array([[0, 1], [2, 3]])
    field_nearest = GridField(data, origin=[0, 0], spacing=[1, 1], method='nearest')
    
    # Exact points
    np.testing.assert_equal(field_nearest.sample(np.array([[0, 0], [1, 1]])), [0, 3])
    
    # Trilinear/Bilinear interpolation
    field_linear = GridField(data, origin=[0, 0], spacing=[1, 1], method='trilinear')
    # Point at (0.5, 0.5) should be average of all 4 points: (0+1+2+3)/4 = 1.5
    np.testing.assert_allclose(field_linear.sample(np.array([[0.5, 0.5]])), [1.5])

def test_layer_stack_field():
    base = AnalyticField("z") # Depth is just z coordinate
    # layers: 
    # L0: thickness 2, z in [0, 2]
    # L1: thickness 3, z in [2, 5]
    field = LayerStackField(base, thicknesses=[2.0, 3.0], labels=[10, 20])
    
    points = np.array([
        [0, 0, 1.0], # L0, w=0.5
        [0, 0, 2.0], # L1, w=0.0 (or boundary)
        [0, 0, 3.5], # L1, w=0.5
    ])
    
    vals = field.sample(points)
    
    np.testing.assert_allclose(vals[0], [10, 0.5])
    # The point at exactly z=2 might fall in either depending on digitization, our implementation puts it in L1 (z=2, start=2, w=0)
    # Actually digitize with bins [0, 2, 5] puts 2 in bin 2 (L1).
    np.testing.assert_allclose(vals[1], [20, 0.0])
    np.testing.assert_allclose(vals[2], [20, 0.5])

def test_point_patterns():
    bounds = (np.array([0, 0]), np.array([10, 10]))
    
    reg = regular_points(bounds, 2.0)
    assert len(reg) == 25 # 5x5 grid (0, 2, 4, 6, 8)
    
    rng = np.random.default_rng(42)
    jit = jittered_points(bounds, 2.0, 0.1, rng)
    assert len(jit) == 25
    assert np.all(jit >= 0) and np.all(jit <= 10)
    
    poi = poisson_disc_points(bounds, 2.0, rng)
    assert len(poi) > 0
    
    # Check minimum distance in Poisson disc
    from scipy.spatial.distance import pdist
    if len(poi) > 1:
        dists = pdist(poi)
        assert np.min(dists) >= 1.99 # Allow tiny numerical error

def test_pinwheel_map():
    bounds = (np.array([0, 0]), np.array([10, 10]))
    singularities = np.array([[5, 5]])
    charges = np.array([0.5])
    
    points, angles, _ = pinwheel_map(bounds, 1.0, singularities, charges)
    
    assert points.shape == (10, 10, 2)
    assert angles.shape == (10, 10)
    
    # Points array is generated as meshgrid(indexing='ij')
    # So points[i, j] corresponds to x=i, y=j
    # We want point at x=6, y=5. This is points[6, 5]
    # Vector is (1, 0) -> angle 0
    np.testing.assert_allclose(angles[6, 5], 0.0, atol=1e-5)
    
    # Check angle at x=5, y=6 (top of (5, 5)) -> vector (0, 1) -> angle pi/2
    # But charge is 0.5, so angle should be pi/4
    np.testing.assert_allclose(angles[5, 6], np.pi / 4, atol=1e-5)

def test_json_roundtrip():
    field = Add(AnalyticField("x"), Threshold(AnalyticField("y"), 0.5))
    d = field.to_dict()
    
    field2 = field_from_dict(d)
    
    assert isinstance(field2, Add)
    assert isinstance(field2.a, AnalyticField)
    assert isinstance(field2.b, Threshold)
    
    points = np.array([[1.0, 0.2], [2.0, 0.8]])
    vals1 = field.sample(points)
    vals2 = field2.sample(points)
    
    np.testing.assert_allclose(vals1, vals2)
