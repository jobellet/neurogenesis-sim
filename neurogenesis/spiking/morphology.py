"""Statistical generation rules and morphogenetic 3D growth cone wiring engine.

Implements biologically-grounded laminar cortical columns, feedforward/recurrent layered
circuits, microcircuits, and anisotropic probabilistic connectivity laws.
"""

from __future__ import annotations

import math
from typing import List, Optional
import numpy as np

from .network import NeuronData, SNNNetwork, SynapseData


class MorphogeneticEngine:
    """Generates 3D neuron populations and wires synapses using anisotropic morphogenetic laws."""

    @staticmethod
    def apply_regime(network: SNNNetwork, weight_scale: float = 1.0, inh_scale: float = 1.0, refractory: int = 0) -> SNNNetwork:
        """Scale base weights (inhibitory ones by inh_scale in addition) and set the refractory period of every neuron.
        Defaults leave the network unchanged. Call before wire_network (weights are drawn from base weights)."""
        for n in network.neurons:
            w = n.base_weight * weight_scale * (inh_scale if n.base_weight < 0 else 1.0)
            n.base_weight = int(np.clip(round(w), -512, 512))
            n.refractory = int(refractory)
        return network

    @staticmethod
    def wire_network(
        network: SNNNetwork,
        conduction_velocity: float = 4.0,
        seed: Optional[int] = None,
    ) -> SNNNetwork:
        """Connect neurons using the morphogenetic directional probability law:

        P(i -> j) = P_0 * exp(-d_ij^2 / (2 * sigma_i^2)) * max(0.1, (u_i . r_ij) / d_ij)
        """
        rng = np.random.default_rng(seed)
        neurons = network.neurons
        n = len(neurons)
        synapses: List[SynapseData] = []

        coords = np.array([[neu.x, neu.y, neu.z] for neu in neurons], dtype=np.float32)
        axons = np.array([[neu.dir_x, neu.dir_y, neu.dir_z] for neu in neurons], dtype=np.float32)

        for i in range(n):
            xi = coords[i]
            ui = axons[i]
            p0 = neurons[i].conn_prob
            sigma = max(1.0, neurons[i].conn_radius)
            two_sigma_sq = 2.0 * sigma * sigma
            base_w = neurons[i].base_weight

            # Displacement vectors to all other neurons
            diff = coords - xi  # [N, 3]
            dist_sq = np.sum(diff * diff, axis=1)  # [N]
            dist = np.sqrt(dist_sq)  # [N]

            # Avoid self-loops and numerical instability near 0
            valid_mask = (dist > 0.1)
            valid_mask[i] = False

            valid_idx = np.where(valid_mask)[0]
            if len(valid_idx) == 0:
                continue

            r_norm = diff[valid_idx] / dist[valid_idx, np.newaxis]
            dot = np.sum(r_norm * ui, axis=1)
            directional_factor = np.maximum(0.1, dot)

            probs = p0 * np.exp(-dist_sq[valid_idx] / two_sigma_sq) * directional_factor
            rand_draws = rng.random(len(valid_idx))

            connected_indices = valid_idx[rand_draws < probs]

            for j in connected_indices:
                d = dist[j]
                delay = int(np.clip(np.round(d / conduction_velocity), 1, 31))
                jitter = 0.9 + rng.random() * 0.2
                w = int(np.clip(round(base_w * jitter), -512, 512))

                synapses.append(SynapseData(pre=i, post=int(j), weight=w, delay=delay))

        network.synapses = synapses
        return network

    @classmethod
    def generate_cortical_column(
        cls,
        num_neurons: int = 1000,
        radius: float = 30.0,
        height: float = 150.0,
        exc_ratio: float = 0.80,
        pace_ratio: float = 0.05,
        conduction_velocity: float = 4.0,
        seed: Optional[int] = 42,
        weight_scale: float = 1.0,
        inh_scale: float = 1.0,
        refractory: int = 0,
    ) -> SNNNetwork:
        """Generate a 3D cylindrical cortical column structured into L1–L6 laminar layers."""
        rng = np.random.default_rng(seed)
        neurons: List[NeuronData] = []

        num_pace = max(2, int(round(num_neurons * pace_ratio)))
        num_poisson = num_pace // 2
        num_burster = num_pace - num_poisson

        num_inh = int(round(num_neurons * (1.0 - exc_ratio)))

        # Cylindrical somatic placement
        for i in range(num_neurons):
            r = math.sqrt(rng.random()) * radius
            theta = rng.random() * math.pi * 2
            x = r * math.cos(theta)
            z = r * math.sin(theta)
            y = (rng.random() - 0.5) * height

            mode = 0  # LIF
            base_w = 180
            shift_v = 5
            shift_s = 4
            conn_r = 28.0
            conn_p = 0.38
            burst_t = 200
            burst_d = 24
            p_hz = 25.0

            dir_x, dir_y, dir_z = 0.0, 1.0, 0.0

            if i < num_poisson:
                # Deep layer thalamic Poisson input drivers
                mode = 1
                base_w = 220
                y = -height * 0.45 + (rng.random() * height * 0.2)
                p_hz = 18.0 + rng.random() * 15.0
                conn_r = 35.0
                conn_p = 0.55
                dir_y = 0.98
            elif i < num_poisson + num_burster:
                # Deep layer autonomous pacemaker bursters (Layer 5/6)
                mode = 2
                base_w = 250
                y = -height * 0.48 + (rng.random() * height * 0.25)
                burst_t = int(160 + rng.random() * 120)
                burst_d = int(24 + rng.random() * 12)
                conn_r = 35.0
                conn_p = 0.50
                dir_y = 0.95
            elif i < num_poisson + num_burster + num_inh:
                # Inhibitory interneurons (local, isotropic)
                mode = 0
                base_w = -320
                shift_v = 4
                shift_s = 3
                conn_r = 16.0
                conn_p = 0.55
                ang = rng.random() * math.pi * 2
                dir_x = math.cos(ang)
                dir_y = (rng.random() - 0.5) * 0.8
                dir_z = math.sin(ang)
            else:
                # Excitatory Pyramidal cells
                mode = 0
                base_w = int(160 + rng.random() * 60)
                shift_v = 5
                shift_s = 4
                conn_r = 26.0
                conn_p = 0.38
                if y > 15:
                    # Superficial L2/3 project laterally and descending
                    dir_y = -0.5 + (rng.random() - 0.5) * 0.4
                    dir_x = (rng.random() - 0.5) * 1.5
                    dir_z = (rng.random() - 0.5) * 1.5
                else:
                    # Deep L5/6 project ascending towards surface
                    dir_y = 0.8 + rng.random() * 0.2
                    dir_x = (rng.random() - 0.5) * 0.6
                    dir_z = (rng.random() - 0.5) * 0.6

            norm = math.sqrt(dir_x * dir_x + dir_y * dir_y + dir_z * dir_z) or 1.0
            dir_x /= norm
            dir_y /= norm
            dir_z /= norm

            neurons.append(
                NeuronData(
                    id=i,
                    x=float(x),
                    y=float(y),
                    z=float(z),
                    dir_x=float(dir_x),
                    dir_y=float(dir_y),
                    dir_z=float(dir_z),
                    mode=mode,
                    shift_v=shift_v,
                    shift_s=shift_s,
                    base_weight=base_w,
                    conn_radius=conn_r,
                    conn_prob=conn_p,
                    burst_period=burst_t,
                    burst_duty=burst_d,
                    poisson_hz=p_hz,
                )
            )

        net = SNNNetwork(
            version="1.0.0",
            morphology="Cortical Column (L1-L6)",
            neurons=neurons,
        )
        cls.apply_regime(net, weight_scale, inh_scale, refractory)
        return cls.wire_network(net, conduction_velocity=conduction_velocity, seed=seed)

    @classmethod
    def generate_layered_network(
        cls,
        num_neurons: int = 600,
        num_layers: int = 4,
        layer_spacing: float = 38.0,
        layer_span: float = 75.0,
        conduction_velocity: float = 4.0,
        seed: Optional[int] = 42,
    ) -> SNNNetwork:
        """Generate layered feedforward + recurrent sensory-to-motor network sheets."""
        rng = np.random.default_rng(seed)
        neurons: List[NeuronData] = []
        neurons_per_layer = num_neurons // num_layers

        for l in range(num_layers):
            y_level = (l - (num_layers - 1) / 2.0) * layer_spacing
            for k in range(neurons_per_layer):
                nid = l * neurons_per_layer + k
                x = (rng.random() - 0.5) * layer_span * 2
                z = (rng.random() - 0.5) * layer_span * 2

                is_inh = (rng.random() < 0.20)
                is_driver = (l == 0 and rng.random() < 0.15)

                mode = 1 if is_driver else 0
                base_w = 220 if is_driver else (-300 if is_inh else 180)
                dir_y = 0.9 if l < num_layers - 1 else -0.5

                neurons.append(
                    NeuronData(
                        id=nid,
                        x=float(x),
                        y=float(y_level),
                        z=float(z),
                        dir_x=float((rng.random() - 0.5) * 0.4),
                        dir_y=float(dir_y),
                        dir_z=float((rng.random() - 0.5) * 0.4),
                        mode=mode,
                        base_weight=base_w,
                        conn_radius=32.0,
                        conn_prob=0.45,
                        poisson_hz=28.0 if is_driver else 0.0,
                    )
                )

        net = SNNNetwork(
            version="1.0.0",
            morphology="Layered Sheets",
            neurons=neurons,
        )
        return cls.wire_network(net, conduction_velocity=conduction_velocity, seed=seed)

    @classmethod
    def generate_microcircuit(
        cls,
        num_neurons: int = 100,
        span: float = 30.0,
        conduction_velocity: float = 4.0,
        seed: Optional[int] = 42,
    ) -> SNNNetwork:
        """Generate a dense, high-frequency oscillatory microcircuit."""
        rng = np.random.default_rng(seed)
        neurons: List[NeuronData] = []

        for i in range(num_neurons):
            x = (rng.random() - 0.5) * span * 2
            y = (rng.random() - 0.5) * span * 2
            z = (rng.random() - 0.5) * span * 2

            is_driver = (i < 4)
            is_inh = (not is_driver and i % 5 == 0)

            mode = 2 if is_driver else 0
            base_w = 260 if is_driver else (-340 if is_inh else 190)

            neurons.append(
                NeuronData(
                    id=i,
                    x=float(x),
                    y=float(y),
                    z=float(z),
                    dir_x=float((rng.random() - 0.5)),
                    dir_y=float((rng.random() - 0.5)),
                    dir_z=float((rng.random() - 0.5)),
                    mode=mode,
                    base_weight=base_w,
                    conn_radius=span * 0.8,
                    conn_prob=0.55,
                    burst_period=140,
                    burst_duty=20,
                )
            )

        net = SNNNetwork(
            version="1.0.0",
            morphology="Microcircuit (100)",
            neurons=neurons,
        )
        return cls.wire_network(net, conduction_velocity=conduction_velocity, seed=seed)
