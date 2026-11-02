"""Fast integer-only SNN simulation engine in Python.

Matches the Web Worker JavaScript kernel bit-for-bit:
1. Integer bit-shift decay with underflow clamping.
2. Spontaneous Poisson / Autonomous Burster generators.
3. 32-bit temporal shift register (spikeBitfield) bitwise delay engine.
4. Compressed Sparse Row (CSR) synaptic propagation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import matplotlib.pyplot as plt
import numpy as np

from .network import SNNNetwork


class IntegerSNNSimulator:
    """Headless bit-for-bit integer SNN simulator."""

    def __init__(self, network: SNNNetwork, seed: int = 12345):
        self.network = network
        self.num_neurons = network.num_neurons
        self.seed = seed

        # CSR Graph
        row_ptr, col_idx, weights, delays = network.to_csr()
        self.row_ptr = row_ptr.astype(np.uint32)
        self.col_idx = col_idx.astype(np.uint32)
        self.weights = weights.astype(np.int16)
        self.delays = delays.astype(np.uint8)

        # History words
        max_delay = int(np.max(self.delays)) if len(self.delays) > 0 else 0
        self.W = max(1, (max_delay + 32) // 32)

        # State arrays
        self.v_mem = np.zeros(self.num_neurons, dtype=np.int16)
        self.i_syn = np.zeros(self.num_neurons, dtype=np.int32)
        self.spike_bitfield = np.zeros((self.num_neurons, self.W), dtype=np.uint32) if self.W > 1 else np.zeros(self.num_neurons, dtype=np.uint32)
        self.burst_phase = np.zeros(self.num_neurons, dtype=np.uint16)
        self.refr_count = np.zeros(self.num_neurons, dtype=np.uint8)

        # Biophysical parameter arrays
        self.shift_v = np.array([n.shift_v for n in network.neurons], dtype=np.uint8)
        self.shift_s = np.array([n.shift_s for n in network.neurons], dtype=np.uint8)
        self.mode = np.array([n.mode for n in network.neurons], dtype=np.uint8)
        self.burst_period = np.array([n.burst_period for n in network.neurons], dtype=np.uint16)
        self.burst_duty = np.array([n.burst_duty for n in network.neurons], dtype=np.uint16)
        self.refractory = np.array([n.refractory for n in network.neurons], dtype=np.uint8)
        self.threshold = np.array([n.threshold for n in network.neurons], dtype=np.int16)

        # Poisson threshold calculation (32-bit uint)
        self.poisson_thresh = np.array(
            [min(4294967295, int((n.poisson_hz / 1000.0) * 4294967296)) for n in network.neurons],
            dtype=np.uint32,
        )

        # Telemetry
        self.tick = 0
        self.spike_history: List[Tuple[int, int]] = []  # (tick, neuron_id)
        self.rng_state = np.uint32(seed)

    def _next_xorshift32(self) -> np.uint32:
        self.rng_state ^= self.rng_state << np.uint32(13)
        self.rng_state ^= self.rng_state >> np.uint32(17)
        self.rng_state ^= self.rng_state << np.uint32(5)
        return self.rng_state

    def step(self) -> int:
        """Execute one discrete integer tick (equivalent to 1 ms at 1000 Hz)."""
        tick_spikes = 0
        n = self.num_neurons

        # Step 1: Membrane leak, Synaptic decay, Spontaneous drives, and Threshold Check
        for i in range(n):
            v = int(self.v_mem[i])
            kv = int(self.shift_v[i])
            if v > 0:
                v -= max(1, v >> kv)
            elif v < 0:
                v -= min(-1, v >> kv)

            isyn = int(self.i_syn[i])
            ks = int(self.shift_s[i])
            if isyn > 0:
                isyn -= max(1, isyn >> ks)
            elif isyn < 0:
                isyn -= min(-1, isyn >> ks)
            self.i_syn[i] = isyn

            v += (isyn >> 2)
            # Clamp to prevent integer underflow/overflow
            if v > 2048:
                v = 2048
            elif v < -2048:
                v = -2048

            m = self.mode[i]
            if m == 1:
                # Poisson pacemaker
                rng = self._next_xorshift32()
                if rng < self.poisson_thresh[i]:
                    v = int(self.threshold[i])
            elif m == 2:
                # Burster pacemaker
                period = int(self.burst_period[i]) or 200
                duty = int(self.burst_duty[i]) or 24
                phase = (int(self.burst_phase[i]) + 1) % period
                self.burst_phase[i] = phase
                if phase < duty and (phase & 3) == 0:
                    v = int(self.threshold[i])

            spiked = 1 if v >= int(self.threshold[i]) else 0
            if self.refr_count[i] > 0:
                # absolute refractory period: no spike, v held at the reset value (random draws are still consumed)
                self.refr_count[i] -= 1
                spiked = 0
                v = -256
            if spiked:
                self.refr_count[i] = self.refractory[i]
                self.v_mem[i] = -256
                tick_spikes += 1
                self.spike_history.append((self.tick, i))
            else:
                self.v_mem[i] = v

            # temporal shift register update
            if self.W == 1:
                bf = int(self.spike_bitfield[i])
                self.spike_bitfield[i] = np.uint32(((bf << 1) | spiked) & 0xFFFFFFFF)
            else:
                for w in range(self.W - 1, 0, -1):
                    bf_curr = int(self.spike_bitfield[i, w])
                    bf_prev = int(self.spike_bitfield[i, w - 1])
                    self.spike_bitfield[i, w] = np.uint32(((bf_curr << 1) | (bf_prev >> 31)) & 0xFFFFFFFF)
                bf = int(self.spike_bitfield[i, 0])
                self.spike_bitfield[i, 0] = np.uint32(((bf << 1) | spiked) & 0xFFFFFFFF)

        # Step 2: Synaptic Propagation via CSR with Bitwise Delays
        for i in range(n):
            if self.W == 1:
                bf = int(self.spike_bitfield[i])
                if bf == 0:
                    continue
                start = int(self.row_ptr[i])
                end = int(self.row_ptr[i + 1])
                for syn in range(start, end):
                    delay = int(self.delays[syn])
                    if (bf >> delay) & 1:
                        target = int(self.col_idx[syn])
                        self.i_syn[target] += int(self.weights[syn])
            else:
                has_spikes = False
                for w in range(self.W):
                    if self.spike_bitfield[i, w] != 0:
                        has_spikes = True
                        break
                if not has_spikes:
                    continue
                start = int(self.row_ptr[i])
                end = int(self.row_ptr[i + 1])
                for syn in range(start, end):
                    delay = int(self.delays[syn])
                    w = delay >> 5
                    bit = delay & 31
                    if w < self.W and (int(self.spike_bitfield[i, w]) >> bit) & 1:
                        target = int(self.col_idx[syn])
                        self.i_syn[target] += int(self.weights[syn])

        self.tick += 1
        return tick_spikes

    def run(self, ticks: int = 1000) -> Dict[str, Any]:
        """Run simulation for specified number of ticks."""
        total_spikes = 0
        spikes_per_tick = []

        for _ in range(ticks):
            spk = self.step()
            total_spikes += spk
            spikes_per_tick.append(spk)

        mean_pop_rate = (total_spikes / (self.num_neurons * (ticks / 1000.0))) if self.num_neurons > 0 else 0.0

        return {
            "ticks_simulated": ticks,
            "total_spikes": total_spikes,
            "mean_population_hz": round(mean_pop_rate, 2),
            "spikes_per_tick": spikes_per_tick,
            "num_spike_events": len(self.spike_history),
        }

    def plot_raster(self, output_path: str, title: Optional[str] = None) -> None:
        """Export high-resolution spike raster plot."""
        if not self.spike_history:
            return

        ticks, neurons = zip(*self.spike_history)
        ticks = np.array(ticks)
        neurons = np.array(neurons)

        fig, (ax_raster, ax_rate) = plt.subplots(
            2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
        )

        # Plot spikes
        ax_raster.scatter(ticks, neurons, s=1.2, c="#00a8cc", alpha=0.8, edgecolors="none")
        ax_raster.set_ylabel("Neuron Index", fontsize=11, fontweight="normal")
        ax_raster.set_ylim(-1, self.num_neurons)
        ax_raster.set_title(
            title or f"SNN Raster Plot: {self.network.morphology} ({self.num_neurons} neurons)",
            fontsize=12,
            fontweight="normal",
        )
        ax_raster.grid(True, linestyle=":", alpha=0.25, linewidth=0.6)
        ax_raster.spines["top"].set_visible(False)
        ax_raster.spines["right"].set_visible(False)

        # Population rate histogram (10ms bins)
        bins = np.arange(0, self.tick + 10, 10)
        hist, bin_edges = np.histogram(ticks, bins=bins)
        # Convert to population spikes per second
        rate_hz = (hist / 10.0) * 1000.0
        ax_rate.bar(bin_edges[:-1], rate_hz, width=10, color="#ff4081", alpha=0.7, align="edge")
        ax_rate.set_xlabel("Time (ticks / ms)", fontsize=11, fontweight="normal")
        ax_rate.set_ylabel("Spikes / sec", fontsize=11, fontweight="normal")
        ax_rate.grid(True, linestyle=":", alpha=0.25, linewidth=0.6)
        ax_rate.spines["top"].set_visible(False)
        ax_rate.spines["right"].set_visible(False)

        plt.tight_layout()
        plt.savefig(output_path, dpi=200)
        plt.close(fig)
