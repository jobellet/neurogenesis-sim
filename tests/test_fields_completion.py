"""B4 / B5 completion: Subtract and Multiply fields, PointSetField, pinwheels located in band-pass maps."""
import numpy as np
import neurogenesis.stages  # noqa: F401
from neurogenesis.fields import (AnalyticField, Multiply, PinwheelField, PointSetField, Subtract, bandpass_pinwheels,
                                 field_from_dict, find_pinwheels, pinwheel_map)
from neurogenesis.params import collect_project_genes
from neurogenesis.stages.base import run_schedule

PTS = np.random.default_rng(0).uniform(0, 1, (50, 3))


def test_subtract_and_multiply_match_analytic_results_and_round_trip():
    x, y = AnalyticField("x"), AnalyticField("y")
    np.testing.assert_allclose(Subtract(x, y).values(PTS), PTS[:, 0] - PTS[:, 1])
    np.testing.assert_allclose(Multiply(x, 2.0).values(PTS), 2 * PTS[:, 0])
    np.testing.assert_allclose(Subtract(1.0, Multiply(x, y)).values(PTS), 1 - PTS[:, 0] * PTS[:, 1])
    for f in (Subtract(x, y), Multiply(Subtract(x, 0.5), y)):
        g = field_from_dict(f.to_dict())
        np.testing.assert_allclose(g.values(PTS), f.values(PTS))


def test_composite_fields_bind_genes_inside():
    project = {"fields": {"m": {"type": "Multiply", "a": {"type": "LayerStackField", "base_field": {"type": "AnalyticField", "expr": "z"},
                                                           "thicknesses": [{"path": ["t"], "lo": 0.1, "hi": 0.9}, 1.0]},
                                "b": 2.0}},
               "schedule": []}
    assert [g[0] for g in collect_project_genes(project)] == [("t",)]


def test_point_set_field_distances_and_patterns():
    f = PointSetField(points=[[0, 0], [1, 0]])
    np.testing.assert_allclose(f.values(np.array([[0.2, 0, 0], [0.9, 0.1, 0], [0.5, 1.0, 0]])),
                               [0.2, np.hypot(0.1, 0.1), np.hypot(0.5, 1.0)])
    g = PointSetField(pattern="poisson_disc", bounds=[[0, 0], [5, 5]], radius=0.5, seed=3)
    h = field_from_dict(g.to_dict())
    np.testing.assert_array_equal(g.points, h.points)                      # regenerated from its seed
    d = np.linalg.norm(g.points[:, None] - g.points[None], axis=-1)
    np.fill_diagonal(d, np.inf)
    assert d.min() >= 0.5 - 1e-9
    np.testing.assert_allclose(g.values(g.points), 0.0, atol=1e-12)
    # brute-force check of the nearest distance
    q = np.random.default_rng(1).uniform(0, 5, (200, 3))
    brute = np.linalg.norm(q[:, None] - g.points[None], axis=-1).min(1)
    np.testing.assert_allclose(g.values(q), brute)


def test_seed_cells_on_a_point_set_field():
    project = {"fields": {"blobs": {"type": "PointSetField", "points": [[1, 1, 0], [2, 2, 0], [3, 3, 0]]}},
               "schedule": [{"name": "s", "operator": "seed_cells", "params": {"points": {"type": "Field", "name": "blobs"}}}]}
    t = run_schedule(project, {}, 0)
    np.testing.assert_array_equal(t.positions, [[1, 1, 0], [2, 2, 0], [3, 3, 0]])


def test_find_pinwheels_recovers_hand_placed_singularities():
    sing = np.array([[3.1, 3.2], [6.7, 6.4]])
    charges = np.array([0.5, -0.5])
    bounds = (np.array([0.0, 0.0]), np.array([10.0, 10.0]))
    _, angles, _ = pinwheel_map(bounds, 0.25, sing, charges)
    pos, q = find_pinwheels(angles, bounds[0], 0.25)
    assert len(pos) == 2
    order = np.argsort(pos[:, 0])
    np.testing.assert_allclose(pos[order], sing, atol=0.25)
    np.testing.assert_array_equal(q[order], charges)


def test_bandpass_map_returns_pinwheels_with_their_charges():
    bounds = (np.array([0.0, 0.0]), np.array([20.0, 20.0]))
    pts, angles, pos, q = bandpass_pinwheels(bounds, 0.2, k0=0.25, sigma=0.03, rng=np.random.default_rng(5),
                                            return_pinwheels=True)
    assert len(pos) > 4 and set(np.unique(q)) <= {-0.5, 0.5}
    # the field built from the map's own singularities has the same winding around each one
    from neurogenesis.fields.core import GridField
    from neurogenesis.fields import pinwheel_charges
    grid = GridField(angles, origin=[0.0, 0.0], spacing=[0.2, 0.2])
    inner = np.all((pos > 2) & (pos < 18), axis=1)
    measured = pinwheel_charges(grid, pos[inner], radius=0.1, n_samples=16)
    np.testing.assert_allclose(measured, q[inner], atol=0.01)
    a2 = bandpass_pinwheels(bounds, 0.2, 0.25, 0.03, np.random.default_rng(5))
    np.testing.assert_array_equal(a2[1], angles)                             # same map without the pinwheels
