"""E5 quality diversity: archive rules (MAP-Elites, CMA-MAE thresholds), emitters, determinism."""
import numpy as np
import pytest

from neurogenesis.evolution.quality_diversity import Archive, CMAEmitter, evolve_qd

BASE = dict(x=dict(a=0.0, b=0.0))
GENES = [(("x", "a"), -1.0, 1.0), (("x", "b"), -1.0, 1.0)]


def _sphere(gs, seeds):
    """Fitness peaks at a = 0.5; descriptors are the genes themselves."""
    f = [-(g["x"]["a"] - 0.5) ** 2 - g["x"]["b"] ** 2 for g in gs]
    return f, [dict(bd=[g["x"]["a"], g["x"]["b"]]) for g in gs]


def test_archive_map_elites_rule():
    a = Archive(2, [0, 0], [1, 1], [4, 4])
    assert a.index([0.0, 0.0]) == 0 and a.index([0.99, 0.99]) == 15 and a.index([5, -5]) == 12   # clipped
    assert a.add([0.1, 0.1], 1.0, [0.1, 0.1]) == (2, 1.0)
    assert a.add([0.1, 0.1], 0.5, [0.1, 0.1])[0] == 0
    st, imp = a.add([0.2, 0.2], 3.0, [0.1, 0.1])
    assert st == 1 and imp == pytest.approx(2.0) and a.fitness[0] == 3.0 and a.threshold[0] == 3.0
    assert a.coverage() == 1 / 16 and a.qd_score() == 3.0 and a.best() == 0
    with pytest.raises(ValueError):
        Archive(2, [0], [1], [4], learning_rate=0.5)          # CMA-MAE needs a finite threshold_min


def test_archive_cma_mae_annealing():
    a = Archive(1, [0], [1], [2], learning_rate=0.5, threshold_min=0.0)
    assert a.add([0.1], -1.0, [0.1])[0] == 0 and a.coverage() == 0.0           # below threshold_min: not stored
    assert a.add([0.1], 4.0, [0.1]) == (2, 4.0)
    assert a.threshold[0] == pytest.approx(2.0)                                 # 0.5 x 0 + 0.5 x 4
    st, imp = a.add([0.2], 3.0, [0.2])
    assert st == 1 and imp == pytest.approx(1.0) and a.threshold[0] == pytest.approx(2.5)
    assert a.fitness[0] == 4.0                                                  # the elite stays the best seen


def test_cma_emitter_minimises_a_quadratic():
    em = CMAEmitter(np.full(3, 0.9), 0.2, 12, np.random.default_rng(0))
    for _ in range(60):
        x = em.ask()
        f = np.sum((x - 0.3) ** 2, 1)
        em.tell(np.argsort(f))
    assert np.allclose(em.mean, 0.3, atol=0.02)


@pytest.mark.parametrize("emitter,lr,tmin", [("gaussian", 1.0, -np.inf), ("cma", 1.0, -np.inf), ("cma", 0.1, -3.0)])
def test_evolve_qd_fills_the_archive_and_finds_the_peak(emitter, lr, tmin):
    seen = []
    arch, hist = evolve_qd(BASE, GENES, _sphere, "bd", [-1, -1], [1, 1], [8, 8], emitter=emitter, emitters=2, batch=8,
                           gens=40, seeds_per_gen=1, sigma=0.15, learning_rate=lr, threshold_min=tmin, log=seen.append)
    assert len(seen) == 40 and hist[-1]["coverage"] > 0.5
    assert arch.fitness[arch.best()] > -0.02
    cov = [h["coverage"] for h in hist]
    assert all(b >= a for a, b in zip(cov, cov[1:]))
    assert arch.qd_score(offset=-3.0) > 0


def test_evolve_qd_is_deterministic_and_validates():
    run = lambda: evolve_qd(BASE, GENES, _sphere, lambda i: i["bd"], [-1, -1], [1, 1], [5, 5], island=3, emitters=2,
                            batch=6, gens=10, seeds_per_gen=1)[0]
    a, b = run(), run()
    assert np.array_equal(np.nan_to_num(a.genes), np.nan_to_num(b.genes))
    with pytest.raises(ValueError):
        evolve_qd(BASE, GENES, _sphere, "bd", [-1, -1], [1, 1], [5, 5], emitter="nsga")
