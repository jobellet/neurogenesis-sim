"""Transmitters, receptor expression and assignment (P2), and compilation in a developmental context (P3)."""
from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np

from neurogenesis.expressions import eval_expr
from neurogenesis.fields import Field
from neurogenesis.geometry import Geometry
from neurogenesis.params import resolve
from neurogenesis.pharmacology import compile_weights, load_profile
from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue


def _env(tissue: Tissue, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Variables of a cell condition: as in `differentiate` (expr, cell_type, region, birth_stage, positions, fields)."""
    env = {"expr": tissue.expression.T, "np": np, "N": len(tissue.alive), "cell_type": tissue.cell_type,
           "region": tissue.region, "birth_stage": tissue.birth_stage, "generation": tissue.generation,
           "sign": tissue.sign, "x": tissue.positions[:, 0], "y": tissue.positions[:, 1], "z": tissue.positions[:, 2]}
    for k, v in fields.items():
        if isinstance(v, Field):
            env[f"field_{k}"] = v.values(tissue.positions)
        elif isinstance(v, Geometry):
            env[f"field_{k}"] = v.contains(tissue.positions).astype(np.float32)
    return env


def _mask(condition, tissue, env) -> np.ndarray:
    if not condition:
        return tissue.alive.copy()
    m = np.asarray(eval_expr(condition, env), dtype=bool)
    return np.broadcast_to(m, tissue.alive.shape) & tissue.alive


@register_stage("set_transmitters")
class SetTransmitters:
    """Sets the transmitters each cell releases (`Tissue.transmitter` bitmask, co-transmission allowed).

    `rules`: list of {condition, transmitters: [names]} applied in order (later rules override); names index the
    profile's `transmitters` (`profile`, default: the default profile, which has none, so names need a profile).
    `add: true` in a rule adds to the cell's transmitters instead of replacing them. No rules is the no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return N * 16, N * 20

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        rules = resolve(params.get("rules", []), genome, fields)
        if not rules or len(tissue.alive) == 0:
            return tissue
        profile = load_profile(resolve(params.get("profile"), genome, fields) if params.get("profile") is not None else None)
        env = _env(tissue, fields)
        for rule in rules:
            bits = 0
            for name in rule.get("transmitters", []):
                bits |= profile.bit(name)
            m = _mask(rule.get("condition"), tissue, env)
            cur = tissue.transmitter.astype(np.int64)
            tissue.transmitter = np.where(m, (cur | bits) if rule.get("add") else bits, cur).astype(np.int8)
        return tissue


@register_stage("express_receptors")
class ExpressReceptors:
    """Receptor expression levels per cell (`Tissue.receptor_expression`, one column per receptor of `profile`).

    `rules`: list of {condition, receptor: name or index, level: number or `Param` (a `Field` is read per cell)};
    matching cells get that level (later rules override). No rules is the no-op.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return N * 64, N * 40

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        rules = resolve(params.get("rules", []), genome, fields)
        if not rules or len(tissue.alive) == 0:
            return tissue
        profile = load_profile(resolve(params.get("profile"), genome, fields) if params.get("profile") is not None else None)
        R = len(profile.receptors)
        rex = tissue.receptor_expression
        if rex.shape[1] != R:
            new = np.zeros((len(tissue.alive), R), np.float32)
            k = min(R, rex.shape[1])
            new[:, :k] = rex[:, :k]
            rex = new
        env = _env(tissue, fields)
        for rule in rules:
            r = profile.receptor_index(rule["receptor"])
            m = _mask(rule.get("condition"), tissue, env)
            level = np.asarray(resolve(rule.get("level", 1.0), genome, fields, positions=tissue.positions), np.float32)
            level = np.broadcast_to(level, (len(tissue.alive),))
            rex[m, r] = level[m]
        tissue.receptor_expression = rex
        return tissue


@register_stage("assign_receptors")
class AssignReceptors:
    """Receptor class of each synapse from transmitter-receptor compatibility (P2).

    For synapse pre -> post, the candidate receptors are those whose transmitter the presynaptic cell releases (plus
    transmitter-free receptors such as the classic one when `allow_classic`, default False), weighted by the
    postsynaptic expression of each. `mode` "sample" (default, from the stage stream) draws one in proportion to the
    expression, "max" takes the most expressed. Synapses without any expressed candidate keep their class. Needs
    `profile`; no profile is the no-op. O(E R).
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        R = 8
        return E * (R * 8 + 16), E * R * 6

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        c = tissue.connectivity
        if params.get("profile") is None or len(c.pre) == 0:
            return tissue
        profile = load_profile(resolve(params["profile"], genome, fields))
        R = len(profile.receptors)
        rex = tissue.receptor_expression
        if rex.shape[1] != R:
            raise ValueError(f"receptor_expression has {rex.shape[1]} columns, profile {profile.id!r} has {R} receptors "
                             "(run express_receptors first)")
        allow_classic = bool(resolve(params.get("allow_classic", False), genome, fields))
        need = np.asarray([profile.bit(r.transmitter) if r.transmitter else 0 for r in profile.receptors], np.int64)
        released = tissue.transmitter.astype(np.int64)[c.pre] & 0x7F
        compat = np.where(need[None, :] == 0, allow_classic, (released[:, None] & need[None, :]) != 0)
        w = compat * np.maximum(rex[c.post], 0.0)                          # (E, R)
        total = w.sum(1)
        ok = total > 0
        mode = str(resolve(params.get("mode", "sample"), genome, fields))
        if mode == "max":
            choice = np.argmax(w, axis=1)
        elif mode == "sample":
            cdf = np.cumsum(w, axis=1)
            u = rng.random(len(c.pre)) * total
            choice = np.minimum((cdf <= u[:, None]).sum(1), R - 1)
        else:
            raise ValueError(f"assign_receptors: unknown mode {mode!r}")
        c._sync()
        c.receptor_class = np.where(ok, choice, c.receptor_class).astype(np.uint8)
        return tissue


@register_stage("pharmacology")
class PharmacologyStage:
    """Compiles synapse weights from receptor classes in a developmental `context` (P3,
    `pharmacology.compile_weights`): sign from the receptor in that context, magnitude x gain, synapses whose
    presynaptic cell lacks the receptor's transmitter silenced (`require_transmitter`, default True). Run it with
    context "immature" before `refine_by_activity` and "mature" afterwards to model a sign switch during development.
    No `profile` is the no-op (the default profile changes nothing).
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return E * 40, E * 20

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        if params.get("profile") is None or len(tissue.connectivity.pre) == 0:
            return tissue
        profile = load_profile(resolve(params["profile"], genome, fields))
        context = params.get("context")
        context = resolve(context, genome, fields) if context is not None else None
        compile_weights(tissue, profile, context, genome,
                        require_transmitter=bool(resolve(params.get("require_transmitter", True), genome, fields)))
        return tissue
