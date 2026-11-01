import pytest
import numpy as np
from neurogenesis.tissue import Tissue, SparseConnectivity
from neurogenesis.spiking.network import SNNNetwork, NeuronData, SynapseData

def test_add_cells():
    t = Tissue.empty(K=2)
    t.add_cells(3, positions=np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]], dtype=np.float32))
    assert len(t.alive) == 3
    assert t.lineage_id.tolist() == [0, 1, 2]
    assert t.parent_id.tolist() == [-1, -1, -1]
    assert t.expression.shape == (3, 2)
    
    t.add_cells(2, parent_ids=np.array([1, 2], dtype=np.int32))
    assert len(t.alive) == 5
    assert t.lineage_id.tolist() == [0, 1, 2, 3, 4]
    assert t.parent_id.tolist() == [-1, -1, -1, 1, 2]

def test_kill_and_compact():
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3), dtype=np.float32))
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 1, 2, 3, 0], dtype=np.int32),
        post=np.array([1, 2, 3, 0, 3], dtype=np.int32),
        weight=np.array([10, 20, 30, 40, 50], dtype=np.int32),
        delay=np.array([1, 2, 3, 4, 5], dtype=np.int32)
    )
    
    mask = np.array([False, True, False, True]) # kill cells 1 and 3
    t.kill(mask)
    assert t.alive.tolist() == [True, False, True, False]
    
    t.compact()
    assert len(t.alive) == 2
    assert t.alive.tolist() == [True, True]
    assert t.lineage_id.tolist() == [0, 2] # Lineage IDs should be preserved
    
    # After killing 1 and 3, remaining are 0 and 2.
    # Synapse (0, 1) -> drops
    # Synapse (1, 2) -> drops
    # Synapse (2, 3) -> drops
    # Synapse (3, 0) -> drops
    # Synapse (0, 3) -> drops
    # If we had a synapse between 0 and 2, it should stay. Let's add one before testing again.
    
def test_kill_and_compact_with_valid_synapses():
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3), dtype=np.float32))
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
    t.add_cells(5)
    t.connectivity = SparseConnectivity(
        pre=np.array([0, 1, 3, 4, 1], dtype=np.int32),
        post=np.array([1, 2, 4, 0, 4], dtype=np.int32),
        weight=np.array([1, 2, 3, 4, 5], dtype=np.int32),
        delay=np.array([1, 1, 1, 1, 1], dtype=np.int32)
    )
    
    t_sub = t.subset(np.array([1, 3, 4]))
    assert len(t_sub.alive) == 3
    assert t_sub.lineage_id.tolist() == [1, 3, 4]
    
    # Original map:
    # 1 -> 0
    # 3 -> 1
    # 4 -> 2
    # Only synapse 3->4 (1->2) and 1->4 (0->2) should survive.
    assert t_sub.connectivity.pre.tolist() == [1, 0]
    assert t_sub.connectivity.post.tolist() == [2, 2]
    assert t_sub.connectivity.weight.tolist() == [3, 5]

def test_concatenate():
    t1 = Tissue.empty(K=1)
    t1.add_cells(2)
    t1.connectivity = SparseConnectivity(
        pre=np.array([0], dtype=np.int32),
        post=np.array([1], dtype=np.int32),
        weight=np.array([10], dtype=np.int32),
        delay=np.array([1], dtype=np.int32)
    )
    
    t2 = Tissue.empty(K=1)
    t2.add_cells(3)
    # Give t2 different lineage IDs to reflect independence before concat
    t2.lineage_id = np.array([2, 3, 4], dtype=np.int32)
    t2._next_lineage_id = 5
    t2.connectivity = SparseConnectivity(
        pre=np.array([1, 2], dtype=np.int32),
        post=np.array([2, 0], dtype=np.int32),
        weight=np.array([20, 30], dtype=np.int32),
        delay=np.array([2, 3], dtype=np.int32)
    )
    
    t = Tissue.concatenate([t1, t2])
    assert len(t.alive) == 5
    assert t.lineage_id.tolist() == [0, 1, 2, 3, 4]
    
    # t1 indices: 0, 1
    # t2 indices: 0->2, 1->3, 2->4
    # t1 syn: 0->1
    # t2 syn: 1->2 becomes 3->4; 2->0 becomes 4->2
    assert t.connectivity.pre.tolist() == [0, 3, 4]
    assert t.connectivity.post.tolist() == [1, 4, 2]
    assert t.connectivity.weight.tolist() == [10, 20, 30]

def test_network_conversion():
    net = SNNNetwork(
        neurons=[
            NeuronData(id=0, x=0.0, y=0.0, z=0.0, dir_x=0.0, dir_y=1.0, dir_z=0.0, mode=0),
            NeuronData(id=1, x=1.0, y=1.0, z=1.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=1),
            NeuronData(id=2, x=2.0, y=2.0, z=2.0, dir_x=0.0, dir_y=0.0, dir_z=1.0, mode=2)
        ],
        synapses=[
            SynapseData(pre=0, post=1, weight=10, delay=1),
            SynapseData(pre=1, post=2, weight=20, delay=2)
        ]
    )
    
    t = Tissue.from_network(net)
    assert len(t.alive) == 3
    assert t.positions.tolist() == [[0,0,0], [1,1,1], [2,2,2]]
    assert t.mode.tolist() == [0, 1, 2]
    assert t.connectivity.pre.tolist() == [0, 1]
    
    net2 = t.to_network()
    assert net2.num_neurons == 3
    assert net2.num_synapses == 2
    assert net2.neurons[1].mode == 1
    assert net2.synapses[0].weight == 10
    
def test_determinism_and_memory():
    # Determinism: same seed, same inputs -> same output (in this case, just adding cells)
    np.random.seed(42)
    pos1 = np.random.rand(10, 3).astype(np.float32)
    t1 = Tissue.empty()
    t1.add_cells(10, positions=pos1)
    
    np.random.seed(42)
    pos2 = np.random.rand(10, 3).astype(np.float32)
    t2 = Tissue.empty()
    t2.add_cells(10, positions=pos2)
    
    assert np.array_equal(t1.positions, t2.positions)
    
    # Memory bytes
    # For N=10, each float32 is 4 bytes. 
    # positions: 10 * 3 * 4 = 120 bytes
    mem = t1.memory_bytes()
    assert mem > 0
    assert type(mem) == int
