"""Evolution strategies on [0, 1] gene vectors (neurogenesis.evolution.strategies)."""
import numpy as np
import pytest

from neurogenesis.evolution import evolve_es
from neurogenesis.evolution.strategies import Adam, antithetic, centred_ranks, gradient, shape, zscores


def test_shaping_known_values():
    assert np.allclose(centred_ranks([3.0, 1.0, 2.0, 10.0]), [1 / 6, -0.5, -1 / 6, 0.5])   # an outlier counts as one rank
    t = centred_ranks([1.0, 1.0, 0.0, 2.0])
    assert t[0] == t[1] and t[2] < t[0] < t[3] and abs(t.sum()) < 1e-12               # ties share their mean rank
    assert np.allclose(zscores([1.0, 2.0, 3.0]), [-1.2247449, 0.0, 1.2247449])
    assert not zscores(np.ones(4)).any() and not centred_ranks(np.ones(4)).any()     # equal scores give no direction
    assert np.allclose(shape([1.0, 2.0], "z"), [-1.0, 1.0])
    with pytest.raises(ValueError):
        shape([1.0], "max")


def test_antithetic_pairs_frozen_columns_and_gradient():
    eps = antithetic(np.random.default_rng(0), 6, 4, frozen=[2])
    assert eps.shape == (6, 4) and np.allclose(eps[:3], -eps[3:]) and not eps[:, 2].any()
    with pytest.raises(ValueError):
        antithetic(np.random.default_rng(0), 5, 4)
    # one direction along gene 0: +eps ranks first, -eps last -> slope (0.5 x 1 + 0.5 x 1) / (2 x 0.1) = 5 along +gene 0
    e = np.array([[1.0, 0.0], [-1.0, 0.0]])
    assert np.allclose(gradient(np.array([0.5, -0.5]), e, 0.1), [5.0, 0.0])


def test_adam_moves_by_about_lr_per_step_and_towards_the_slope():
    a = Adam(2, 0.01)
    d = a.step(np.array([5.0, -0.001]))
    assert np.allclose(np.abs(d), 0.01, rtol=1e-3) and d[0] > 0 > d[1]


def _quadratic(gs, seeds):
    return [-(g["x"]["a"] - 0.6) ** 2 - (g["x"]["b"] + 0.3) ** 2 for g in gs], [dict(seeds=list(seeds))] * len(gs)


BASE = dict(x=dict(a=0.0, b=0.0, c=0.5))
GENES = [(("x", "a"), -1.0, 1.0), (("x", "b"), -1.0, 1.0), (("x", "c"), 0.0, 1.0)]


@pytest.mark.parametrize("optimizer,lr", [("sgd", 0.005), ("adam", 0.02)])
def test_es_climbs_a_simple_objective_and_leaves_frozen_genes(optimizer, lr):
    from neurogenesis.genome.genes import from_unit
    seen = []
    u, hist = evolve_es(BASE, GENES, _quadratic, island=0, pop=16, gens=80, seeds_per_gen=1, sigma=0.05, lr=lr,
                        optimizer=optimizer, frozen=[("x", "c")], log=seen.append)
    g = from_unit(BASE, GENES, u)
    assert abs(g["x"]["a"] - 0.6) < 0.1 and abs(g["x"]["b"] + 0.3) < 0.1
    assert g["x"]["c"] == 0.5                                            # frozen by path: never moves
    assert hist[-1]["centre"] > hist[0]["centre"] and len(seen) == 80 and seen[-1] is hist[-1]
    assert set(hist[0]) >= {"generation", "centre", "best", "median", "spread", "grad_norm", "step_norm", "dist_from_start",
                            "centre_info", "wall_s"}


def test_es_is_deterministic_and_uses_island_seeds():
    calls = []

    def ev(gs, seeds):
        calls.append(tuple(seeds))
        return _quadratic(gs, seeds)
    u1, _ = evolve_es(BASE, GENES, ev, island=3, pop=8, gens=5, seeds_per_gen=2)
    u2, _ = evolve_es(BASE, GENES, ev, island=3, pop=8, gens=5, seeds_per_gen=2)
    u3, _ = evolve_es(BASE, GENES, ev, island=4, pop=8, gens=5, seeds_per_gen=2)
    assert np.array_equal(u1, u2) and not np.array_equal(u1, u3)
    from neurogenesis.evolution import seeds_of
    assert calls[0] == seeds_of(3, 0, 2) and calls[1] == seeds_of(3, 1, 2)


def test_es_rejects_bad_arguments():
    with pytest.raises(ValueError):
        evolve_es(BASE, GENES, _quadratic, pop=7, gens=1)
    with pytest.raises(ValueError):
        evolve_es(BASE, GENES, _quadratic, pop=8, gens=1, optimizer="rmsprop")
    with pytest.raises(KeyError):
        evolve_es(BASE, GENES, _quadratic, pop=8, gens=1, frozen=["x/z"])
