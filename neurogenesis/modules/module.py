"""Shareable modules: a body plan, a genome, an interface and validation records.

A module is what one researcher evolves or designs (for example a retina whose ganglion cells show ON / OFF responses)
and another reuses as-is: inputs are the regions driven by external currents, outputs the regions read out. Modules
can be composed into a larger nervous system: region names get a prefix ("retina.ganglion"), each module keeps its own
genes, and links add new projections (with their own guidance genes) between modules.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..development.grow import grow
from ..development.plan import BodyPlan, Count, FixedPlacement, Region
from ..genome.io import from_json, to_json

REGION_ROOTS = ("count", "migration", "inhibitory", "excitability", "differentiation", "identity", "types")
FORMAT = "neurogenesis-module/1"


@dataclass
class Module:
    name: str
    plan: BodyPlan
    genome: dict
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    description: str = ""
    validation: dict = field(default_factory=dict)       # metrics, seeds, pass fractions (how the module was tested)
    provenance: dict = field(default_factory=dict)       # authors, source repository, commit, date

    def grow(self, seed=0, **kw):
        return grow(self.plan, self.genome, seed, **kw)

    def to_dict(self):
        return dict(format=FORMAT, name=self.name, description=self.description, plan=self.plan.to_dict(),
                    genome=to_json(self.genome), inputs=list(self.inputs), outputs=list(self.outputs),
                    validation=to_json(self.validation), provenance=to_json(self.provenance))

    @classmethod
    def from_dict(cls, d):
        assert d.get("format") == FORMAT, f"not a {FORMAT} file"
        return cls(name=d["name"], plan=BodyPlan.from_dict(d["plan"]), genome=from_json(d["genome"]), inputs=list(d["inputs"]),
                   outputs=list(d["outputs"]), description=d.get("description", ""), validation=d.get("validation", {}),
                   provenance=d.get("provenance", {}))

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=1))

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))


def _prefix_genome(genome, plan, prefix):
    """Genome of a module with region names prefixed; per-module global genes moved into its projections; other
    top-level genes (used by placements) renamed "prefix.key"."""
    g = copy.deepcopy(genome)
    out = {r: {} for r in REGION_ROOTS}
    out["guidance"] = {}
    names = {r.name for r in plan.regions}
    for root in REGION_ROOTS:
        for k, v in g.get(root, {}).items():
            if k in names:
                out[root][f"{prefix}.{k}"] = v
    for (s, d), gd in g.get("guidance", {}).items():
        if s in names and d in names:
            gd = dict(gd)
            gd.setdefault("wc", int(g.get("w_clip", 512)))
            if "inh_weight_factor" in g:
                gd.setdefault("inh", g["inh_weight_factor"])
            out["guidance"][(f"{prefix}.{s}", f"{prefix}.{d}")] = gd
    custom = {k: v for k, v in g.items() if k not in REGION_ROOTS + ("guidance", "w_clip", "inh_weight_factor")}
    for k, v in custom.items():
        out[f"{prefix}.{k}"] = v
    return out, set(custom)


def _prefix_region(r, prefix, custom, offset):
    r = copy.deepcopy(r)
    r.name = f"{prefix}.{r.name}"
    r.origin = tuple(float(o) + float(d) for o, d in zip(r.origin, offset))
    if r.placement is not None and r.placement.counts is not None:
        counts = []
        for c in r.placement.counts:
            c = Count(**c) if isinstance(c, dict) else copy.copy(c)
            if c.gene is not None and c.gene[0] in custom:
                c.gene = (f"{prefix}.{c.gene[0]}",) + tuple(c.gene[1:])
            counts.append(c)
        r.placement = FixedPlacement(labels=r.placement.labels, counts=counts, jitter=r.placement.jitter)
    return r


def compose(name, modules, links=(), offsets=None, inh_weight_factor=2.0, w_clip=512):
    """One plan and genome from several modules.

    modules: {prefix: Module}. links: [(src, dst, guidance genes)] with prefixed region names ("retina.ganglion").
    offsets: {prefix: (dx, dy, dz)} shifts a module's regions in space (this changes conduction delays of links only).
    Returns a Module whose inputs and outputs are those of the parts, prefixed.
    """
    regions, projections, genome, inputs, outputs = [], [], {r: {} for r in REGION_ROOTS}, [], []
    genome["guidance"] = {}
    rules = None
    for prefix, m in modules.items():
        gm, custom = _prefix_genome(m.genome, m.plan, prefix)
        for root in REGION_ROOTS + ("guidance",):
            genome[root].update(gm.pop(root))
        genome.update(gm)
        off = (offsets or {}).get(prefix, (0.0, 0.0, 0.0))
        regions += [_prefix_region(r, prefix, custom, off) for r in m.plan.regions]
        projections += [(f"{prefix}.{s}", f"{prefix}.{d}") for s, d in m.plan.projections]
        inputs += [f"{prefix}.{r}" for r in m.inputs]
        outputs += [f"{prefix}.{r}" for r in m.outputs]
        if rules is None:
            rules = dict(m.plan.rules)
        assert dict(m.plan.rules) == rules, "composed modules must use the same guidance rules"
    for s, d, gd in links:
        projections.append((s, d))
        genome["guidance"][(s, d)] = dict(gd)
    genome["inh_weight_factor"], genome["w_clip"] = inh_weight_factor, w_clip
    genome = {k: v for k, v in genome.items() if v != {}}
    plan = BodyPlan(name=name, regions=regions, projections=projections, rules=rules or {})
    return Module(name=name, plan=plan, genome=genome, inputs=inputs, outputs=outputs,
                  provenance=dict(composed_from={p: m.name for p, m in modules.items()}))
