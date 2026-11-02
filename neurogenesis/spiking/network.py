"""Data structures and serialization for 3D Spiking Neural Networks (SNN).

Handles Structure-of-Arrays (SoA), Compressed Sparse Row (CSR) graph conversions,
JSON serialization/deserialization compatible with the WebGL2 morphogenetic visualizer,
and network topology graph analytics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


class _SynapseListView(Sequence['SynapseData']):
    def __init__(self, arrays: Dict[str, np.ndarray]):
        self.arrays = arrays
        self.length = len(arrays['pre'])

    def __getitem__(self, idx: int) -> 'SynapseData':
        if isinstance(idx, slice):
            raise NotImplementedError("Slice indexing not supported")
        if idx < 0 or idx >= self.length:
            raise IndexError("Synapse index out of range")
        return SynapseData(
            pre=int(self.arrays['pre'][idx]),
            post=int(self.arrays['post'][idx]),
            weight=int(self.arrays['weight'][idx]),
            delay=int(self.arrays['delay'][idx]),
        )

    def __len__(self) -> int:
        return self.length


@dataclass
class NeuronData:
    id: int
    x: float
    y: float
    z: float
    dir_x: float
    dir_y: float
    dir_z: float
    mode: int  # 0: LIF, 1: Poisson, 2: Burster
    shift_v: int = 5
    shift_s: int = 4
    base_weight: int = 180
    conn_radius: float = 28.0
    conn_prob: float = 0.38
    burst_period: int = 200
    burst_duty: int = 24
    poisson_hz: float = 25.0
    refractory: int = 0          # absolute refractory period in ticks (0: none, as in the first version)
    role: int = 0                # 0 internal, 1 input, 2 output (ignored by the kernel)
    compartment: int = -1        # compartment index of compartmental brains (devbrain.COMPARTMENT_ID; -1 none)
    threshold: int = 1024        # firing threshold (per-neuron intrinsic excitability; 1024 = first version)


@dataclass
class SynapseData:
    pre: int
    post: int
    weight: int
    delay: int


@dataclass
class SNNNetwork:
    version: str = "1.0.0"
    morphology: str = "Custom"
    neurons: List[NeuronData] = field(default_factory=list)
    synapses: Union[List[SynapseData], _SynapseListView] = field(default_factory=list)
    synapse_arrays: Optional[Dict[str, np.ndarray]] = None

    def __post_init__(self):
        if self.synapse_arrays is not None:
            self.synapses = _SynapseListView(self.synapse_arrays)
        elif isinstance(self.synapses, _SynapseListView):
            self.synapse_arrays = self.synapses.arrays

    @classmethod
    def from_arrays(cls, version: str, morphology: str, neurons: List[NeuronData], synapse_arrays: Dict[str, np.ndarray]) -> SNNNetwork:
        return cls(version=version, morphology=morphology, neurons=neurons, synapse_arrays=synapse_arrays)

    @property
    def num_neurons(self) -> int:
        return len(self.neurons)

    @property
    def num_synapses(self) -> int:
        if self.synapse_arrays is not None:
            return len(self.synapse_arrays['pre'])
        return len(self.synapses)

    def to_dict(self) -> Dict[str, Any]:
        """Convert network to a JSON-serializable dictionary matching the Web format."""
        return {
            "version": self.version,
            "morphology": self.morphology,
            "numNeurons": self.num_neurons,
            "numSynapses": self.num_synapses,
            "neurons": [
                {
                    "id": n.id,
                    "x": round(float(n.x), 2),
                    "y": round(float(n.y), 2),
                    "z": round(float(n.z), 2),
                    "dirX": round(float(n.dir_x), 3),
                    "dirY": round(float(n.dir_y), 3),
                    "dirZ": round(float(n.dir_z), 3),
                    "mode": int(n.mode),
                    "shiftV": int(n.shift_v),
                    "shiftS": int(n.shift_s),
                    "baseWeight": int(n.base_weight),
                    "connRadius": round(float(n.conn_radius), 1),
                    "connProb": round(float(n.conn_prob), 2),
                    "burstPeriod": int(n.burst_period),
                    "burstDuty": int(n.burst_duty),
                    "poissonHz": round(float(n.poisson_hz), 6),
                    "refractory": int(n.refractory),
                    "role": int(n.role),
                    "compartment": int(n.compartment),
                    "threshold": int(n.threshold),
                }
                for n in self.neurons
            ],
            "synapses": [
                {
                    "pre": int(s.pre),
                    "post": int(s.post),
                    "weight": int(s.weight),
                    "delay": int(s.delay),
                }
                for s in self.synapses
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SNNNetwork:
        """Construct SNNNetwork from parsed JSON data."""
        neurons = [
            NeuronData(
                id=n.get("id", i),
                x=float(n["x"]),
                y=float(n["y"]),
                z=float(n["z"]),
                dir_x=float(n.get("dirX", 0.0)),
                dir_y=float(n.get("dirY", 1.0)),
                dir_z=float(n.get("dirZ", 0.0)),
                mode=int(n.get("mode", 0)),
                shift_v=int(n.get("shiftV", 5)),
                shift_s=int(n.get("shiftS", 4)),
                base_weight=int(n.get("baseWeight", 180)),
                conn_radius=float(n.get("connRadius", 28.0)),
                conn_prob=float(n.get("connProb", 0.38)),
                burst_period=int(n.get("burstPeriod", 200)),
                burst_duty=int(n.get("burstDuty", 24)),
                poisson_hz=float(n.get("poissonHz", 25.0)),
                refractory=int(n.get("refractory", 0)),
                role=int(n.get("role", 0)),
                compartment=int(n.get("compartment", -1)),
                threshold=int(n.get("threshold", 1024)),
            )
            for i, n in enumerate(data.get("neurons", []))
        ]

        synapses = [
            SynapseData(
                pre=int(s["pre"]),
                post=int(s["post"]),
                weight=int(s["weight"]),
                delay=int(s["delay"]),
            )
            for s in data.get("synapses", [])
        ]

        return cls(
            version=data.get("version", "1.0.0"),
            morphology=data.get("morphology", "Custom"),
            neurons=neurons,
            synapses=synapses,
        )

    def save_json(self, path: str | Path) -> None:
        """Save the network to a JSON file."""
        if self.num_neurons > 100_000 or self.num_synapses > 1_000_000:
            raise ValueError("Network too large for JSON serialization. Use save_npz() instead.")
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path: str | Path) -> SNNNetwork:
        """Load a network from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def save_npz(self, path: str | Path) -> None:
        """Save the network to an NPZ file."""
        if self.synapse_arrays is None:
            # We need to construct synapse arrays if they aren't available
            if not self.synapses:
                pre = np.array([], dtype=np.uint32)
                post = np.array([], dtype=np.uint32)
                weight = np.array([], dtype=np.int16)
                delay = np.array([], dtype=np.uint8)
            else:
                pre = np.array([s.pre for s in self.synapses], dtype=np.uint32)
                post = np.array([s.post for s in self.synapses], dtype=np.uint32)
                weight = np.array([s.weight for s in self.synapses], dtype=np.int16)
                delay = np.array([s.delay for s in self.synapses], dtype=np.uint8)
            synapse_arrays = {"pre": pre, "post": post, "weight": weight, "delay": delay}
        else:
            synapse_arrays = self.synapse_arrays

        # Convert neurons to dict, excluding synapses
        d = self.to_dict()
        del d["synapses"]
        
        np.savez_compressed(
            path,
            metadata=json.dumps(d),
            pre=synapse_arrays["pre"],
            post=synapse_arrays["post"],
            weight=synapse_arrays["weight"],
            delay=synapse_arrays["delay"]
        )

    @classmethod
    def load_npz(cls, path: str | Path) -> SNNNetwork:
        """Load a network from an NPZ file."""
        with np.load(path) as data:
            metadata = json.loads(str(data["metadata"]))
            pre = data["pre"]
            post = data["post"]
            weight = data["weight"]
            delay = data["delay"]
            
        synapse_arrays = {"pre": pre, "post": post, "weight": weight, "delay": delay}
        
        neurons = [
            NeuronData(
                id=n.get("id", i),
                x=float(n["x"]),
                y=float(n["y"]),
                z=float(n["z"]),
                dir_x=float(n.get("dirX", 0.0)),
                dir_y=float(n.get("dirY", 1.0)),
                dir_z=float(n.get("dirZ", 0.0)),
                mode=int(n.get("mode", 0)),
                shift_v=int(n.get("shiftV", 5)),
                shift_s=int(n.get("shiftS", 4)),
                base_weight=int(n.get("baseWeight", 180)),
                conn_radius=float(n.get("connRadius", 28.0)),
                conn_prob=float(n.get("connProb", 0.38)),
                burst_period=int(n.get("burstPeriod", 200)),
                burst_duty=int(n.get("burstDuty", 24)),
                poisson_hz=float(n.get("poissonHz", 25.0)),
                refractory=int(n.get("refractory", 0)),
                role=int(n.get("role", 0)),
                compartment=int(n.get("compartment", -1)),
                threshold=int(n.get("threshold", 1024)),
            )
            for i, n in enumerate(metadata.get("neurons", []))
        ]

        return cls.from_arrays(
            version=metadata.get("version", "1.0.0"),
            morphology=metadata.get("morphology", "Custom"),
            neurons=neurons,
            synapse_arrays=synapse_arrays
        )

    def to_csr(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Convert synapses to Compressed Sparse Row (CSR) format."""
        n = self.num_neurons
        if self.synapse_arrays is not None:
            pre = self.synapse_arrays["pre"]
            post = self.synapse_arrays["post"]
            weight = self.synapse_arrays["weight"]
            delay = self.synapse_arrays["delay"]
        else:
            pre = np.array([s.pre for s in self.synapses], dtype=np.uint32)
            post = np.array([s.post for s in self.synapses], dtype=np.uint32)
            weight = np.array([s.weight for s in self.synapses], dtype=np.int16)
            delay = np.array([s.delay for s in self.synapses], dtype=np.uint8)

        # Filter valid synapses where pre and post are within bounds
        mask = (pre < n) & (post < n)
        pre = pre[mask]
        post = post[mask]
        weight = weight[mask]
        delay = delay[mask]

        # Vectorized sorting by pre
        # kind="stable" isn't strictly necessary for CSR itself, but keeps order of synapses from the same pre
        sort_idx = np.argsort(pre, kind="stable")
        
        sorted_pre = pre[sort_idx]
        sorted_post = post[sort_idx]
        sorted_weight = weight[sort_idx]
        sorted_delay = delay[sort_idx]

        # bincount calculates how many synapses each pre neuron has
        counts = np.bincount(sorted_pre, minlength=n)
        
        row_ptr = np.zeros(n + 1, dtype=np.uint32)
        row_ptr[1:] = np.cumsum(counts)
        
        col_idx = sorted_post.astype(np.uint32)
        weights = sorted_weight
        delays = sorted_delay

        return row_ptr, col_idx, weights, delays

    def compute_statistics(self) -> Dict[str, Any]:
        """Compute comprehensive graph topology and biophysical statistics."""
        n = self.num_neurons
        m = self.num_synapses

        if n == 0:
            return {"num_neurons": 0, "num_synapses": 0}

        in_deg = np.zeros(n, dtype=int)
        out_deg = np.zeros(n, dtype=int)
        weights = []
        delays = []
        edge_set = set()

        exc_count = 0
        inh_count = 0
        burster_count = 0
        poisson_count = 0

        for neuron in self.neurons:
            if neuron.mode == 1:
                poisson_count += 1
            elif neuron.mode == 2:
                burster_count += 1
            elif neuron.base_weight < 0:
                inh_count += 1
            else:
                exc_count += 1

        if self.synapse_arrays is not None:
            pre = self.synapse_arrays["pre"]
            post = self.synapse_arrays["post"]
            w = self.synapse_arrays["weight"]
            d = self.synapse_arrays["delay"]
            mask = (pre < n) & (post < n)
            pre = pre[mask]
            post = post[mask]
            
            # Using bincount for degrees
            if len(pre) > 0:
                out_deg = np.bincount(pre, minlength=n)
                in_deg = np.bincount(post, minlength=n)
            weights = w[mask].tolist() if len(w[mask]) > 0 else []
            delays = d[mask].tolist() if len(d[mask]) > 0 else []
            
            # Using np unique for edge set mapping to calculate reciprocity
            if len(pre) > 0:
                # encode edges as integers to find reciprocals efficiently
                max_n = max(n, 1)
                # Ensure using uint64 to avoid overflow if n is large
                edges = pre.astype(np.uint64) * max_n + post.astype(np.uint64)
                recip_edges = post.astype(np.uint64) * max_n + pre.astype(np.uint64)
                # Find reciprocal edges by intersecting edges and recip_edges
                edges_unique = np.unique(edges)
                recip_edges_unique = np.unique(recip_edges)
                intersection = np.intersect1d(edges_unique, recip_edges_unique, assume_unique=True)
                
                # Each reciprocal pair will appear twice in intersection (A->B and B->A), divide by 2
                # Also we need to subtract self loops
                self_loops = np.sum(pre == post)
                reciprocal_count = (len(intersection) - self_loops) // 2
            else:
                reciprocal_count = 0

        else:
            for syn in self.synapses:
                if syn.pre < n and syn.post < n:
                    out_deg[syn.pre] += 1
                    in_deg[syn.post] += 1
                    weights.append(syn.weight)
                    delays.append(syn.delay)
                    edge_set.add((syn.pre, syn.post))

            # Reciprocity
            reciprocal_count = 0
            for pre, post in edge_set:
                if (post, pre) in edge_set and pre < post:
                    reciprocal_count += 1

        density = m / (n * (n - 1)) if n > 1 else 0.0

        return {
            "num_neurons": n,
            "num_synapses": m,
            "morphology": self.morphology,
            "density": round(density, 4),
            "cell_types": {
                "excitatory_lif": exc_count,
                "inhibitory_lif": inh_count,
                "autonomous_burster": burster_count,
                "poisson_driver": poisson_count,
            },
            "in_degree": {
                "mean": round(float(np.mean(in_deg)), 2),
                "std": round(float(np.std(in_deg)), 2),
                "min": int(np.min(in_deg)),
                "max": int(np.max(in_deg)),
            },
            "out_degree": {
                "mean": round(float(np.mean(out_deg)), 2),
                "std": round(float(np.std(out_deg)), 2),
                "min": int(np.min(out_deg)),
                "max": int(np.max(out_deg)),
            },
            "weights": {
                "mean": round(float(np.mean(weights)), 2) if weights else 0.0,
                "min": int(np.min(weights)) if weights else 0,
                "max": int(np.max(weights)) if weights else 0,
            },
            "delays_ms": {
                "mean": round(float(np.mean(delays)), 2) if delays else 0.0,
                "min": int(np.min(delays)) if delays else 0,
                "max": int(np.max(delays)) if delays else 0,
            },
            "reciprocal_pairs": reciprocal_count,
        }
