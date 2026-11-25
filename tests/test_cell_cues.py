"""C27: cues released by cells (`CueField`, `secrete_cue`) and receptor-gated, two-phase growth in `grow_arbors`."""
import tracemalloc

import numpy as np
import pytest

import neurogenesis.stages  # noqa: F401
from neurogenesis.arbors import AXON
from neurogenesis.fields import field_from_dict
from neurogenesis.fields.maps import CueField
from neurogenesis.stages.base import STAGE_REGISTRY
from neurogenesis.tissue import Tissue


def _run(op, t, params, fields, seed=0):
    return STAGE_REGISTRY[op]().run(t, params, {}, fields, np.random.default_rng(seed))


def _two_groups(n_src=20, n_tgt=20, seed=0):
    """Growing cells (type 0) near x = 0, target cells (type 1) near x = 20, in a 20 x 10 x 10 slab."""
    rng = np.random.default_rng(seed)
    t = Tissue.empty()
    t.add_cells(n_src, positions=np.c_[rng.uniform(0, 1, n_src), rng.uniform(0, 10, (n_src, 2))], cell_type=np.zeros(n_src, np.int32))
    t.add_cells(n_tgt, positions=np.c_[rng.uniform(19, 20, n_tgt), rng.uniform(0, 10, (n_tgt, 2))], cell_type=np.ones(n_tgt, np.int32))
    return t


def test_cue_field_profile_round_trip_and_empty():
    f = CueField([[0, 0, 0]], [2.0], length=3.0)
    r = np.array([0.0, 1.0, 3.0, 6.0])
    np.testing.assert_allclose(f.values(np.c_[r, np.zeros(4), np.zeros(4)]), 2.0 * np.exp(-r / 3.0))
    assert f.values(np.array([[20.0, 0, 0]]))[0] == 0.0                      # beyond cutoff x length
    g = field_from_dict(f.to_dict())
    q = np.random.default_rng(1).uniform(-5, 5, (50, 3))
    np.testing.assert_allclose(g.values(q), f.values(q))
    np.testing.assert_array_equal(CueField(np.zeros((0, 3)), length=1.0).values(q), np.zeros(50))
    with pytest.raises(ValueError):
        CueField([[0, 0, 0]], length=0.0)


def test_secrete_cue_neutral_selection_expression_and_add():
    t = _two_groups()
    fields = {}
    _run("secrete_cue", t, {}, fields)
    assert fields == {}                                                     # no name: no-op
    _run("secrete_cue", t, {"name": "netrin", "cells": {"cell_type": [1]}, "length": 4.0}, fields)
    f = fields["netrin"]
    assert len(f.points) == 20 and np.all(f.points[:, 0] >= 19)
    near, far = f.values(np.array([[18.0, 5, 5], [2.0, 5, 5]]))
    assert near > far > 0
    t.expression = np.zeros((len(t.alive), 2))
    t.expression[:5, 1] = 1.0                                               # five type-0 cells express the ligand
    _run("secrete_cue", t, {"name": "x", "cells": {"expressing": 1, "threshold": 0.5},
                             "amount": {"expression": 1, "scale": 3.0}, "length": 2.0}, fields)
    assert len(fields["x"].points) == 5 and np.allclose(fields["x"].amounts, 3.0)
    _run("secrete_cue", t, {"name": "netrin", "cells": {"cell_type": [0]}, "length": 4.0, "mode": "add"}, fields)
    assert len(fields["netrin"].points) == 40
    with pytest.raises(ValueError):
        _run("secrete_cue", t, {"name": "netrin", "cells": {"cell_type": [0]}, "length": 1.0, "mode": "add"}, fields)


def test_secrete_cue_from_axon_terminals():
    t = _two_groups(5, 5)
    fields = {}
    t = _run("grow_arbors", t, {"cells": {"cell_type": [0]}, "steps": 10, "compartment": "axon", "direction": [1, 0, 0],
                                "angle_noise": 0.0, "step_length": 1.0}, fields)
    _run("secrete_cue", t, {"name": "aff", "cells": {"cell_type": [0]}, "source": "terminals", "length": 1.0}, fields)
    pts = fields["aff"].points
    assert len(pts) == 5 and np.all(pts[:, 0] >= 10.0 - 1e-6)                 # the tips, not the somata


