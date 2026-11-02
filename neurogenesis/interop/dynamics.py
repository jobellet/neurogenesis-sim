"""One translation of the integer LIF neuron into a current-based exponential LIF, shared by all exporters.

The integer kernel (`neurogenesis.spiking.reference`) updates every neuron once per tick of 1 ms::

    v <- v - max(1, v >> shift_v)    (leak; the mirror rule for v < 0)
    I <- I - max(1, I >> shift_s)    (decay of the neuron's synaptic current, same rounding)
    v <- v + (I >> 2)                (floor of I / 4), then v is clamped to [-2048, 2048]
    spike when v >= threshold; then v <- -256, held there with no spike for `refractory` ticks
    a spike at tick t through a synapse of delay d adds `weight` to the target's I at the end of tick t + d,
    so it first moves v at tick t + d + 1

Without rounding this is the 1-ms sampling of a current-based exponential LIF::

    dV/dt = (E_L - V) / tau_m + I / C_m,    tau_syn dI/dt = -I,

with these correspondences (a = 2^-shift):

- tau = -1 ms / ln(1 - a): the per-tick decay factors match exactly (2^shift ms overestimates tau, by 39 % at
  shift 1 and 1.6 % at shift 5);
- voltage = E_L + s * v for a free scale s (mV per unit): exact, spikes are invariant under it. The default
  (E_L = -65 mV, s = 15/1024 mV) puts the default threshold of 1024 units at -50 mV, as in PyNN's defaults;
- a weight w becomes a current jump W = C_m * s * w * (1 - a) / (4 a tau_syn) (a = 2^-shift_s), which delivers the
  same total charge to V as w delivers to v: an approximation of the PSP shape;
- a delay of d ticks becomes d + 1 ms (the extra tick of synaptic latency), always >= 1 ms;
- the refractory period is `refractory` ms.

Integer rounding, the minimum decrement of 1, the clamp and the 1-ms time step are not represented: spike times in
another simulator are close, not identical. Exporters that can carry extra attributes also store the raw integers,
so that reading the file back into the toolbox is exact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

RESET_UNITS = -256
DEFAULT_E_L = -65.0                 # mV
DEFAULT_MV_PER_UNIT = 15.0 / 1024   # mV per voltage unit
DEFAULT_C_M = 250.0                 # pF (NEST's default for iaf_psc_exp); currents are then in pA


def tau_ms(shift: int) -> float:
    """Time constant (ms) whose 1-ms decay factor equals the kernel's 1 - 2^-shift (shift >= 1)."""
    if shift < 1:
        raise ValueError(f"shift must be >= 1, got {shift}")
    return -1.0 / math.log(1.0 - 2.0 ** -shift)


def shift_from_tau(tau: float) -> int:
    """The kernel shift whose time constant is closest to `tau` (ms), for importers."""
    return min(range(1, 16), key=lambda k: abs(tau_ms(k) - tau))


def delay_ms(delay_ticks: int) -> float:
    """Delay in ms of a synapse of `delay_ticks`, including the kernel's extra tick of latency."""
    return float(delay_ticks) + 1.0


def delay_ticks(delay: float) -> int:
    """Inverse of `delay_ms`, for importers."""
    return max(0, int(round(delay)) - 1)


@dataclass(frozen=True)
class LIFParams:
    """Current-based exponential LIF parameters of one neuron: ms, mV, pF; currents in pA."""
    tau_m: float
    tau_syn: float
    C_m: float
    E_L: float
    V_reset: float
    V_th: float
    t_ref: float
    mV_per_unit: float
    shift_s: int

    def psc_amplitude(self, w: float) -> float:
        """Current jump (pA) of a synapse of integer weight `w` onto this neuron (total charge matched)."""
        a = 2.0 ** -self.shift_s
        return self.C_m * self.mV_per_unit * w * (1.0 - a) / (4.0 * a * self.tau_syn)

    def weight_units(self, amplitude: float) -> float:
        """Inverse of `psc_amplitude`, for importers."""
        a = 2.0 ** -self.shift_s
        return amplitude * 4.0 * a * self.tau_syn / (self.C_m * self.mV_per_unit * (1.0 - a))

    def nest(self) -> dict:
        """Parameters of NEST's `iaf_psc_exp` (I_e = 0)."""
        return dict(C_m=self.C_m, tau_m=self.tau_m, tau_syn_ex=self.tau_syn, tau_syn_in=self.tau_syn,
                    t_ref=self.t_ref, E_L=self.E_L, V_reset=self.V_reset, V_th=self.V_th, I_e=0.0)


def lif_params(neuron, mV_per_unit: float = DEFAULT_MV_PER_UNIT, E_L: float = DEFAULT_E_L,
               C_m: float = DEFAULT_C_M) -> LIFParams:
    """The shared translation of one `NeuronData` (drivers keep their LIF part)."""
    return LIFParams(tau_m=tau_ms(neuron.shift_v), tau_syn=tau_ms(neuron.shift_s), C_m=C_m, E_L=E_L,
                     V_reset=E_L + RESET_UNITS * mV_per_unit, V_th=E_L + neuron.threshold * mV_per_unit,
                     t_ref=float(neuron.refractory), mV_per_unit=mV_per_unit, shift_s=neuron.shift_s)


APPROXIMATION = ("integer LIF -> current-based exponential LIF (neurogenesis.interop.dynamics): "
                 "tau = -1/ln(1 - 2^-shift) ms, V = E_L + s*v, PSC amplitude matched on total charge, "
                 "delay = ticks + 1 ms; integer rounding, the minimum decrement, the +-2048 clamp and the 1-ms "
                 "step are not represented")
