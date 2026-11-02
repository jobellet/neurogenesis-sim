import pytest
import numpy as np
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.spiking.network import SNNNetwork, NeuronData, SynapseData
from neurogenesis.development.grow import grow
from neurogenesis.development.plan import BodyPlan

def test_add_cells():
    t = Tissue.empty(K=2)
    t.add_cells(3, positions=np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]], dtype=np.float64))
    assert len(t.alive) == 3
    assert t.cell_id.tolist() == [0, 1, 2]
    assert t.lineage_id.tolist() == [0, 1, 2]
    assert t.parent_id.tolist() == [-1, -1, -1]
    assert t.clone_id.tolist() == [0, 1, 2]
    assert t.expression.shape == (3, 2)
    
    t.add_cells(2, parent_ids=np.array([1, 2], dtype=np.int32))
    assert len(t.alive) == 5
    assert t.cell_id.tolist() == [0, 1, 2, 3, 4]
    assert t.parent_id.tolist() == [-1, -1, -1, 1, 2]
    assert t.clone_id.tolist() == [0, 1, 2, 1, 2]

def test_lineage_three_generations():
    t = Tissue.empty()
    # Gen 1: Founder 0
    t.add_cells(1)
    assert t.cell_id[0] == 0
    assert t.parent_id[0] == -1
    assert t.clone_id[0] == 0

    # Gen 2: Child 1 from parent 0
    t.add_cells(1, parent_ids=np.array([0], dtype=np.int32))
    assert t.cell_id[1] == 1
    assert t.parent_id[1] == 0
    assert t.clone_id[1] == 0

    # Gen 3: Grandchild 2 from parent 1
    t.add_cells(1, parent_ids=np.array([1], dtype=np.int32))
    assert t.cell_id[2] == 2
    assert t.parent_id[2] == 1
    assert t.clone_id[2] == 0  # clone_id must trace back to founder 0!

    assert t.clone_id.tolist() == [0, 0, 0]

def test_kill_and_compact():
    t = Tissue.empty()
    t.add_cells(5, positions=np.zeros((5, 3), dtype=np.float64))
    assert len(t.clone_id) == 5

    mask = np.array([False, True, False, True, False]) # kill cells 1 and 3
    t.kill(mask)
    assert t.alive.tolist() == [True, False, True, False, True]
    
    t.compact()
    assert len(t.alive) == 3
    assert len(t.clone_id) == 3
    assert len(t.cell_id) == 3
    assert t.alive.tolist() == [True, True, True]
    assert t.cell_id.tolist() == [0, 2, 4]
    assert t.clone_id.tolist() == [0, 2, 4]

def test_kill_and_compact_with_valid_synapses():
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3), dtype=np.float64))
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 1, 2, 3, 0], dtype=np.int32),
        post=np.array([1, 2, 3, 0, 2], dtype=np.int32), # 0->2 is valid
        weight=np.array([10, 20, 30, 40, 50], dtype=np.int32),
        delay=np.array([1, 2, 3, 4, 5], dtype=np.int32)
    )
    
    mask = np.array([False, True, False, True]) # kill cells 1 and 3
    t.kill(mask)
    t.compact()
    
    # Surviving cells: old index 0 -> new index 0, old index 2 -> new index 1
    # Only synapse 0->2 survives, remapped to 0->1
    assert t.connectivity.pre.tolist() == [0]
    assert t.connectivity.post.tolist() == [1]
    assert t.connectivity.weight.tolist() == [50]
    assert t.connectivity.delay.tolist() == [5]

