"""Shared fixtures for E2E Interoperability & System Tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict

import pytest

from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData


def _make_neuron(i: int, **kw) -> NeuronData:
    defaults = dict(
        id=i,
        x=float(i * 10),
        y=0.0,
        z=0.0,
        dir_x=1.0,
        dir_y=0.0,
        dir_z=0.0,
        mode=0,
        shift_v=4,
        shift_s=2,
        threshold=1024,
        refractory=2,
        base_weight=100,
        burst_period=0,
        burst_duty=0,
        role=0,
        compartment=0,
        poisson_hz=0.0,
        conn_radius=1.0,
        conn_prob=1.0,
    )
    defaults.update(kw)
    return NeuronData(**defaults)


@pytest.fixture
def single_neuron_net() -> SNNNetwork:
    """A minimal network with a single LIF neuron and no synapses."""
    return SNNNetwork(
        version="1.0.0",
        morphology="single_neuron",
        neurons=[_make_neuron(0, shift_v=4, shift_s=2, threshold=1024)],
        synapses=[],
    )


@pytest.fixture
def two_neuron_feedforward_net() -> SNNNetwork:
    """A 2-neuron feedforward circuit (0 -> 1) with positive weight and delay."""
    n0 = _make_neuron(0, shift_v=4, shift_s=2, threshold=1024)
    n1 = _make_neuron(1, shift_v=5, shift_s=3, threshold=1024)
    syn = SynapseData(pre=0, post=1, weight=250, delay=3)
    return SNNNetwork(
        version="1.0.0",
        morphology="feedforward_pair",
        neurons=[n0, n1],
        synapses=[syn],
    )


@pytest.fixture
def recurrent_net() -> SNNNetwork:
    """A 2-neuron recurrent circuit with reciprocal and self synapses."""
    n0 = _make_neuron(0, shift_v=4, shift_s=2, threshold=1024)
    n1 = _make_neuron(1, shift_v=4, shift_s=2, threshold=1024)
    synapses = [
        SynapseData(pre=0, post=1, weight=180, delay=1),
        SynapseData(pre=1, post=0, weight=-150, delay=2),  # inhibitory
        SynapseData(pre=0, post=0, weight=80, delay=1),   # self-loop
    ]
    return SNNNetwork(
        version="1.0.0",
        morphology="recurrent_pair",
        neurons=[n0, n1],
        synapses=synapses,
    )


@pytest.fixture
def mixed_drivers_net() -> SNNNetwork:
    """A 3-neuron network mixing standard LIF, Poisson driver, and burster."""
    n0 = _make_neuron(0, mode=0, shift_v=4, shift_s=2, threshold=1024)
    n1 = _make_neuron(1, mode=1, poisson_hz=50.0, shift_v=4, shift_s=2, threshold=1024)
    n2 = _make_neuron(2, mode=2, burst_period=25, burst_duty=5, shift_v=4, shift_s=2, threshold=1024)
    synapses = [
        SynapseData(pre=1, post=0, weight=300, delay=2),
        SynapseData(pre=2, post=0, weight=200, delay=1),
        SynapseData(pre=0, post=0, weight=50, delay=1),
    ]
    return SNNNetwork(
        version="1.0.0",
        morphology="mixed_drivers",
        neurons=[n0, n1, n2],
        synapses=synapses,
    )


@pytest.fixture(scope="module")
def cortical_column_net() -> SNNNetwork:
    """Standard 300-neuron cortical column from MorphogeneticEngine."""
    return MorphogeneticEngine.generate_cortical_column(300, seed=42, refractory=2)


@pytest.fixture(scope="module")
def layered_net() -> SNNNetwork:
    """Standard layered network from MorphogeneticEngine."""
    return MorphogeneticEngine.generate_layered_network(60, seed=42)


@pytest.fixture
def toy_connectome_dir(tmp_path: Path) -> Path:
    """Creates a temporary dataset directory with toy connectome CSV files and manifest."""
    neurons_csv = (
        "root_id,pos_x,pos_y,pos_z,type,class,region,side,nt\n"
        "101,0,0,0,A1,local,R1,left,glutamate\n"
        "102,100,0,0,A2,local,R1,right,glutamate\n"
        "103,0,100,0,B1,projection,R2,left,gaba\n"
        "104,0,0,100,B2,projection,R2,right,acetylcholine\n"
        "105,5000,0,0,C,other,R3,left,gaba\n"
    )
    edges_csv = (
        "pre_root_id,post_root_id,neuropil,syn_count\n"
        "101,102,N1,4\n"
        "101,102,N2,3\n"
        "102,103,N1,2\n"
        "103,101,N1,10\n"
        "104,101,N1,1\n"
        "105,101,N1,50\n"
    )
    (tmp_path / "neurons.csv").write_text(neurons_csv, encoding="utf-8")
    (tmp_path / "edges.csv").write_text(edges_csv, encoding="utf-8")

    manifest = {
        "id": "toy_e2e",
        "title": "Toy E2E Connectome",
        "license": "CC-BY-4.0",
        "citation": "E2E Test Writer 2026",
        "url": "http://127.0.0.1:1/",
        "files": [
            {"name": "neurons.csv", "sha256": hashlib.sha256(neurons_csv.encode()).hexdigest(), "size": len(neurons_csv)},
            {"name": "edges.csv", "sha256": hashlib.sha256(edges_csv.encode()).hexdigest(), "size": len(edges_csv)},
        ],
        "tables": {
            "neurons": {
                "file": "neurons.csv",
                "format": "csv",
                "columns": {
                    "id": "root_id",
                    "x": "pos_x",
                    "y": "pos_y",
                    "z": "pos_z",
                    "cell_type": "type",
                    "class": "class",
                    "region": "region",
                    "side": "side",
                    "transmitter": "nt",
                },
            },
            "edges": {
                "file": "edges.csv",
                "format": "csv",
                "columns": {
                    "pre": "pre_root_id",
                    "post": "post_root_id",
                    "count": "syn_count",
                },
            },
        },
        "units": {
            "voxel_size": [0.1, 0.1, 0.1],
            "origin": [1.0, 0.0, 0.0],
            "mirror": [],
            "unit": "um",
        },
    }
    (tmp_path / "toy_e2e.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return tmp_path
