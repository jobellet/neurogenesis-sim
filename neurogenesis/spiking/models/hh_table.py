"""Hodgkin-Huxley point neuron with tabulated gates: the `hh` model, with the exponential Euler factors of each gate read
from tables over voltage instead of computed with exponentials at every substep.

For each gate x the tables hold x_inf(V) = a / (a + b) and exp(-dt (a + b)) on a grid of 0.05 mV from -120 to +80 mV
(clamped outside), computed once in float64 and interpolated linearly; the update is x <- x_inf + (x - x_inf) * factor
(Rush & Larsen 1978, IEEE Trans Biomed Eng). Tabulated channel rates are the usual way detailed simulators make
Hodgkin-Huxley channels cheap (GENESIS: Bower & Beeman 1998; NEURON: Hines & Carnevale 2000, Neural Comput), and the
gate updates no longer depend on a platform's exp(). Every other part (voltage, synapses, drivers, units) is `hh`.
Known properties (onset of repetitive firing, f-I curve) match `hh` within the tolerances of its tests.
"""
from __future__ import annotations

import numpy as np
import jax.numpy as jnp

from . import hh

name = "hh_table"
description = "Hodgkin-Huxley point neuron with tabulated gates (no exponentials per substep); 40 substeps per 1 ms tick"
substeps = hh.substeps
state_bytes = hh.state_bytes
flops = 70                          # 3 gates x (index, 2 interpolations, update) and the membrane equation, no exp
V_MIN, V_MAX, V_STEP = -120.0, 80.0, 0.05
TABLE_BYTES = 6 * int(round((V_MAX - V_MIN) / V_STEP) + 1) * 4
_TABLES = {}
init_state = hh.init_state


def tables(dt: float):
    """(6, L) float32 tables [m_inf, m_fac, h_inf, h_fac, n_inf, n_fac] for the step dt (ms), cached per dt."""
    if dt not in _TABLES:
        v = np.linspace(V_MIN, V_MAX, int(round((V_MAX - V_MIN) / V_STEP)) + 1)

        def vtrap(x, y):
            with np.errstate(divide="ignore", invalid="ignore"):
                return np.where(np.abs(x / y) < 1e-6, y * (1 - x / y / 2), x / np.expm1(x / y))
        am, bm = 0.1 * vtrap(-(v + 40.0), 10.0), 4.0 * np.exp(-(v + 65.0) / 18.0)
        ah, bh = 0.07 * np.exp(-(v + 65.0) / 20.0), 1.0 / (1.0 + np.exp(-(v + 35.0) / 10.0))
        an, bn = 0.01 * vtrap(-(v + 55.0), 10.0), 0.125 * np.exp(-(v + 65.0) / 80.0)
        rows = []
        for a, b in ((am, bm), (ah, bh), (an, bn)):
            rows += [a / (a + b), np.exp(-dt * (a + b))]
        _TABLES[dt] = np.asarray(rows, np.float32)
    return _TABLES[dt]


def table_gates(v, m, h, n, dt):
    """Gate update from the tables, linear interpolation in V."""
    t = jnp.asarray(tables(float(dt)))
    x = (jnp.clip(v, V_MIN, V_MAX) - V_MIN) / V_STEP
    i = jnp.clip(jnp.floor(x).astype(jnp.int32), 0, t.shape[1] - 2)
    w = x - i
    lo, hi = t[:, i], t[:, i + 1]
    val = lo + w * (hi - lo)
    m = val[0] + (m - val[0]) * val[1]
    h = val[2] + (h - val[2]) * val[3]
    n = val[4] + (n - val[4]) * val[5]
    return m, h, n


def tick(net, st, ext, n_substeps=None):
    return hh.tick(net, st, ext, n_substeps=n_substeps, gates=table_gates)