def test_subset():
    t = Tissue.empty()
    t.expression_names = ["geneA", "geneB"]
    t.add_cells(5, K=2)
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 1, 3, 4, 1], dtype=np.int32),
        post=np.array([1, 2, 4, 0, 4], dtype=np.int32),
        weight=np.array([1, 2, 3, 4, 5], dtype=np.int32),
        delay=np.array([1, 1, 1, 1, 1], dtype=np.int32)
    )
    
    t_sub = t.subset(np.array([1, 3, 4]))
    assert len(t_sub.alive) == 3
    assert t_sub.cell_id.tolist() == [1, 3, 4]
    assert t_sub.expression_names == ["geneA", "geneB"]
    
    assert t_sub.connectivity.pre.tolist() == [1, 0]
    assert t_sub.connectivity.post.tolist() == [2, 2]
    assert t_sub.connectivity.weight.tolist() == [3, 5]

def test_concatenate_no_duplicate_ids():
    t1 = Tissue.empty(K=1)
    t1.expression_names = ["morphogen"]
    t1.add_cells(3)
    
    t2 = Tissue.empty(K=1)
    t2.expression_names = ["morphogen"]
    t2.add_cells(3)
    
    assert t1.cell_id.tolist() == [0, 1, 2]
    assert t2.cell_id.tolist() == [0, 1, 2]
    
    t = Tissue.concatenate([t1, t2])
    assert len(t.alive) == 6
    # cell_ids must be strictly unique!
    assert len(np.unique(t.cell_id)) == 6
    assert t.cell_id.tolist() == [0, 1, 2, 3, 4, 5]
    assert t.clone_id.tolist() == [0, 1, 2, 3, 4, 5]
    assert t.expression_names == ["morphogen"]

from neurogenesis.development import BodyPlan, Region, FixedPlacement

def test_roundtrip_bit_for_bit_from_grow():
    plan = BodyPlan(
        name="toy", regions=[
            Region("sheet", (0, 0, 0), (10, 10, 10), FixedPlacement([[(i + 0.5) / 4, (j + 0.5) / 4, ch] for i in range(2) for j in range(2) for ch in (0.0, 1.0)]), role=1),
            Region("map", (20, 0, 0), (20, 20, 20)),
            Region("inter", (20, 30, 0), (10, 10, 10), sign="inh"),
            Region("out", (50, 0, 0), (5, 10, 10), FixedPlacement([[0.5, 0.25, 0.5], [0.5, 0.75, 0.5]]), role=2)],
        projections=[("sheet", "map"), ("map", "map"), ("map", "inter"), ("inter", "map"), ("map", "out")])
    
    genome = dict(
        count=dict(map=20, inter=5), inh_weight_factor=2.0,
        migration=dict(map=dict(mean=np.full(3, 0.5), spread=0.3), inter=dict(mean=np.full(3, 0.5), spread=0.3)),
        inhibitory=dict(map=dict(a0=-1.4, a=np.zeros(3)), inter=dict(a0=0.0, a=np.zeros(3))),
        excitability=dict(map=dict(shift_v=5, shift_s=4))
    )
    genome["guidance"] = {p: dict(B=np.eye(3), c=np.zeros(3), sigma=0.3, p0=0.5, w=100.0) for p in plan.projections}
    
    net_orig = grow(plan, genome, seed=123)
    
    # Network -> Tissue -> Network
    tissue = Tissue.from_network(net_orig)
    net_rt = tissue.to_network()
    
    assert net_orig.num_neurons == net_rt.num_neurons
    assert net_orig.num_synapses == net_rt.num_synapses
    
    # Exact bit-for-bit field by field check on every neuron
    for n1, n2 in zip(net_orig.neurons, net_rt.neurons):
        assert n1.id == n2.id
        assert n1.x == n2.x
        assert n1.y == n2.y
        assert n1.z == n2.z
        assert n1.dir_x == n2.dir_x
        assert n1.dir_y == n2.dir_y
        assert n1.dir_z == n2.dir_z
        assert n1.mode == n2.mode
        assert n1.shift_v == n2.shift_v
        assert n1.shift_s == n2.shift_s
        assert n1.base_weight == n2.base_weight
        assert n1.conn_radius == n2.conn_radius
        assert n1.conn_prob == n2.conn_prob
        assert n1.burst_period == n2.burst_period
        assert n1.burst_duty == n2.burst_duty
        assert n1.poisson_hz == n2.poisson_hz
        assert n1.refractory == n2.refractory
        assert n1.role == n2.role
        assert n1.compartment == n2.compartment
        assert n1.threshold == n2.threshold

    # Exact check on every synapse
    for s1, s2 in zip(net_orig.synapses, net_rt.synapses):
        assert s1.pre == s2.pre
        assert s1.post == s2.post
        assert s1.weight == s2.weight
        assert s1.delay == s2.delay

