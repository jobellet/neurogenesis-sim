"""C26 development during simulation: state carried across blocks, new cells, determinism."""
import numpy as np

import neurogenesis.stages  # noqa: F401
from neurogenesis.development.lifelong import develop_during_simulation
from neurogenesis.tissue import SparseConnectivity, Tissue


def _chain(n=5):
    t = Tissue.empty()
    t.add_cells(n, positions=np.random.default_rng(0).random((n, 3)))
    pre = np.arange(n - 1, dtype=np.int32)
    t.connectivity = SparseConnectivity(pre, pre + 1, np.full(n - 1, 400, np.int32), np.full(n - 1, 3, np.int32))
    return t


def _drive(tissue, block):
    ext = np.zeros(int(tissue.alive.sum()), np.int32)
    ext[0] = 150
    return ext


def test_blocks_without_development_equal_one_long_run():
    t = _chain()
    _, one = develop_during_simulation(t, [], blocks=1, ticks=120, ext_current=_drive)
    _, three = develop_during_simulation(t, [], blocks=3, ticks=40, ext_current=_drive)
    joined = np.concatenate([h["spikes"] for h in three])
    assert one[0]["spikes"].sum() > 0
    np.testing.assert_array_equal(joined, one[0]["spikes"])


def test_new_cells_join_without_disturbing_the_others():
    t = _chain()
    add = [{"operator": "place_by_hand", "name": "newborn", "params": {"positions": [[0.5, 0.5, 0.5]], "region": 1}}]
    grown, hist = develop_during_simulation(t, add, blocks=3, ticks=40, ext_current=_drive)
    assert [len(h["cell_id"]) for h in hist] == [5, 6, 7]
    assert len(grown.alive) == 7 and len(t.alive) == 5                 # the input tissue is not modified
    _, plain = develop_during_simulation(t, [], blocks=3, ticks=40, ext_current=_drive)
    for a, b in zip(hist, plain):                                         # unconnected newborn cells change nothing
        np.testing.assert_array_equal(a["spikes"][:, :5], b["spikes"])
    assert all(h["spikes"][:, 5:].sum() == 0 for h in hist)


def test_dead_cells_leave_and_the_rest_keep_their_state():
    t = _chain()
    kill = [{"operator": "apoptosis", "name": "die", "params": {"prob": [0, 0, 0, 0, 1]}}]   # the last cell dies
    _, hist = develop_during_simulation(t, kill, blocks=2, ticks=40, ext_current=_drive)
    assert hist[1]["cell_id"].tolist() == hist[0]["cell_id"][:4].tolist()
    _, plain = develop_during_simulation(t, [], blocks=2, ticks=40, ext_current=_drive)
    np.testing.assert_array_equal(hist[1]["spikes"], plain[1]["spikes"][:, :4])   # cell 4 sends nothing back


def test_deterministic():
    t = _chain()
    add = [{"operator": "place_by_hand", "name": "newborn", "params": {"positions": [[0.1, 0.2, 0.3]]}}]
    a = develop_during_simulation(t, add, blocks=3, ticks=30, ext_current=150)[1]
    b = develop_during_simulation(t, add, blocks=3, ticks=30, ext_current=150)[1]
    for x, y in zip(a, b):
        np.testing.assert_array_equal(x["spikes"], y["spikes"])
