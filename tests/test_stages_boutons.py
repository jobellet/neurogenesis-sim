import numpy as np
import pytest

from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.stages.base import Stage
from neurogenesis.params import Const

def test_cluster_boutons_stage():
    t = Tissue.empty()
    t.add_cells(4, cell_type=np.array([1, 1, 2, 2]))

    t.connectivity = SparseConnectivity(
        pre=np.array([0, 0, 2, 2]),
        post=np.array([1, 2, 0, 3]),
        weight=np.array([10, 10, 10, 10]),
        delay=np.array([1, 1, 1, 1])
    )

    contacts_param = {
        (1, 1): 5,
        (1, 2): {"type": "truncated_poisson", "mean": 3.0},
        (2, 1): [0.0, 0.0, 0.5, 0.5], # 50% 2 contacts, 50% 3 contacts
    }

    stage = Stage(name="cluster", operator="cluster_boutons", params={"contacts": Const(contacts_param)})

    rng = np.random.default_rng(42)
    t2 = stage.run(t, {}, {}, rng)

    assert t2.connectivity.contacts is not None
    assert t2.connectivity.contacts[0] == 5 # 1->1
    assert t2.connectivity.contacts[1] >= 1 # 1->2 truncated poisson
    assert t2.connectivity.contacts[2] in [2, 3] # 2->1 list
    assert t2.connectivity.contacts[3] == 1 # 2->2 unmapped default

    # Check weights scaled
    assert t2.connectivity.weight[0] == 50
    assert t2.connectivity.weight[1] == 10 * t2.connectivity.contacts[1]
    assert t2.connectivity.weight[2] == 10 * t2.connectivity.contacts[2]
    assert t2.connectivity.weight[3] == 10

def test_cluster_boutons_empty_tissue():
    t = Tissue.empty()
    stage = Stage(name="cluster", operator="cluster_boutons", params={})
    t2 = stage.run(t, {}, {}, np.random.default_rng(0))
    assert len(t2.alive) == 0

def test_cluster_boutons_no_contacts():
    t = Tissue.empty()
    t.add_cells(2, cell_type=np.array([1, 2]))
    t.connectivity = SparseConnectivity(
        pre=np.array([0]), post=np.array([1]), weight=np.array([10]), delay=np.array([1])
    )
    stage = Stage(name="cluster", operator="cluster_boutons", params={})
    t2 = stage.run(t, {}, {}, np.random.default_rng(0))
    assert getattr(t2.connectivity, "contacts", None) is None
