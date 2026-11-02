import pytest
import numpy as np
import json
from pathlib import Path
from neurogenesis.spiking.network import SNNNetwork, NeuronData, SynapseData

def test_to_csr_large_neurons():
    """Verify to_csr works for N = 70_000 neurons, which is greater than the uint16 limit of 65,535."""
    N = 70_000
    net = SNNNetwork(
        version="1.0.0",
        morphology="test",
        neurons=[NeuronData(id=i, x=0, y=0, z=0, dir_x=0, dir_y=0, dir_z=0, mode=0) for i in range(10)], # Only need a few neurons for this test
        synapse_arrays={
            "pre": np.array([0, 1, 69999], dtype=np.uint32),
            "post": np.array([69999, 10, 0], dtype=np.uint32),
            "weight": np.array([10, -5, 20], dtype=np.int16),
            "delay": np.array([1, 2, 3], dtype=np.uint8),
        }
    )
    # mock num_neurons to 70_000
    net.neurons = [NeuronData(id=i, x=0, y=0, z=0, dir_x=0, dir_y=0, dir_z=0, mode=0) for i in range(N)]

    row_ptr, col_idx, weights, delays = net.to_csr()
    
    assert len(row_ptr) == N + 1
    assert row_ptr.dtype == np.uint32
    assert col_idx.dtype == np.uint32
    
    # Check that indices were correctly computed
    assert row_ptr[0] == 0
    assert row_ptr[1] == 1
    assert row_ptr[2] == 2
    assert row_ptr[69999] == 2
    assert row_ptr[70000] == 3

    assert col_idx[0] == 69999
    assert col_idx[1] == 10
    assert col_idx[2] == 0

def test_save_json_refuses_large_network(tmp_path: Path):
    net = SNNNetwork(
        version="1.0.0",
        morphology="test",
        neurons=[NeuronData(id=i, x=0, y=0, z=0, dir_x=0, dir_y=0, dir_z=0, mode=0) for i in range(100_001)],
    )
    with pytest.raises(ValueError, match="Network too large for JSON serialization. Use save_npz.. instead."):
        net.save_json(tmp_path / "test.json")

    net2 = SNNNetwork(
        version="1.0.0",
        morphology="test",
        neurons=[NeuronData(id=i, x=0, y=0, z=0, dir_x=0, dir_y=0, dir_z=0, mode=0) for i in range(10)],
        synapse_arrays={
            "pre": np.zeros(1_000_001, dtype=np.uint32),
            "post": np.zeros(1_000_001, dtype=np.uint32),
            "weight": np.zeros(1_000_001, dtype=np.int16),
            "delay": np.zeros(1_000_001, dtype=np.uint8),
        }
    )
    with pytest.raises(ValueError, match="Network too large for JSON serialization. Use save_npz.. instead."):
        net2.save_json(tmp_path / "test.json")

def test_npz_roundtrip(tmp_path: Path):
    net = SNNNetwork(
        version="1.0.0",
        morphology="test",
        neurons=[NeuronData(id=i, x=0, y=0, z=0, dir_x=0, dir_y=0, dir_z=0, mode=0) for i in range(10)],
        synapse_arrays={
            "pre": np.array([0, 1], dtype=np.uint32),
            "post": np.array([1, 0], dtype=np.uint32),
            "weight": np.array([10, 20], dtype=np.int16),
            "delay": np.array([1, 2], dtype=np.uint8),
        }
    )
    npz_path = tmp_path / "test.npz"
    net.save_npz(npz_path)

    net2 = SNNNetwork.load_npz(npz_path)
    
    assert net2.num_neurons == 10
    assert net2.num_synapses == 2
    assert net2.synapses[0].pre == 0
    assert net2.synapse_arrays["weight"][1] == 20
