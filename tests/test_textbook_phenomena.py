"""Textbook phenomena with known answers, on tiny hand-built networks (the scoreboard in docs/NEURON_MODELS.md).

Each test is one classic experiment of cellular or small-circuit electrophysiology. Where a model does not show a
phenomenon, the test says so, so that the scoreboard stays honest. Currents are in toolbox units.
"""
import numpy as np
import pytest

from neurogenesis.analysis import fi_curve, spike_raster
from neurogenesis.spiking.models import hh
from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData


def net(n, synapses=(), per_cell=None, **kw):
    """n cells on a line (mode 0) with the given (pre, post, weight, delay) synapses."""
    cells = []
    for i in range(n):
        opts = dict(kw, **(per_cell(i) if per_cell else {}))
        cells.append(NeuronData(id=i, x=float(i), y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, **opts))
    return SNNNetwork(neurons=cells, synapses=[SynapseData(*s) for s in synapses])


def pulse(amp, start, dur, ticks, n=1, cells=(0,)):
    e = np.zeros((ticks, n), np.int32)
    e[start:start + dur, list(cells)] = amp
    return e


def threshold_current(model, duration, amps, ticks=200):
    """Smallest pulse amplitude of the given duration that makes an isolated cell fire: one run, one cell per
    amplitude (the cells are not connected)."""
    amps = np.asarray(amps, np.int32)
    e = np.zeros((ticks, len(amps)), np.int32)
    e[20:20 + duration] = amps
    fired = spike_raster(net(len(amps), refractory=3), model, e, ticks).sum(0) > 0
    assert fired[-1], "largest amplitude does not fire"
    return int(amps[np.argmax(fired)])


@pytest.mark.parametrize("model", ["lif_int", "hh"])
def test_strength_duration_curve(model):
    """Shorter pulses need stronger currents, levelling off at the rheobase (Lapicque 1907)."""
    durations = [1, 2, 5, 10, 20, 50]
    grid = np.arange(1, 700) if model == "lif_int" else np.arange(1, 60)
    amps = [threshold_current(model, d, grid) for d in durations]
    assert all(a >= b for a, b in zip(amps, amps[1:])) and amps[0] > 2 * amps[-1]
    if model == "lif_int":
        assert abs(amps[0] * 1 - amps[1] * 2) <= 0.1 * amps[0]       # brief pulses: a constant charge
        assert amps[-1] <= 2 * 8.5                                    # long pulses: near the rheobase (8.5 units)


def test_absolute_refractory_period_sets_the_maximum_rate():
    """Under a very strong drive the cell fires once every refractory + 1 ticks."""
    for refr in (2, 3, 5):
        r = spike_raster(net(1, refractory=refr), "lif_int", np.full(1, 3000, np.int32), 120)[:, 0]
        assert set(np.diff(np.nonzero(r)[0]).tolist()) == {refr + 1}


def test_type_one_and_type_two_onset_of_firing():
    """Integrate-and-fire starts firing at low rates (type I); Hodgkin-Huxley starts abruptly near 50 Hz (type II;
    Hodgkin 1948)."""
    lif = fi_curve(np.arange(8, 14), ticks=2000) * 1000
    assert 0 < lif[lif > 0][0] < 15
    units = np.round(np.arange(5.6, 7.5, 0.1) / hh.SCALE).astype(int)
    f = fi_curve(units, model="hh") * 1000
    assert f[f > 20][0] > 40 and not np.any((f > 2) & (f < 30))


