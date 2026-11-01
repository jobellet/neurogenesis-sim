"""Body plan: the declarative, genome-independent part of a nervous system.

A plan lists regions (where neurons are born, and how they are placed) and the projections that may grow between them.
Everything that varies between individuals or evolves lives in the genome (a nested dict), never in the plan. Plans are
plain data and round-trip through JSON, so that a plan and a genome together fully describe a shareable module.

Regions are either
* fixed: neurons at given labels (for example a sensor sheet or the pools of an output), each label possibly
  repeated a genetic number of times, with optional positional jitter drawn at development;
* grown: a genetic number of neurons placed by migration (genome["migration"][region]), each inhibitory with a
  genetic, position-dependent probability (genome["inhibitory"][region]), unless the region's sign is imposed.
Positions are local (u, v, w) in [0, 1]^3; a region's box maps them to space (origin + size * local), which sets
conduction delays.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


def get_path(genome, path, default=None):
    """Value at a gene path (sequence of keys) in a nested genome, or default if any key is missing."""
    node = genome
    for k in path:
        if isinstance(node, dict) and k in node:
            node = node[k]
        else:
            return default
    return node


@dataclass
class Count:
    """A number of neurons: a constant, or a gene (path in the genome) with a default and bounds."""
    value: int = 1
    gene: tuple | None = None
    lo: int = 1
    hi: int = 16

    def resolve(self, genome) -> int:
        v = self.value if self.gene is None else get_path(genome, self.gene, self.value)
        return int(np.clip(round(v), self.lo, self.hi))


@dataclass
class FixedPlacement:
    """Neurons at given local labels; label k is repeated counts[k] times (consecutively).

    jitter: None; {"kind": "normal", "sd": s, "axes": (1, 1, 0)} adds s * N(0, 1) * axes to every label (then clips to
    [0, 1]); {"kind": "uniform", "axes": [1, 2]} replaces the listed coordinates by U(0, 1) draws.
    """
    labels: list
    counts: list | None = None
    jitter: dict | None = None

    def place(self, genome, rng):
        base = np.asarray(self.labels, float).reshape(-1, 3)
        if self.counts is not None:
            reps = np.asarray([Count(**c).resolve(genome) if isinstance(c, dict) else c.resolve(genome) for c in self.counts])
            base = np.repeat(base, reps, axis=0)
        if not self.jitter:
            return base
        if self.jitter["kind"] == "normal":
            return np.clip(base + self.jitter["sd"] * rng.standard_normal(base.shape) * np.asarray(self.jitter["axes"], float),
                           0.0, 1.0)
        if self.jitter["kind"] == "uniform":
            axes = list(self.jitter["axes"])
            out = base.copy()
            out[:, axes] = rng.random((len(base), len(axes)))
            return out
        raise ValueError(f"unknown jitter kind {self.jitter['kind']}")


@dataclass
class Region:
    """A region of the plan. placement None means grown (count, migration and inhibitory genes of this region).

    role: 0 internal, 1 input (driven by external currents), 2 output (read out). sign: None (genetic), "exc" or "inh"
    (imposed on every neuron of the region). refractory: refractory period in ticks.
    """
    name: str
    origin: tuple
    size: tuple
    placement: FixedPlacement | None = None
    role: int = 0
    sign: str | None = None
    refractory: int = 3
    count_bounds: tuple = (4, 1024)

    @property
    def grown(self) -> bool:
        return self.placement is None


DEFAULT_RULES = dict(shift=("identity_offset",), target=("lamina",), probability=("identity_expression", "no_autapse", "source_sign"))


@dataclass
class BodyPlan:
    """Regions, allowed projections (src, dst) in growth order, and physical constants of development."""
    name: str
    regions: list
    projections: list
    conduction_velocity: float = 20.0
    max_delay: int = 31
    ids: dict = field(default_factory=dict)                    # region name -> compartment id stored on each neuron
    rules: dict = field(default_factory=lambda: dict(DEFAULT_RULES))

    def __post_init__(self):
        self.projections = [tuple(p) for p in self.projections]
        if not self.ids:
            self.ids = {r.name: i for i, r in enumerate(self.regions)}
        names = [r.name for r in self.regions]
        assert len(set(names)) == len(names), "region names must be unique"
        for s, d in self.projections:
            assert s in names and d in names, f"projection {s}->{d} between unknown regions"

    def region(self, name) -> Region:
        return next(r for r in self.regions if r.name == name)

    # ------------------------------------------------------------------ JSON
    def to_dict(self) -> dict:
        d = json.loads(json.dumps(asdict(self), default=lambda o: o.tolist() if hasattr(o, "tolist") else list(o)))
        d["projections"] = [list(p) for p in self.projections]
        d["rules"] = {k: list(v) for k, v in self.rules.items()}
        return d

    @classmethod
    def from_dict(cls, d) -> "BodyPlan":
        regions = []
        for r in d["regions"]:
            r = dict(r)
            if r.get("placement") is not None:
                pl = dict(r["placement"])
                if pl.get("counts") is not None:
                    pl["counts"] = [Count(**{**c, "gene": tuple(c["gene"]) if c.get("gene") else None}) for c in pl["counts"]]
                r["placement"] = FixedPlacement(**pl)
            r["origin"], r["size"], r["count_bounds"] = tuple(r["origin"]), tuple(r["size"]), tuple(r.get("count_bounds", (4, 1024)))
            regions.append(Region(**r))
        rules = {k: tuple(v) for k, v in d.get("rules", DEFAULT_RULES).items()}
        return cls(name=d["name"], regions=regions, projections=[tuple(p) for p in d["projections"]],
                   conduction_velocity=d.get("conduction_velocity", 20.0), max_delay=d.get("max_delay", 31),
                   ids=dict(d.get("ids", {})), rules=rules)

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=1))

    @classmethod
    def load(cls, path) -> "BodyPlan":
        return cls.from_dict(json.loads(Path(path).read_text()))
