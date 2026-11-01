"""Batched simulation equals each network run alone, tick by tick."""
import jax
import numpy as np

from neurogenesis.spiking import batch, jax_backend
from neurogenesis.spiking.morphology import MorphogeneticEngine


def test_batched_counts_equal_single_runs():
    nets = [MorphogeneticEngine.generate_cortical_column(n, seed=s, weight_scale=0.25, refractory=3) for n, s in ((60, 1), (90, 2))]
    rng = np.random.default_rng(0)
    exts = [rng.integers(0, 80, size=(3, n.num_neurons)).astype(np.int32) for n in nets]
    counts = batch.simulate_counts(nets, exts, ticks=20, blank=5)
    N, E, P = batch.pad_sizes(nets)
    for k, (net, ext) in enumerate(zip(nets, exts)):
        a = jax_backend.pack(net, N, E, P)
        st = jax_backend.init_state(a, k)
        tick = jax.jit(lambda st, e: jax_backend.tick(a, st, e))
        for s in range(3):
            tot = np.zeros(N, np.int64)
            for t in range(25):
                e = np.zeros(N, np.int32)
                if t >= 5:
                    e[:net.num_neurons] = ext[s]
                st, spk, _ = tick(st, e)
                if t >= 5:
                    tot += np.asarray(spk)
            assert np.array_equal(counts[k][s], tot)
    assert counts.sum() > 0