@pytest.mark.parametrize("model,shows", [("hh", True), ("lif_int", False), ("two_compartment", False)])
def test_accommodation_to_slow_ramps(model, shows):
    """A step fires the cell, a slow ramp to the same amplitude does not when the cell accommodates (Hodgkin & Huxley
    1952). Integrate-and-fire models do not accommodate."""
    ticks, amp = 400, 12
    step = np.zeros((ticks, 1), np.int32)
    step[50:] = amp
    ramp = np.zeros((ticks, 1), np.int32)
    ramp[50:, 0] = np.minimum(np.arange(ticks - 50) * amp // 300, amp)
    s = spike_raster(net(1, refractory=3), model, step, ticks).sum()
    r = spike_raster(net(1, refractory=3), model, ramp, ticks).sum()
    assert s > 0
    assert (r == 0) == shows


@pytest.mark.parametrize("model,shows", [("hh", True), ("lif_int", False), ("two_compartment", False)])
def test_rebound_spike_after_inhibition(model, shows):
    """Release from a hyperpolarising step fires a Hodgkin-Huxley cell (anode-break excitation); integrate-and-fire
    cells need an added current for it (`currents.t_current`, tested in test_currents)."""
    e = pulse(-30, 50, 100, 300)
    r = spike_raster(net(1, refractory=3), model, e, 300)[:, 0]
    assert r[:150].sum() == 0
    assert (r[150:].sum() > 0) == shows


def test_temporal_summation_window_follows_the_membrane_time_constant():
    """Two sub-threshold inputs fire the cell only when close in time; a slower leak widens the window."""
    def window(shift_v):
        gaps = np.arange(1, 80)
        e = np.zeros((200, len(gaps)), np.int32)
        e[10] = 300
        e[10 + gaps, np.arange(len(gaps))] = 300
        fired = spike_raster(net(len(gaps), shift_v=shift_v), "lif_int", e, 200).sum(0) > 0
        return int(gaps[fired].max()) if fired.any() else 0
    single = np.zeros((200, 1), np.int32)
    single[10, 0] = 300
    assert spike_raster(net(1), "lif_int", single, 200).sum() == 0
    assert 5 < window(5) < 80 and window(3) < window(5)


def test_lateral_inhibition_enhances_an_edge():
    """Cells that inhibit their neighbours exaggerate a step of input: the bright side of the edge fires more, the dark
    side less, than the interior (Mach bands; Hartline & Ratliff 1957)."""
    n = 20
    syn = [(i, j, -60, 1) for i in range(n) for j in range(n) if i != j and abs(i - j) <= 2]
    inp = np.where(np.arange(n) < 10, 40, 20).astype(np.int32)
    r = spike_raster(net(n, syn, refractory=2), "lif_int", inp, 1000).sum(0)
    bright, dark = r[4:7].mean(), r[13:16].mean()
    assert r[9] > bright > dark > r[10]


def test_coincidence_detection_with_axonal_delays():
    """Detectors fed by two delay lines fire where the delays cancel the timing difference of the inputs: a place
    code of time (Jeffress 1948). One input alone fires no detector."""
    K = 7
    syn = [s for k in range(K) for s in ((0, 2 + k, 5000, 1 + k), (1, 2 + k, 5000, K - k))]

    def cell(i):
        return dict(refractory=30) if i < 2 else dict(shift_v=1, shift_s=1, refractory=30)
    centres = []
    for dt in (-4, -2, 0, 2, 4):
        e = np.zeros((80, 2 + K), np.int32)
        e[20, 0] = e[20 + dt, 1] = 3000
        d = spike_raster(net(2 + K, syn, cell), "lif_int", e, 80)[:, 2:].sum(0)
        assert 0 < d.sum() <= 3
        centres.append(float(np.average(np.arange(K), weights=d)))
    assert all(a < b for a, b in zip(centres, centres[1:]))
    one = np.zeros((80, 2 + K), np.int32)
    one[20, 0] = 3000
    assert spike_raster(net(2 + K, syn, cell), "lif_int", one, 80)[:, 2:].sum() == 0


def test_recurrent_excitation_holds_persistent_activity():
    """A group with recurrent excitation is bistable: a brief pulse switches it on, it stays on without input, and a
    brief inhibitory pulse switches it off (cf. the bistable populations of Wilson & Cowan 1972)."""
    n = 10
    syn = [(i, j, 250, 1) for i in range(n) for j in range(n) if i != j]
    e = np.zeros((400, n), np.int32)
    e[50:55] = 3000
    e[250:255] = -3000
    r = spike_raster(net(n, syn, refractory=3), "lif_int", e, 400).sum(1)
    assert r[:50].sum() == 0 and r[200:250].sum() > 0 and r[270:].sum() == 0


def test_mutual_inhibition_makes_a_flip_flop():
    """Two driven cells that inhibit each other: one wins and silences the other, and a brief pulse to the loser
    switches the state. Without a slow fatigue current they do not alternate (no half-centre oscillation)."""
    syn = [(0, 1, -2000, 1), (1, 0, -2000, 1)]
    e = np.full((900, 2), 30, np.int32)
    e[:30, 1] = 0                                          # cell 0 starts first
    e[450:455, 1] = 3000                                   # pulse to the loser
    r = spike_raster(net(2, syn, refractory=3), "lif_int", e, 900)
    first, second = r[100:450].sum(0), r[550:].sum(0)
    assert first[0] > 0 and first[1] == 0
    assert second[1] > 0 and second[0] == 0