def _axon_x(t, fields, params, seed=0):
    m = _run("grow_arbors", t, {"cells": {"cell_type": [0]}, "steps": 25, "compartment": "axon", "step_length": 0.8,
                                "angle_noise": 0.4, **params}, fields, seed).morphology
    return m, m.xyz[m.compartment == AXON][:, 0]


def test_guidance_attracts_or_repels_by_receptor_gain():
    fields = {}
    t = _two_groups()
    _run("secrete_cue", t, {"name": "cue", "cells": {"cell_type": [1]}, "length": 8.0}, fields)
    _, free = _axon_x(_two_groups(), fields, {})
    _, att = _axon_x(_two_groups(), fields, {"guidance": [{"field": "cue", "gain": 1.5}]})
    _, rep = _axon_x(_two_groups(), fields, {"guidance": [{"field": "cue", "gain": -1.5}]})
    _, rel = _axon_x(_two_groups(), fields, {"guidance": [{"field": "cue", "gain": 6.0, "sensing": "relative",
                                                            "saturation": 0.1}]})
    assert np.mean(att) > np.mean(free) + 4 and np.mean(rep) < np.mean(free) - 1 and np.mean(rel) > np.mean(free) + 4
    t2 = _two_groups()
    t2.expression = np.zeros((len(t2.alive), 1))
    t2.expression[:10, 0] = 1.0                                             # half of the growing cells have the receptor
    m, _ = _axon_x(t2, fields, {"guidance": [{"field": "cue", "gain": {"expression": 0, "scale": 1.5}}]})
    ax = m.compartment == AXON
    with_r, without_r = m.xyz[ax & (m.cell < 10)][:, 0], m.xyz[ax & (m.cell >= 10) & (m.cell < 20)][:, 0]
    assert np.mean(with_r) > np.mean(without_r) + 3


def test_two_phase_growth_shaft_then_arbor_in_target():
    fields = {}
    t = _two_groups()
    _run("secrete_cue", t, {"name": "cue", "cells": {"cell_type": [1]}, "length": 3.0}, fields)
    thr = float(np.median(fields["cue"].values(np.c_[np.full(20, 17.0), np.random.default_rng(0).uniform(0, 10, (20, 2))])))
    params = {"guidance": [{"field": "cue", "gain": 2.0}], "branch_prob": 0.0, "target_field": "cue",
              "target_threshold": thr, "arbor_branch_prob": 0.4, "arbor_step_length": 0.4, "arbor_angle_noise": 0.8,
              "steps": 60}
    m, _ = _axon_x(t, fields, params)
    new = (m.compartment == AXON)
    inside = fields["cue"].values(m.xyz.astype(float)) >= thr
    nc = m.children_count()
    assert np.all(nc[new & ~inside] <= 1)                                   # unbranched shafts on the way
    assert np.sum(nc[new & inside] >= 2) > 20                               # arbors in the target region
    parent_inside = np.r_[inside, False][m.parent]
    assert np.all(inside[new & parent_inside])                              # arbors stay in the target (confined)
    m2, _ = _axon_x(_two_groups(), fields, params)
    np.testing.assert_array_equal(m.xyz, m2.xyz)                            # deterministic


def test_without_new_keys_growth_is_unchanged():
    fields = {"cue": CueField([[20.0, 5, 5]], length=5.0)}
    a, _ = _axon_x(_two_groups(), fields, {"branch_prob": 0.1})
    b, _ = _axon_x(_two_groups(), fields, {"branch_prob": 0.1, "guidance": []})
    c, _ = _axon_x(_two_groups(), fields, {"branch_prob": 0.1, "guidance": [{"field": "cue", "gain": 0.0}]})
    np.testing.assert_array_equal(a.xyz, b.xyz)
    np.testing.assert_array_equal(a.xyz, c.xyz)


def test_secrete_cue_declared_memory_within_factor_three():
    n = 20000
    t = Tissue.empty()
    t.add_cells(n, positions=np.random.default_rng(0).uniform(0, 100, (n, 3)))
    params = {"name": "c", "length": 2.0}
    fields = {}
    tracemalloc.start()
    _run("secrete_cue", t, params, fields)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    declared = STAGE_REGISTRY["secrete_cue"].cost(n, 0, params)[0]
    assert declared / 3 <= peak <= declared * 3
