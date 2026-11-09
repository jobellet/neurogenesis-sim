import copy

import numpy as np

from neurogenesis.stages.partner import PartnerSelectStage
from neurogenesis.tissue import Tissue, SparseConnectivity


def _tissue(n=60, seed=0):
    t = Tissue.empty()
    t.add_cells(n, positions=np.zeros((n, 3)), cell_type=(np.arange(n) % 2).astype(np.int32))
    pre, post = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    keep = pre != post
    pre, post = pre[keep].astype(np.int32), post[keep].astype(np.int32)
    t.connectivity = SparseConnectivity(pre, post, np.full(len(pre), 5, np.int32), np.ones(len(pre), np.int32))
    return t


def _run(t, params, seed=0):
    return PartnerSelectStage().run(t, params, {}, {}, np.random.default_rng(seed))


def test_neutral_is_noop():
    t = _tissue(10)
    out = _run(copy.deepcopy(t), {})
    assert np.array_equal(out.connectivity.pre, t.connectivity.pre)
    assert PartnerSelectStage.cost(0, 0, {}) == (0, 0)


def test_identity_matrix_keeps_only_same_channel_pairs():
    t = _tissue()
    out = _run(t, {"compat": [[1, 0], [0, 1]]})
    ct = t.cell_type
    assert len(out.connectivity.pre) > 0
    assert np.all(ct[out.connectivity.pre] == ct[out.connectivity.post])


def test_probabilities_are_respected():
    t = _tissue(80)
    n0 = len(t.connectivity.pre)
    out = _run(t, {"compat": [[0.5, 0.1], [0.9, 0.0]]})
    c = out.connectivity
    ct = t.cell_type
    frac = {(i, j): np.mean((ct[c.pre] == i) & (ct[c.post] == j)) * len(c.pre) / (n0 / 4) for i in (0, 1) for j in (0, 1)}
    assert abs(frac[(0, 0)] - 0.5) < 0.05 and abs(frac[(0, 1)] - 0.1) < 0.05
    assert abs(frac[(1, 0)] - 0.9) < 0.05 and frac[(1, 1)] == 0.0


def test_explicit_channels_expression_and_determinism():
    t = _tissue(20)
    a = _run(copy.deepcopy(t), {"compat": [[1, 0], [0, 1]], "channels": [0] * 10 + [1] * 10}, seed=3)
    b = _run(copy.deepcopy(t), {"compat": [[1, 0], [0, 1]], "channels": [0] * 10 + [1] * 10}, seed=3)
    assert np.array_equal(a.connectivity.pre, b.connectivity.pre)
    assert np.all((a.connectivity.pre < 10) == (a.connectivity.post < 10))
    out = _run(copy.deepcopy(t), {"compat": [[1, 0], [0, 1]], "channels": [5] * 20})   # outside the matrix: kept
    assert len(out.connectivity.pre) == len(t.connectivity.pre)


def test_cost_linear():
    b1, o1 = PartnerSelectStage.cost(100, 1000, {})
    b2, o2 = PartnerSelectStage.cost(200, 2000, {})
    assert b2 == 2 * b1 and o2 == 2 * o1


# transmitter-receptor match (P2) -----------------------------------------------------------------------------------
def _matched_tissue():
    from pathlib import Path
    from neurogenesis.pharmacology import load_profile
    path = str(Path(__file__).resolve().parents[1] / "examples" / "profiles" / "example_receptors.json")
    prof = load_profile(path)
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3)))
    t.transmitter = np.array([prof.bit("glutamate"), prof.bit("gaba"), 0, 0], np.int8)
    rex = np.zeros((4, len(prof.receptors)), np.float32)
    rex[2, prof.receptor_index("ionotropic_glutamate")] = 1.0
    rex[3, prof.receptor_index("gaba_a")] = 1.0
    rex[3, prof.receptor_index("classic")] = 1.0
    t.receptor_expression = rex
    pre, post = np.meshgrid(np.arange(4), np.arange(4), indexing="ij")
    keep = pre != post
    pre, post = pre[keep].astype(np.int32), post[keep].astype(np.int32)
    t.connectivity = SparseConnectivity(pre, post, np.full(len(pre), 5, np.int32), np.ones(len(pre), np.int32))
    return t, path


def test_receptor_match_keeps_only_compatible_pairs():
    t, path = _matched_tissue()
    out = _run(t, {"match_receptors": True, "profile": path})
    c = out.connectivity
    assert sorted(zip(c.pre.tolist(), c.post.tolist())) == [(0, 2), (1, 3)]


def test_receptor_match_allow_classic_min_level_and_compat():
    t, path = _matched_tissue()
    out = _run(copy.deepcopy(t), {"match_receptors": True, "profile": path, "allow_classic": True})
    assert sorted(set(out.connectivity.post.tolist())) == [2, 3]
    assert sum(out.connectivity.post == 3) == 3                  # classic receptor: every presynaptic cell
    out = _run(copy.deepcopy(t), {"match_receptors": True, "profile": path, "min_level": 1.0})
    assert len(out.connectivity.pre) == 0
    t.cell_type = np.array([0, 1, 1, 1], np.int32)                 # 0 -> 2 is now type 0 -> 1: blocked
    out = _run(copy.deepcopy(t), {"match_receptors": True, "profile": path, "compat": [[1, 0], [0, 1]]})
    assert list(zip(out.connectivity.pre.tolist(), out.connectivity.post.tolist())) == [(1, 3)]


def test_receptor_match_needs_profile_and_expression():
    import pytest
    t, path = _matched_tissue()
    with pytest.raises(ValueError):
        _run(copy.deepcopy(t), {"match_receptors": True})
    t.receptor_expression = np.zeros((4, 2), np.float32)
    with pytest.raises(ValueError):
        _run(t, {"match_receptors": True, "profile": path})