def test_sign_as_single_source_of_truth():
    t = Tissue.empty()
    # Add an inhibitory cell (sign = -1) with base_weight = 100
    t.add_cells(1, sign=np.array([-1], dtype=np.int8), base_weight=np.array([100], dtype=np.int32))
    net = t.to_network()
    # base_weight in network must be negative (-100) because sign is -1!
    assert net.neurons[0].base_weight == -100

    # Add an excitatory cell (sign = 1) with base_weight = -50
    t2 = Tissue.empty()
    t2.add_cells(1, sign=np.array([1], dtype=np.int8), base_weight=np.array([-50], dtype=np.int32))
    net2 = t2.to_network()
    # base_weight in network must be positive (+50) because sign is +1!
    assert net2.neurons[0].base_weight == 50


def test_generation_optional_and_carried_through_operations():
    t = Tissue.empty()
    t.add_cells(3)
    assert t.generation.dtype == np.int32 and t.generation.tolist() == [0, 0, 0]
    t.add_cells(2, parent_ids=np.array([0, 1], dtype=np.int32), generation=np.array([1, 2], dtype=np.int32))
    assert t.generation.tolist() == [0, 0, 0, 1, 2]
    assert t.subset(np.array([4, 0])).generation.tolist() == [2, 0]
    cat = Tissue.concatenate([t, t.subset(np.array([3]))])
    assert cat.generation.tolist() == [0, 0, 0, 1, 2, 1]
    t.kill(np.array([True, False, False, True, False]))
    t.compact()
    assert t.generation.tolist() == [0, 0, 2]
    back = Tissue.from_network(t.to_network())
    assert back.generation.tolist() == [0, 0, 0]  # not part of the network: defaults on the way back
    # Constructed without the field (as before it existed): defaults to zeros.
    kwargs = {k: getattr(t, k) for k in t.__dataclass_fields__ if k != "generation"}
    assert Tissue(**kwargs).generation.tolist() == [0, 0, 0]


def test_add_cells_keeps_int32_base_weight():
    t = Tissue.empty()
    t.add_cells(3, base_weight=np.array([2, -3, 4]), sign=np.array([1, -1, 1]))
    t.add_cells(2)
    assert t.base_weight.dtype == np.int32 and list(t.base_weight) == [2, -3, 4, 1, 1]
    net = SNNNetwork(neurons=[NeuronData(id=i, x=0.0, y=0.0, z=0.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, shift_v=5,
                                         shift_s=4, base_weight=w, conn_radius=0.0, conn_prob=0.0, refractory=3)
                              for i, w in enumerate((5, -7))], synapses=[])
    assert Tissue.from_network(net).base_weight.dtype == np.int32


