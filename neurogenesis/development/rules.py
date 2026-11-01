"""Axon-guidance rules: how a projection's targets and connection probabilities depend on genes and cell identity.

Growth of a projection src -> dst (neurogenesis.development.grow):
  shift   = c                                         then every "shift" rule
  target  = sigmoid(4 B (pos_src - 1/2) + shift)      then every "target" rule      (positional chemoaffinity)
  p_ij    = p0 exp(-|pos_dst_j - target_i|^2 / 2 sigma^2)   then every "probability" rule
Synapses then form with probability p_ij. Rules are registered by name and listed per phase in the plan (BodyPlan.rules),
so new molecular mechanisms can be added without changing the engine. A rule receives a GuidanceContext and modifies it;
rules must not draw random numbers (development stays reproducible).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RULES = {"shift": {}, "target": {}, "probability": {}}


@dataclass
class GuidanceContext:
    src: str
    dst: str
    pos_src: np.ndarray          # (Ns, 3) local positions
    pos_dst: np.ndarray          # (Nd, 3)
    inhibitory_src: np.ndarray   # (Ns,) bool
    identity_src: np.ndarray | None   # (Ns,) int, molecular identity of the source neurons (None: untyped region)
    gd: dict                     # the projection's genes (genome["guidance"][(src, dst)])
    shift: np.ndarray | None = None
    target: np.ndarray | None = None
    p: np.ndarray | None = None


def register(phase, name):
    """Decorator: register a guidance rule for a phase ("shift", "target" or "probability")."""
    def deco(fn):
        RULES[phase][name] = fn
        return fn
    return deco


@register("shift", "identity_offset")
def identity_offset(ctx):
    """Each molecular identity of the source region adds its own target offset (genes gd["type_c"], K x 3)."""
    if ctx.identity_src is not None and "type_c" in ctx.gd:
        ctx.shift = ctx.shift + np.asarray(ctx.gd["type_c"], float)[ctx.identity_src]


@register("target", "lamina")
def lamina(ctx):
    """Laminar targeting: the target depth (w) is set by the source neuron's channel, read from its w label
    (gd["lamina"]: one depth per channel, channels evenly spaced on w)."""
    if "lamina" in ctx.gd:
        lam = np.asarray(ctx.gd["lamina"], float)
        ctx.target = ctx.target.copy()
        ctx.target[:, 2] = lam[np.clip(np.round(ctx.pos_src[:, 2] * (len(lam) - 1)).astype(int), 0, len(lam) - 1)]


@register("probability", "identity_expression")
def identity_expression(ctx):
    """Each identity expresses the projection's guidance receptor at its own level (gd["type_s"], K values in [0, 1])."""
    if ctx.identity_src is not None and "type_s" in ctx.gd:
        ctx.p = ctx.p * np.clip(np.asarray(ctx.gd["type_s"], float)[ctx.identity_src], 0.0, 1.0)[:, None]


@register("probability", "no_autapse")
def no_autapse(ctx):
    """No synapse from a neuron onto itself."""
    if ctx.src == ctx.dst:
        np.fill_diagonal(ctx.p, 0.0)


@register("probability", "source_sign")
def source_sign(ctx):
    """gd["source"] = "exc" or "inh": the projection is made only by excitatory or only by inhibitory neurons."""
    if ctx.gd.get("source") in ("exc", "inh"):
        ctx.p = ctx.p * (ctx.inhibitory_src == (ctx.gd["source"] == "inh"))[:, None]
