"""Step-halving check of the float neuron models (analysis.cells.step_convergence)."""
import numpy as np
import pytest

from neurogenesis.analysis import step_convergence
from neurogenesis.spiking.batch import simulate_counts
from neurogenesis.spiking.morphology import MorphogeneticEngine


@pytest.mark.parametrize("model", ["two_compartment", "hh", "hh_table"])
def test_default_substeps_are_small_enough(model):
    net = MorphogeneticEngine.generate_cortical_column(60, seed=1, weight_scale=0.25, refractory=3)
    ext = np.random.default_rng(0).integers(0, 14, 60).astype(np.int32)
    r = step_convergence(net, model, ext, ticks=200)
    assert r["spikes"] > 50
    assert r["rate_change"] < 0.05 and r["matched"] > 0.7            # recurrent networks amplify small differences

    isolated = MorphogeneticEngine.generate_cortical_column(60, seed=1, weight_scale=0.25, refractory=3)
    for syn in isolated.synapses:                                    # same shapes (no recompilation), no coupling
        syn.weight = 0
    r = step_convergence(isolated, model, ext, ticks=200)
    assert r["matched"] > 0.95 and r["max_count_change"] <= 1        # single cells: spikes stay within one tick


def test_default_substeps_reproduce_the_batched_kernel_and_inputs_are_unchanged():
    from neurogenesis.analysis import spike_raster
    net = MorphogeneticEngine.generate_cortical_column(40, seed=2, weight_scale=0.25, refractory=3)
    ext = np.random.default_rng(1).integers(0, 14, 40).astype(np.int32)
    keep = ext.copy()
    for model in ("two_compartment", "hh"):
        raster = spike_raster(net, model, ext, 100, None, 0)     # simulate_counts seeds network i with i
        counts = simulate_counts([net], [ext[None, :]], ticks=100, model=model)[0][0]
        assert np.array_equal(raster.sum(0)[:40], counts[:40])
    assert np.array_equal(ext, keep)


def test_lif_int_is_refused():
    net = MorphogeneticEngine.generate_cortical_column(10, seed=0)
    with pytest.raises(ValueError):
        step_convergence(net, "lif_int", np.zeros(10, np.int32))