def test_add_cells_clone_id_matches_python_lookup():
    def old_clone_ids(cell_id, clone_id, par_id, c_id):  # the per-cell dict lookup it replaces
        out = np.zeros(len(par_id), dtype=np.int32)
        id_to_clone = dict(zip(cell_id, clone_id)) if len(cell_id) > 0 else {}
        for idx in range(len(par_id)):
            pid = par_id[idx]
            out[idx] = c_id[idx] if pid == -1 or pid not in id_to_clone else id_to_clone[pid]
        return out

    rng = np.random.default_rng(0)
    for trial in range(20):
        t = Tissue.empty()
        n0 = int(rng.integers(0, 30))
        if n0:  # existing cells with duplicated ids and arbitrary clones
            t.add_cells(n0, cell_id=rng.integers(0, 40, n0), clone_id=rng.integers(0, 100, n0))
        before = (t.cell_id.copy(), t.clone_id.copy())
        n = int(rng.integers(1, 30))
        par = rng.integers(-1, 50, n).astype(np.int32)
        par[rng.random(n) < 0.3] = -1
        t.add_cells(n, parent_ids=par)
        expected = old_clone_ids(*before, par, t.cell_id[n0:])
        assert np.array_equal(t.clone_id[n0:], expected)
        assert t.clone_id.dtype == np.int32


# K2: transmitter, receptor expression, receptor class and morphology arrays -----------------------------------------
def _k2_tissue():
    from neurogenesis.tissue import SparseConnectivity
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3)), transmitter=np.array([1, 2, 3, 0]),
                receptor_expression=np.arange(8, dtype=np.float32).reshape(4, 2))
    t.connectivity = SparseConnectivity(np.array([0, 1, 2, 3], np.int32), np.array([1, 2, 3, 0], np.int32),
                                        np.array([5, 6, 7, 8], np.int32), np.array([1, 2, 3, 4], np.int32),
                                        receptor_class=np.array([1, 2, 3, 4], np.uint8),
                                        path_length=np.array([0.1, 0.2, 0.3, 0.4], np.float32))
    return t


def test_k2_defaults_are_neutral():
    t = Tissue.empty()
    t.add_cells(3, positions=np.zeros((3, 3)))
    assert t.transmitter.tolist() == [0, 0, 0] and t.receptor_expression.shape == (3, 0) and t.morphology is None
    assert t.connectivity.receptor_class.dtype == np.uint8 and t.connectivity.pre_node is None


def test_k2_arrays_follow_compact_subset_and_concatenate():
    t = _k2_tissue()
    t.alive[1] = False
    t.compact()
    assert t.transmitter.tolist() == [1, 3, 0]
    np.testing.assert_array_equal(t.receptor_expression, [[0, 1], [4, 5], [6, 7]])
    c = t.connectivity
    assert list(zip(c.pre, c.post)) == [(1, 2), (2, 0)]                  # synapses 2->3 and 3->0 survive
    assert c.receptor_class.tolist() == [3, 4] and np.allclose(c.path_length, [0.3, 0.4])
    s = _k2_tissue().subset(np.array([2, 3]))
    assert s.connectivity.receptor_class.tolist() == [3] and s.transmitter.tolist() == [3, 0]
    plain = Tissue.empty()
    plain.add_cells(2, positions=np.zeros((2, 3)))
    j = Tissue.concatenate([_k2_tissue(), plain])
    assert j.receptor_expression.shape == (6, 2) and j.transmitter.tolist() == [1, 2, 3, 0, 0, 0]
    assert len(j.connectivity.path_length) == 4 and j.memory_bytes() > _k2_tissue().memory_bytes()


def test_k2_synapse_stages_keep_arrays_aligned():
    from neurogenesis.stages.base import STAGE_REGISTRY
    import neurogenesis.stages  # noqa: F401
    t = _k2_tissue()
    t = STAGE_REGISTRY["prune"]().run(t, {"threshold": 7}, {}, {}, np.random.default_rng(0))
    assert t.connectivity.receptor_class.tolist() == [3, 4]
    t = STAGE_REGISTRY["connect_by_hand"]().run(t, {"pre": [0], "post": [1]}, {}, {}, np.random.default_rng(0))
    c = t.connectivity
    assert c.receptor_class.tolist() == [3, 4, 0] and np.isnan(c.path_length[-1])
    c.receptor_class = np.array([1], np.uint8)                       # a real mismatch is reported, never guessed
    with pytest.raises(ValueError, match="receptor_class"):
        c.take(np.ones(3, bool))


