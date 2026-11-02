import json

import numpy as np
import pytest

from neurogenesis.fields import (
    GridField, AnalyticField, LayerStackField, Add, Threshold,
    regular_points, jittered_points, poisson_disc_points,
    pinwheel_map, field_from_dict, VectorField, LabelField, PinwheelField,
    pinwheel_charges, Gradient, DistanceToBoundary, DistanceTransform, GaussianSmooth
)
from neurogenesis.fields import ops as field_ops
from neurogenesis.geometry import Sphere
from neurogenesis.params import Gene

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
    if len(poi) > 1:
        d = np.linalg.norm(poi[:, None] - poi[None], axis=-1)
        assert np.min(d[np.triu_indices(len(poi), 1)]) >= 1.99 # Allow tiny numerical error

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


def _roundtrip(field):
    d = field.to_dict()
    json.dumps(d)
    return field_from_dict(json.loads(json.dumps(d)))


def test_no_scipy_in_fields():
    import neurogenesis.fields as fields_pkg
    import os
    root = os.path.dirname(fields_pkg.__file__)
    for name in os.listdir(root):
        if name.endswith('.py'):
            src = open(os.path.join(root, name)).read()
            assert 'import scipy' not in src and 'from scipy' not in src, name


def test_gradient_grid_and_analytic():
    xs = np.arange(5.0)
    X, Y = np.meshgrid(xs, xs, indexing='ij')
    grid = GridField(2 * X + 3 * Y, origin=[0, 0], spacing=[0.5, 0.5], method='trilinear')
    pts = np.array([[0.3, 0.7], [1.2, 1.9], [0.0, 2.0]])
    np.testing.assert_allclose(Gradient(grid).values(pts), np.tile([4.0, 6.0], (3, 1)), atol=1e-12)

    f = AnalyticField("x**2 + y*z")
    p3 = np.array([[1.0, 2.0, 3.0], [-0.5, 0.25, 1.5]])
    expected = np.stack([2 * p3[:, 0], p3[:, 2], p3[:, 1]], axis=-1)
    g = Gradient(f, step=1e-4)
    np.testing.assert_allclose(g.values(p3), expected, atol=1e-6)
    np.testing.assert_allclose(_roundtrip(g).values(p3), g.values(p3))
    np.testing.assert_allclose(_roundtrip(Gradient(grid)).values(pts), Gradient(grid).values(pts))


def test_distance_to_boundary_of_geometry():
    R, h = 3.0, 0.25
    dist = DistanceToBoundary(Sphere([0, 0, 0], R), bounds=([-4, -4, -4], [4, 4, 4]), spacing=h, signed=True)
    rng = np.random.default_rng(0)
    pts = rng.uniform(-3.5, 3.5, size=(500, 3))
    r = np.linalg.norm(pts, axis=-1)
    np.testing.assert_allclose(dist.values(pts), R - r, atol=h)
    unsigned = DistanceToBoundary(Sphere([0, 0, 0], R), bounds=([-4, -4, -4], [4, 4, 4]), spacing=h)
    np.testing.assert_allclose(unsigned.values(pts), np.abs(R - r), atol=h)
    np.testing.assert_allclose(_roundtrip(dist).values(pts), dist.values(pts))


def test_distance_to_boundary_of_label_region():
    labels = np.zeros((20, 10), dtype=int)
    labels[8:, :] = 3  # region 3: x >= 8 (cells of size 1)
    lf = LabelField(labels, origin=[0, 0], spacing=[1, 1])
    dist = DistanceToBoundary(lf, bounds=([0.5, 0.5], [19.5, 9.5]), spacing=0.5, label=3)
    pts = np.array([[2.0, 4.0], [12.0, 3.0], [18.0, 7.0]])
    np.testing.assert_allclose(dist.values(pts), np.abs(pts[:, 0] - 8.0), atol=0.5)
    np.testing.assert_allclose(_roundtrip(dist).values(pts), dist.values(pts))
    with pytest.raises(ValueError, match="label"):
        DistanceToBoundary(lf, bounds=([0, 0], [1, 1]), spacing=0.5)


def test_edt_exact_and_chunked(monkeypatch):
    rng = np.random.default_rng(1)
    seeds = rng.random((9, 7, 5)) < 0.05
    seeds[0, 0, 0] = True
    sp = np.array([1.0, 0.5, 2.0])
    nodes = np.stack(np.meshgrid(*[np.arange(n) * s for n, s in zip(seeds.shape, sp)], indexing='ij'), -1).reshape(-1, 3)
    s_pts = nodes[seeds.ravel()]
    brute = np.min(np.sum((nodes[:, None] - s_pts[None]) ** 2, -1), 1).reshape(seeds.shape)
    np.testing.assert_allclose(field_ops._edt_sq(seeds, sp), brute, atol=1e-9)
    monkeypatch.setattr(field_ops, "MAX_PAIRS", 7)
    np.testing.assert_allclose(field_ops._edt_sq(seeds, sp), brute, atol=1e-9)


