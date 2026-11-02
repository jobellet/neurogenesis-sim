import pytest
import numpy as np
from pathlib import Path
import zipfile

from neurogenesis.arbors import ArborStore
from neurogenesis.tissue import Tissue
from neurogenesis.data.skeletons import simplify_arbor_rdp, import_connectome_skeletons, attach_connectome_skeletons
from neurogenesis.stages.arbors import ArborSynapses

def test_simplify_arbor_rdp():
    # Straight line with intermediate points that can be removed
    xyz = [[0,0,0], [1,0,0], [2,0,0], [3,0,0], [4,0,0]]
    radius = [1]*5
    parent = [-1, 0, 1, 2, 3]
    compartment = [1, 2, 2, 2, 2] # node 1 changes to compartment 2
    cell = [0]*5
    
    store = ArborStore.ordered(xyz, radius, parent, compartment, cell)
    
    # tolerance 0 -> lossless
    s0 = simplify_arbor_rdp(store, 0.0)
    assert s0.n_nodes == 5
    
    # tolerance > 0 -> keeps roots, branches, terminals, compartment boundaries
    # root: 0
    # compartment boundary: 1
    # branch: none
    # terminal: 4
    # removable: 2, 3
    s1 = simplify_arbor_rdp(store, 0.1)
    assert s1.n_nodes == 3
    assert list(s1.xyz[:, 0]) == [0, 1, 4]
    assert list(s1.parent) == [-1, 0, 1]

    # V-shape that shouldn't be removed with small tolerance
    xyz = [[0,0,0], [1,1,0], [2,0,0]]
    radius = [1]*3
    parent = [-1, 0, 1]
    compartment = [1, 1, 1]
    cell = [0]*3
    store2 = ArborStore.ordered(xyz, radius, parent, compartment, cell)
    s2 = simplify_arbor_rdp(store2, 0.1)
    assert s2.n_nodes == 3
    
    # Large tolerance -> removes the bend
    s3 = simplify_arbor_rdp(store2, 10.0)
    assert s3.n_nodes == 2
    assert list(s3.xyz[:, 0]) == [0, 2]

def test_import_connectome_skeletons_directory(tmp_path):
    swc1 = "1 1 0 0 0 1 -1\n2 2 10 10 10 1 1\n"
    swc2 = "1 1 5 5 5 2 -1\n"
    
    (tmp_path / "101.swc").write_text(swc1)
    (tmp_path / "102.swc").write_text(swc2)
    
    units = {"voxel_size": [0.008, 0.008, 0.04], "origin": [10.0, 20.0, 30.0]}
    
    store = import_connectome_skeletons(
        source=tmp_path,
        source_ids=[101, 102],
        units=units,
        rdp_tolerance=0.0
    )
    
    assert store.n_nodes == 3
    assert list(store.cell) == [0, 0, 1]
    
    mean_vs = np.mean([0.008, 0.008, 0.04])
    assert np.allclose(store.radius, [1 * mean_vs, 1 * mean_vs, 2 * mean_vs])
    assert np.allclose(store.xyz[0], [0*0.008+10, 0*0.008+20, 0*0.04+30])

def test_import_connectome_skeletons_zip(tmp_path):
    zip_path = tmp_path / "skels.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("101.swc", "1 1 0 0 0 1 -1\n2 2 10 10 10 1 1\n")
        zf.writestr("102.swc", "1 1 5 5 5 2 -1\n")
        
    store = import_connectome_skeletons(
        source=zip_path,
        source_ids=[101, 102]
    )
    assert store.n_nodes == 3
    
def test_import_connectome_budget(tmp_path):
    # Check max_nodes_per_cell is applied
    swc1 = "\n".join(f"{i+1} 1 {i} 0 0 1 {i if i>0 else -1}" for i in range(10)) + "\n"
    (tmp_path / "101.swc").write_text(swc1)
    
    store = import_connectome_skeletons(
        source=tmp_path,
        source_ids=[101],
        max_nodes_per_cell=3
    )
    # Downsampling cuts it down
    assert store.n_nodes <= 3

def test_attach_connectome_skeletons_and_synapses(tmp_path):
    # Neuron 1: pre (axon)
    swc1 = "1 2 0 0 0 1 -1\n2 2 1 0 0 1 1\n" # Axon
    # Neuron 2: post (dendrite)
    swc2 = "1 3 0 0 0 1 -1\n2 3 1.1 0 0 1 1\n" # Dendrite nearby
    
    zip_path = tmp_path / "skels.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("101.swc", swc1)
        zf.writestr("102.swc", swc2)
        
    tissue = Tissue.empty()
    tissue.add_cells(2)
    tissue.sign = np.array([1, 1], dtype=np.int8)
    tissue.alive = np.array([True, True], dtype=bool)
    
    info = {"source_ids": [101, 102]}
    tissue = attach_connectome_skeletons(tissue, info, zip_path)
    
    assert tissue.morphology.n_nodes == 4
    
    stage = ArborSynapses()
    params = {
        "contact_distance": 0.5,
        "pre_compartments": ["axon"],
        "post_compartments": ["dendrite"]
    }
    tissue = stage.run(tissue, params, {}, {}, np.random.default_rng(0))
    
    assert len(tissue.connectivity.pre) > 0