def test_k2_direct_array_edits_keep_a_default_receptor_class():
    t = Tissue.empty()
    t.add_cells(2, positions=np.zeros((2, 3)))
    t.connectivity.pre = np.array([0], np.int32)
    t.connectivity.post = np.array([1], np.int32)
    t.connectivity.weight = np.array([1], np.int32)
    t.connectivity.delay = np.array([1], np.int32)
    assert len(t.subset(np.arange(2)).connectivity.receptor_class) == 1


def test_k6_cycling_defaults_and_carried_through_operations():
    from neurogenesis.stages.base import STAGE_REGISTRY
    import neurogenesis.stages  # noqa: F401

    t = Tissue.empty()
    t = STAGE_REGISTRY["seed_cells"]().run(t, {"N": 3, "position": [0.0, 0.0, 0.0]}, {}, {}, np.random.default_rng(0))
    assert t.cycling.dtype == bool and t.cycling.tolist() == [True, True, True]

    t = STAGE_REGISTRY["place_by_hand"]().run(t, {"positions": [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]}, {}, {}, np.random.default_rng(0))
    assert t.cycling.tolist() == [True, True, True, False, False]

    t.add_cells(1, cycling=np.array([False]))
    assert t.cycling.tolist() == [True, True, True, False, False, False]

    sub = t.subset(np.array([4, 0, 5]))
    assert sub.cycling.tolist() == [False, True, False]

    cat = Tissue.concatenate([sub, t.subset(np.array([1, 3]))])
    assert cat.cycling.tolist() == [False, True, False, True, False]

    t.kill(np.array([True, False, False, True, False, False]))
    t.compact()
    assert t.cycling.tolist() == [True, True, False, False]

    back = Tissue.from_network(t.to_network())
    assert back.cycling.tolist() == [True, True, False, False]

    # Constructed without cycling field: defaults to True for all cells.
    kwargs = {k: getattr(t, k) for k in t.__dataclass_fields__ if k != "cycling"}
    assert Tissue(**kwargs).cycling.tolist() == [True, True, True, True]



def test_k6_plastic_mask_defaults_and_carried_through_operations():
    t = Tissue.empty()
    t.add_cells(4)
    c = SparseConnectivity(np.array([0, 1, 2, 3], np.int32), np.array([1, 2, 3, 0], np.int32),
                           np.array([5, 6, 7, 8], np.int32), np.array([1, 1, 1, 1], np.int32))
    t.connectivity = c
    # Default: no array stored (memory unchanged), every synapse plastic.
    assert c.plastic is None and c.plastic_mask().tolist() == [True] * 4
    nbytes = t.memory_bytes()
    assert Tissue.from_network(t.to_network()).connectivity.plastic is None
    assert t.memory_bytes() == nbytes

    t.connectivity.plastic = np.array([True, False, True, False])
    # Appended synapses (as connectivity stages add them) are plastic.
    app = t.connectivity.append([0], [2], [1], [1])
    assert app.plastic.tolist() == [True, False, True, False, True]
    assert SparseConnectivity.concat([c.take(slice(None)), SparseConnectivity.empty().append([0], [1], [1], [1])]
                                     ).plastic.tolist() == [True, False, True, False, True]

    sub = t.subset(np.array([1, 2, 3]))                          # keeps synapses 1->2, 2->3
    assert sub.connectivity.plastic.tolist() == [False, True]
    cat = Tissue.concatenate([sub, t])
    assert cat.connectivity.plastic.tolist() == [False, True, True, False, True, False]

    back = Tissue.from_network(t.to_network())
    assert back.connectivity.plastic.tolist() == [True, False, True, False]

    t.kill(np.array([True, False, False, False]))                 # drops synapses 0->1 and 3->0
    t.compact()
    assert t.connectivity.plastic.tolist() == [False, True]
    assert t.connectivity.plastic_mask().tolist() == [False, True]