def test_distance_transform_point_set_exact():
    targets = np.array([[1.0, 1.0], [7.5, 3.0]])
    dt = DistanceTransform((np.array([0.0, 0.0]), np.array([10.0, 5.0])), 1.0, targets)
    nodes = regular_points((np.array([0.0, 0.0]), np.array([10.0, 5.0])), 1.0)
    expected = np.min(np.linalg.norm(nodes[:, None] - targets[None], axis=-1), axis=1)
    np.testing.assert_allclose(dt.values(nodes), expected, atol=1e-12)


def test_gaussian_smooth_numpy():
    data = np.zeros((41, 41))
    data[20, 20] = 1.0
    sigma = 1.5
    sm = GaussianSmooth(GridField(data, [0, 0], [0.5, 0.5]), sigma)  # sigma 3 cells
    out = sm.smoothed_data
    assert np.isclose(out.sum(), 1.0)
    x = (np.arange(41) - 20) * 0.5
    var_x = np.sum(out.sum(axis=1) * x ** 2)
    assert abs(var_x - sigma ** 2) < 0.01 * sigma ** 2
    const = GaussianSmooth(GridField(np.full((6, 7), 2.5), [0, 0], [1, 1]), 2.0)
    np.testing.assert_allclose(const.smoothed_data, 2.5)
    np.testing.assert_array_equal(GaussianSmooth(GridField(data, [0, 0], [1, 1]), 0.0).smoothed_data, data)


def test_vector_field():
    vf = VectorField([AnalyticField("x"), AnalyticField("2*y"), AnalyticField("1")])
    pts = np.array([[1.0, 2.0, 3.0], [0.0, -1.0, 0.0]])
    np.testing.assert_allclose(vf.values(pts), [[1, 4, 1], [0, -2, 1]])
    vf2 = _roundtrip(vf)
    assert isinstance(vf2, VectorField)
    np.testing.assert_allclose(vf2.values(pts), vf.values(pts))


def test_label_field():
    data = np.array([[0, 1], [2, 3]])
    lf = LabelField(data, origin=[0, 0], spacing=[2, 2], background=-1, names={"3": "core"})
    pts = np.array([[0.5, 0.5], [0.5, 3.9], [3.0, 1.0], [3.0, 3.0], [-0.1, 0.0], [4.0, 1.0]])
    vals = lf.values(pts)
    assert vals.dtype == np.int32
    np.testing.assert_array_equal(vals, [0, 1, 2, 3, -1, -1])
    lf2 = _roundtrip(lf)
    assert isinstance(lf2, LabelField) and lf2.names == {"3": "core"}
    np.testing.assert_array_equal(lf2.values(pts), vals)


def test_layer_stack_gene_thicknesses():
    genome = {"layers": {"t0": 2.0, "t1": 3.0}}
    field = LayerStackField(AnalyticField("z"),
                            thicknesses=[Gene(("layers", "t0"), 0.5, 4.0), {"type": "Gene", "path": ["layers", "t1"]}],
                            labels=[10, 20])
    pts = np.array([[0, 0, 1.0], [0, 0, 3.5]])
    with pytest.raises(ValueError, match="bind"):
        field.values(pts)
    bound = field.bind(genome)
    np.testing.assert_allclose(bound.values(pts), [[10, 0.5], [20, 0.5]])
    np.testing.assert_allclose(_roundtrip(field).bind(genome).values(pts), bound.values(pts))
    genome2 = {"layers": {"t0": 1.0, "t1": 3.0}}
    np.testing.assert_allclose(field.bind(genome2).values(np.array([[0, 0, 0.5], [0, 0, 3.5]])),
                               [[10, 0.5], [20, 2.5 / 3.0]])
    # numeric thicknesses are unchanged by bind and serialised as numbers
    plain = LayerStackField(AnalyticField("z"), [2.0, 3.0])
    assert plain.to_dict()["thicknesses"] == [2.0, 3.0]
    np.testing.assert_allclose(plain.bind(genome).values(pts), plain.values(pts))


