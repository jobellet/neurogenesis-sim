"""Structural measures (neurogenesis.analysis.structure) and the analysis package's public names."""
import numpy as np
import pytest

from neurogenesis.analysis import (connection_lengths, fi_curve, modularity, nearest_neighbour_regularity,  # noqa: F401
                                   within_group_fraction)


def test_modularity_of_known_partitions():
    pre, post = np.array([0, 1, 2, 3]), np.array([1, 0, 3, 2])
    assert modularity(pre, post, [0, 0, 1, 1]) == pytest.approx(0.5)          # two disconnected modules
    assert modularity(pre, post, [0, 1, 0, 1]) < 0                           # a partition against the wiring
    rng = np.random.default_rng(1)
    a, b = rng.integers(0, 200, 20000), rng.integers(0, 200, 20000)
    assert abs(modularity(a, b, np.arange(200) % 4)) < 0.02                  # random graph
    assert np.isnan(modularity([], [], []))


def test_within_group_fraction_and_lengths():
    pos = np.array([[0.0, 0, 0], [3.0, 4, 0], [0, 0, 1]])
    assert connection_lengths(pos, [0, 0], [1, 2]).tolist() == [5.0, 1.0]
    assert within_group_fraction([0, 0, 1], [1, 2, 2], [7, 7, 8]) == pytest.approx(1 / 3)


def test_old_import_paths_still_work():
    from neurogenesis.analysis import cells, criticality, structure  # noqa: F401
    assert nearest_neighbour_regularity(np.random.default_rng(0).random((200, 2))) == pytest.approx(1.9, abs=0.3)
