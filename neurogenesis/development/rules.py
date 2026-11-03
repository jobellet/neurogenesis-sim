"""Developmental rules: the extension points of growth.

Five phases, each a list of named rules in the plan (BodyPlan.rules); a rule acts only when the genes it reads are present,
so adding a rule to a plan never changes networks whose genomes do not use it. Rules must not draw random numbers.
  placement    PlacementContext: moves the local positions of a region's neurons, after their placement and before
               their sign is drawn (e.g. "mosaic": homotypic repulsion);
  shift, target, probability    GuidanceContext: axon guidance of a projection (below);
  weight       WeightContext: modifies the weights of a projection's new synapses before rounding and clipping
               (e.g. "receptor_sign": sign-inverting receptors).

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

RULES = {"placement": {}, "shift": {}, "target": {}, "probability": {}, "weight": {}}


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


@dataclass
class PlacementContext:
    region: str
    pos: np.ndarray              # (n, 3) local positions, modified in place by rules
    genome: dict


@dataclass
class WeightContext:
    src: str
    dst: str
    pre: np.ndarray              # (S,) source index within the region of each new synapse
    post: np.ndarray             # (S,) target index within the region
    w: np.ndarray                # (S,) float weights (sign from the source neuron), modified by rules
    gd: dict


def register(phase, name):
    """Decorator: register a rule for a phase ("placement", "shift", "target", "probability" or "weight")."""
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


@register("target", "topographic")
def topographic(ctx):
    """Point-to-point map (matched gradients): along the axes set in gd["topographic"] (e.g. [1, 1, 0]), the target equals
    the source's own local position, instead of the sigmoid map."""
    if "topographic" in ctx.gd:
        m = np.asarray(ctx.gd["topographic"], bool)
        ctx.target = ctx.target.copy()
        ctx.target[:, m] = ctx.pos_src[:, m]


_EXPR_NORMS = ("minmax", "none")


@register("target", "expression_gradient")
def expression_gradient(ctx):
    """Chemoaffinity read from graded receptor expression (Sperry, 1963, PNAS; EphA / ephrin-A and EphB / ephrin-B
    gradients, McLaughlin & O'Leary, 2005, Annu Rev Neurosci): along each listed axis the target logit is
    4 sum_g gain_g sign_g (e_g - 1/2) + shift, e_g the source cell's normalised expression of gene g.

    gd["expression_gradient"]: a list of entries, or {"genes": [...], "mode": ...}. Each entry:
      gene: name in tissue.expression_names (or an int column); axis: 0, 1 or 2 (target u, v, w);
      gain (default 1); sign: +1 / "attract" (high expression -> high target coordinate) or -1 / "repel";
      normalize: "minmax" (default, over the projection's source cells; a constant gene gives 1/2, i.e. no map along
      its axis) or "none" (raw levels, expected in [0, 1]).
    mode: "replace" (default; the listed axes ignore B) or "modulate" (the terms are added to the logit of the current
    target). Requires ctx.expression_src (set by grow_axons from tissue.expression); a missing gene raises ValueError.
    """
    spec = ctx.gd.get("expression_gradient")
    if spec is None:
        return
    entries, mode = (spec.get("genes", []), spec.get("mode", "replace")) if isinstance(spec, dict) else (spec, "replace")
    if mode not in ("replace", "modulate"):
        raise ValueError(f"expression_gradient: mode {mode!r} is not 'replace' or 'modulate'")
    expr = getattr(ctx, "expression_src", None)
    if expr is None or np.asarray(expr).size == 0:
        raise ValueError(f"expression_gradient: projection {ctx.src}->{ctx.dst} has no source expression; "
                         f"run 'express' before 'grow_axons'")
    expr = np.asarray(expr, float)
    names = list(getattr(ctx, "expression_names", None) or [])
    shift = np.broadcast_to(np.asarray(ctx.shift if ctx.shift is not None else 0.0, float), ctx.target.shape)
    logit = np.zeros_like(ctx.target)
    axes = set()
    for e in entries:
        gene = e["gene"]
        if isinstance(gene, str):
            if gene not in names:
                raise ValueError(f"expression_gradient: gene {gene!r} is not in expression_names {names}; name the "
                                 f"columns with express(names=...)")
            col = names.index(gene)
        else:
            col = int(gene)
            if not 0 <= col < expr.shape[1]:
                raise ValueError(f"expression_gradient: column {col} is outside the {expr.shape[1]} expression columns")
        axis = int(e["axis"])
        if axis not in (0, 1, 2):
            raise ValueError(f"expression_gradient: axis {axis} is not 0, 1 or 2")
        sign = e.get("sign", 1)
        sign = {"attract": 1.0, "repel": -1.0}.get(sign, sign) if isinstance(sign, str) else float(sign)
        if sign not in (1.0, -1.0):
            raise ValueError(f"expression_gradient: sign {e.get('sign')!r} is not +1, -1, 'attract' or 'repel'")
        norm = e.get("normalize", "minmax")
        if norm not in _EXPR_NORMS:
            raise ValueError(f"expression_gradient: normalize {norm!r} is not one of {_EXPR_NORMS}")
        x = expr[:, col]
        if norm == "minmax":
            lo, span = x.min(), x.max() - x.min()
            x = (x - lo) / span if span > 0 else np.full_like(x, 0.5)
        logit[:, axis] += 4.0 * float(e.get("gain", 1.0)) * sign * (x - 0.5)
        axes.add(axis)
    if not axes:
        return
    m = sorted(axes)
    t = np.clip(ctx.target[:, m], 1e-12, 1.0 - 1e-12)
    base = shift[:, m] if mode == "replace" else np.log(t / (1.0 - t))
    ctx.target = ctx.target.copy()
    ctx.target[:, m] = 1.0 / (1.0 + np.exp(-np.clip(base + logit[:, m], -30.0, 30.0)))


@register("placement", "mosaic")
def mosaic(ctx, iters=None):
    """Homotypic repulsion (regular mosaics of a cell type): genome["mosaic"][region] = {"spacing": d, "iters": n}; cells
    closer than d in the (u, v) plane push each other apart, n deterministic relaxation steps."""
    mg = ctx.genome.get("mosaic", {}).get(ctx.region)
    if not mg or len(ctx.pos) < 2:
        return
    d0 = float(mg["spacing"])
    for _ in range(int(mg.get("iters", 20))):
        uv = ctx.pos[:, :2]
        diff = uv[:, None, :] - uv[None, :, :]
        dist = np.sqrt((diff ** 2).sum(-1))
        push = np.clip(d0 - dist, 0.0, None) / np.maximum(dist, 1e-9)   # coincident cells (diff = 0) do not move each other
        np.fill_diagonal(push, 0.0)
        ctx.pos[:, :2] = np.clip(uv + 0.5 * (push[:, :, None] * diff).sum(1), 0.0, 1.0)


@register("weight", "receptor_sign")
def receptor_sign(ctx):
    """gd["receptor"] = "inverting": the postsynaptic receptor inverts the transmitter's effect (e.g. a metabotropic
    glutamate receptor that closes a cation channel), so an excitatory source inhibits this target and vice versa."""
    if ctx.gd.get("receptor") == "inverting":
        from ..pharmacology import Receptor
        sign, gain = Receptor("inverting", sign=-1).resolved(None, ctx.gd)
        ctx.w = float(sign) * ctx.w * gain