def test_layer_stack_gene_thickness_in_schedule():
    from neurogenesis.stages.base import run_schedule
    project = {
        "version": "1.0.0",
        "geometry": {"box": {"type": "Box", "center": [0.0, 0.0, 2.0], "size": [1.0, 1.0, 4.0]}},
        "fields": {"layers": {"type": "LayerStackField", "base_field": {"type": "AnalyticField", "expr": "z"},
                              "thicknesses": [{"type": "Gene", "path": ["t0"]}, 10.0], "labels": [1, 2]}},
        "schedule": [
            {"name": "seed", "operator": "seed_cells", "params": {"N": 200, "geometry": "box"}},
            {"name": "diff", "operator": "differentiate",
             "params": {"types": [{"type_id": 7, "condition": "field_layers[:, 0] == 1", "sign": 1, "base_weight": 1}]}},
        ],
    }
    for t0 in (1.0, 3.0):
        tissue = run_schedule(project, genome={"t0": t0}, seed=3)
        upper = tissue.positions[:, 2] < t0
        assert np.all(tissue.cell_type[upper] == 7) and not np.any(tissue.cell_type[~upper] == 7)


def test_pinwheel_field_and_charges():
    sing = np.array([[5.0, 5.0], [15.0, 5.0], [5.0, 15.0], [15.0, 15.0]])
    charges = np.array([0.5, -0.5, -0.5, 0.5])
    pf = PinwheelField(sing, charges, phase=0.3)
    pts = np.random.default_rng(0).uniform(0, 20, size=(100, 2))
    vals = pf.values(pts)
    assert np.all((vals >= 0) & (vals < np.pi))
    pf2 = _roundtrip(pf)
    assert isinstance(pf2, PinwheelField)
    np.testing.assert_allclose(pf2.values(pts), vals)
    np.testing.assert_allclose(pinwheel_charges(pf, sing, radius=1.0), charges, atol=1e-9)

    # charges recovered from the generated raw map (grid sampled with nearest neighbour)
    bounds = (np.array([0.0, 0.0]), np.array([20.0, 20.0]))
    _, angles, _ = pinwheel_map(bounds, 0.25, sing, charges)
    grid = GridField(angles, origin=[0, 0], spacing=[0.25, 0.25], method='nearest')
    np.testing.assert_allclose(pinwheel_charges(grid, sing + 0.1, radius=2.0), charges, atol=1e-9)
    # no singularity enclosed: charge 0
    np.testing.assert_allclose(pinwheel_charges(grid, [[10.0, 10.0]], radius=2.0), [0.0], atol=1e-9)


def test_composite_fields_bind_sub_fields():
    genome = {"layers": {"t0": 2.0}}
    layers = LayerStackField(AnalyticField("z"), thicknesses=[Gene(("layers", "t0"), 0.5, 4.0), 3.0], labels=[10, 20])
    pts = np.array([[0, 0, 1.0], [0, 0, 3.5]])
    field = Threshold(Add(layers, 1.0), threshold=15.0)
    with pytest.raises(ValueError, match="bind"):
        field.values(pts)
    bound = field.bind(genome)
    np.testing.assert_allclose(bound.base_field.values(pts), layers.bind(genome).values(pts) + 1.0)
    np.testing.assert_allclose(bound.values(pts), [[0, 0], [1, 0]])
    np.testing.assert_allclose(Add(1.0, layers).bind(genome).values(pts), [[11, 1.5], [21, 1.5]])
    # composites without genome-dependent parameters bind to themselves
    grid = GridField(np.arange(27.0).reshape(3, 3, 3), [0, 0, 0], [1, 1, 1])
    for f in (Add(grid, AnalyticField("x")), Threshold(grid, 3.0), GaussianSmooth(grid, 1.0),
              DistanceToBoundary(Sphere([1, 1, 1], 1.0), ([0, 0, 0], [2, 2, 2]), 0.5)):
        assert f.bind(genome) is f


def test_grid_shape_follows_generated_nodes():
    # The grid shape is the number of np.arange nodes per axis, whatever the bounds' type or the spacing.
    for bounds, spacing in [((np.array([0.0, 0.0]), np.array([0.3, 0.3])), 0.1),
                            (([0.0, 0.1], [0.7, 0.7]), 0.1),
                            ((np.array([0.0, -0.3]), np.array([1.1, 0.3])), [0.1, 0.2])]:
        nodes = regular_points(bounds, spacing)
        sp = [spacing] * 2 if np.isscalar(spacing) else spacing
        shape = tuple(len(np.arange(lo, hi, s)) for lo, hi, s in zip(bounds[0], bounds[1], sp))
        points, angles, _ = pinwheel_map(bounds, spacing, np.array([[0.05, 0.05]]), np.array([0.5]))
        assert angles.shape == shape and points.shape == shape + (2,)
        np.testing.assert_array_equal(points.reshape(-1, 2), nodes)
        dt = DistanceTransform(bounds, spacing, np.array([[0.05, 0.05]]))
        assert dt.grid_field.data.shape == shape
        expected = np.linalg.norm(nodes - [0.05, 0.05], axis=-1)
        np.testing.assert_allclose(dt.values(nodes), expected, atol=1e-12)
