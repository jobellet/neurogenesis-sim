"""Writes NGB1 files with neurogenesis.bridge.ngb, plus expected.json with every value they hold, for the C# NGB1
reader tests (NgbTests.cs). Usage: python make_ngb_fixtures.py <output dir>"""
import json
import sys
from pathlib import Path

import numpy as np

from neurogenesis.bridge.ngb import NEURON_F64, NEURON_I32, SYNAPSE_I32, read_extensions, write_network
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData


def extreme():
    """Two neurons and two synapses with int32 / float64 edge values (indices are int32, never 16-bit)."""
    a = NeuronData(id=0, x=-1e300, y=5e-324, z=0.1, dir_x=0.0, dir_y=-0.0, dir_z=1.0, mode=2, shift_v=-2147483648,
                   shift_s=2147483647, base_weight=-180, poisson_hz=123.456789, compartment=-1, threshold=70000)
    b = NeuronData(id=1, x=1e9 + 0.5, y=-7.25, z=3.0, dir_x=1.0, dir_y=0.0, dir_z=0.0, mode=0, role=2, compartment=40000)
    return SNNNetwork(morphology="extreme", neurons=[a, b],
                      synapses=[SynapseData(0, 1, -2047, 31), SynapseData(1, 0, 2047, 200000)])


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    layered = MorphogeneticEngine.generate_layered_network(num_neurons=60, seed=5)
    n, e = len(layered.neurons), len(layered.synapses)
    ext = {
        "vec": ("neuron", np.arange(3 * n, dtype="<f4").reshape(n, 3) / 7),
        "receptor": ("synapse", (np.arange(e) % 3).astype("<u1")),
        "level": ("neuron", np.linspace(-1, 1, n).astype("<f8")),
        "count": ("neuron", (np.arange(n) - 30).astype("<i2")),
    }
    cases = {
        "column": (MorphogeneticEngine.generate_cortical_column(num_neurons=200, seed=3), None),
        "empty": (SNNNetwork(morphology="empty"), None),
        "extreme": (extreme(), None),
        "extensions": (layered, ext),
    }
    expected = {}
    for name, (net, extensions) in cases.items():
        path = out / f"{name}.ngb"
        write_network(net, path, extensions)
        ns, ss = net.neurons, net.synapses
        expected[name] = dict(
            neurons=len(ns), synapses=len(ss),
            positions=[c for nd in ns for c in (nd.x, nd.y, nd.z)],
            directions=[c for nd in ns for c in (nd.dir_x, nd.dir_y, nd.dir_z)],
            int32={a: [getattr(nd, a) for nd in ns] for a in NEURON_I32},
            float64={a: [getattr(nd, a) for nd in ns] for a in NEURON_F64},
            synapse={a: [getattr(s, a) for s in ss] for a in SYNAPSE_I32},
            extensions={k: dict(axis=axis, components=1 if arr.ndim == 1 else arr.shape[1],
                                values=np.asarray(arr, "f8").ravel().tolist())
                        for k, (axis, arr) in read_extensions(path).items()},
        )
    (out / "expected.json").write_text(json.dumps(expected))


if __name__ == "__main__":
    main(sys.argv[1])
