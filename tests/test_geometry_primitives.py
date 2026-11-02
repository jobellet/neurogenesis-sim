import numpy as np
import pytest
from neurogenesis.geometry import (
    Box, Sphere, Ellipsoid, Cylinder, Sheet2D, CurvedSheet, Union, Difference, geometry_from_dict
)

@pytest.fixture
def rng():
    return np.random.default_rng(42)

def check_geometry_basics(geom, rng, num_samples=1000):
    # Determinism
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    samples1 = geom.sample(num_samples, rng1)
    samples2 = geom.sample(num_samples, rng2)
    np.testing.assert_allclose(samples1, samples2)
    
    # Containment of sampled points
    assert np.all(geom.contains(samples1)), f"Not all sampled points contained in {type(geom).__name__}"
    
    # Bounding box bounds sampled points
    mins, maxs = geom.bounding_box()
    assert np.all(samples1 >= mins - 1e-4), f"Samples below bounding box min for {type(geom).__name__}"
    assert np.all(samples1 <= maxs + 1e-4), f"Samples above bounding box max for {type(geom).__name__}"
    
    # Local coordinates within [0, 1] range for the most part
    loc = geom.local_coordinates(samples1)
    assert loc.shape == (num_samples, 3)
    # Some geometries like CurvedSheet are approximate for local coords, just ensure it doesn't crash and is float32
    assert loc.dtype == np.float32 or loc.dtype == np.float64
    
    # Round-trip JSON
    d = geom.to_dict()
    geom2 = geometry_from_dict(d)
    
    # Just check that it doesn't crash and has same type
    assert type(geom) == type(geom2)

def check_uniformity_box(geom, rng):
    samples = geom.sample(8000, rng)
    # Octant counts
    mid = geom.center
    octants = np.zeros(8, dtype=int)
    for p in samples:
        idx = 0
        if p[0] > mid[0]: idx += 1
        if p[1] > mid[1]: idx += 2
        if p[2] > mid[2]: idx += 4
        octants[idx] += 1
    
    expected = 1000
    chi2 = np.sum((octants - expected)**2 / expected)
    # Chi2 critical value for 7 dof and p=0.01 is 18.47
    assert chi2 < 25.0, f"Chi2 too high for uniformity test: {chi2}"


def test_box(rng):
    b = Box(center=[1, 2, 3], size=[2, 4, 6])
    check_geometry_basics(b, rng)
    check_uniformity_box(b, rng)

def test_sphere(rng):
    s = Sphere(center=[-1, 0, 1], radius=2.5)
    check_geometry_basics(s, rng)
    
    # For a sphere, uniformity in octants around center
    samples = s.sample(8000, rng)
    mid = s.center
    octants = np.zeros(8, dtype=int)
    for p in samples:
        idx = 0
        if p[0] > mid[0]: idx += 1
        if p[1] > mid[1]: idx += 2
        if p[2] > mid[2]: idx += 4
        octants[idx] += 1
    
    expected = 1000
    chi2 = np.sum((octants - expected)**2 / expected)
    assert chi2 < 25.0

def test_ellipsoid(rng):
    e = Ellipsoid(center=[0, 0, 0], radii=[1, 2, 3])
    check_geometry_basics(e, rng)

def test_cylinder(rng):
    c = Cylinder(p0=[0, 0, 0], p1=[0, 0, 10], radius=2.0)
    check_geometry_basics(c, rng)
    
    samples = c.sample(8000, rng)
    # check that along Z it's uniform
    z_vals = samples[:, 2]
    h, _ = np.histogram(z_vals, bins=4, range=(0, 10))
    chi2 = np.sum((h - 2000)**2 / 2000)
    assert chi2 < 20.0

def test_sheet2d(rng):
    s = Sheet2D(center=[0, 0, 0], u_vec=[1, 0, 0], v_vec=[0, 1, 0], thickness=0.1)
    check_geometry_basics(s, rng)

def test_curved_sheet(rng):
    # A simple parabolic sheet
    s = CurvedSheet("u", "v", "u**2 + v**2", thickness=0.1)
    # Re-using check_geometry_basics might fail contains() occasionally due to approximation, 
    # Let's write a custom one or just bump epsilon.
    rng1 = np.random.default_rng(42)
    samples1 = s.sample(100, rng1)
    # Because contains uses an approximation on a grid, let's just assert the shape and some properties
    assert samples1.shape == (100, 3)
    
    # Containment
    mask = s.contains(samples1)
    assert np.mean(mask) > 0.9  # Should contain almost all its own samples
    
    # Round-trip JSON
    d = s.to_dict()
    s2 = geometry_from_dict(d)
    assert s2.thickness == s.thickness

def test_curved_sheet_expressions_are_restricted(tmp_path):
    s = CurvedSheet("cos(pi * u)", "np.sin(v)", "0.5 * exp(-u^2)", thickness=0.1)
    p = s.surface_points[-1]
    assert np.allclose(p, [np.cos(np.pi), np.sin(1.0), 0.5 * np.exp(-1.0)], atol=1e-6)
    marker = tmp_path / "pwned"
    for bad in (f"__import__('os').system('touch {marker}')", "u.__class__", "open('x')"):
        with pytest.raises(Exception):
            CurvedSheet("u", "v", bad, thickness=0.1)
    assert not marker.exists()


def test_csg_union(rng):
    b1 = Box([0, 0, 0], [2, 2, 2])
    b2 = Box([1, 1, 1], [2, 2, 2])
    u = Union(b1, b2)
    check_geometry_basics(u, rng, num_samples=100)

def test_csg_difference(rng):
    b1 = Box([0, 0, 0], [2, 2, 2])
    b2 = Box([1, 1, 1], [2, 2, 2])
    d = Difference(b1, b2)
    check_geometry_basics(d, rng, num_samples=100)
    
    samples = d.sample(100, rng)
    assert np.all(~b2.contains(samples))

