"""NGB1: the binary network format exchanged between the bridge and the desktop apps (desktop/common/PROTOCOL.md).

Little endian, no padding:
  header      b"NGB1", int32 N (neurons), int32 E (synapses), int32 flags (0)
  neurons     positions (N, 3) float64, directions (N, 3) float64,
              then one int32 column (N,) per NEURON_I32 field, one float64 column (N,) per NEURON_F64 field
  synapses    pre, post, weight, delay: one int32 column (E,) each
Float64 keeps positions and Poisson rates exactly as in Python, so a round trip changes nothing.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

NGB_VERSION = 1
MAGIC = b"NGB1"
NEURON_I32 = ("mode", "shift_v", "shift_s", "base_weight", "burst_period", "burst_duty", "refractory", "role",
              "compartment", "threshold")
NEURON_F64 = ("poisson_hz", "conn_radius", "conn_prob")
SYNAPSE_I32 = ("pre", "post", "weight", "delay")


def nbytes(n_neurons: int, n_synapses: int) -> int:
    """Size of an NGB1 file: 16 + 112 N + 16 E bytes."""
    return 16 + n_neurons * (48 + 4 * len(NEURON_I32) + 8 * len(NEURON_F64)) + n_synapses * 4 * len(SYNAPSE_I32)


def write_network(net, path) -> None:
    """Writes an SNNNetwork as NGB1."""
    ns, ss = net.neurons, net.synapses
    N, E = len(ns), len(ss)
    with open(path, "wb") as f:
        f.write(MAGIC + struct.pack("<iii", N, E, 0))
        f.write(np.asarray([(n.x, n.y, n.z) for n in ns], "<f8").reshape(N, 3).tobytes())
        f.write(np.asarray([(n.dir_x, n.dir_y, n.dir_z) for n in ns], "<f8").reshape(N, 3).tobytes())
        for a in NEURON_I32:
            f.write(np.asarray([getattr(n, a) for n in ns], "<i4").tobytes())
        for a in NEURON_F64:
            f.write(np.asarray([getattr(n, a) for n in ns], "<f8").tobytes())
        for a in SYNAPSE_I32:
            f.write(np.asarray([getattr(s, a) for s in ss], "<i4").tobytes())


def read_network(path):
    """Reads an NGB1 file into an SNNNetwork."""
    from ..spiking.network import NeuronData, SNNNetwork, SynapseData
    b = Path(path).read_bytes()
    if b[:4] != MAGIC:
        raise ValueError(f"{path}: not an NGB1 network file")
    N, E, _ = struct.unpack("<iii", b[4:16])
    if len(b) != nbytes(N, E):
        raise ValueError(f"{path}: {len(b)} bytes, expected {nbytes(N, E)} for {N} neurons and {E} synapses")
    o = 16

    def take(dt, n):
        nonlocal o
        a = np.frombuffer(b, dt, n, o)
        o += a.nbytes
        return a
    pos = take("<f8", 3 * N).reshape(N, 3)
    dirs = take("<f8", 3 * N).reshape(N, 3)
    ints = {a: take("<i4", N) for a in NEURON_I32}
    flts = {a: take("<f8", N) for a in NEURON_F64}
    syn = {a: take("<i4", E) for a in SYNAPSE_I32}
    neurons = [NeuronData(id=i, x=float(pos[i, 0]), y=float(pos[i, 1]), z=float(pos[i, 2]), dir_x=float(dirs[i, 0]),
                          dir_y=float(dirs[i, 1]), dir_z=float(dirs[i, 2]),
                          **{a: int(ints[a][i]) for a in NEURON_I32}, **{a: float(flts[a][i]) for a in NEURON_F64})
               for i in range(N)]
    synapses = [SynapseData(int(p), int(q), int(w), int(d)) for p, q, w, d in zip(*(syn[a] for a in SYNAPSE_I32))]
    return SNNNetwork(morphology="NGB1", neurons=neurons, synapses=synapses)
