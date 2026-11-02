"""Transmitter and receptor pharmacology as data (P1), compiled to signed integer weights (P3).

A profile lists transmitters and receptor classes. A cell releases the transmitters set in its bitmask
`Tissue.transmitter` (bit k = transmitter k, up to 7); a synapse's `receptor_class` (index into the profile's
receptors) says how the postsynaptic cell responds. Each receptor has:
- `transmitter`: the transmitter it binds (None for the classic receptor);
- `sign`: +1 (depolarising), -1 (hyperpolarising) or "pre" (the presynaptic sign, i.e. today's behaviour);
- `gain`: weight factor (a number or a `Param`, default 1);
- optional `reversal_mV` and `tau_ms` (recorded for conductance models, P4; not used by `lif_int`);
- optional `contexts`: {context: {sign, gain}} overrides, for developmental switches such as GABA-A currents that
  depolarise immature neurons (Ben-Ari 2002, Nat Rev Neurosci).

The default profile has one receptor, class 0 "classic", sign "pre", gain 1: compiling with it leaves every weight
unchanged, so existing plans and networks keep their fingerprints. Profiles are JSON
(`{"id", "transmitters": [...], "receptors": [...]}`), loaded by id from $NEUROGENESIS_PROFILES, the working directory's
`profiles/` folder, or a path.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from .params import resolve

MAX_TRANSMITTERS = 7


@dataclass
class Receptor:
    name: str
    transmitter: Optional[str] = None
    sign: Union[int, str] = "pre"
    gain: Any = 1.0
    reversal_mV: Optional[float] = None
    tau_ms: Optional[float] = None
    contexts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    citation: str = ""

    def resolved(self, context: Optional[str], genome: Dict[str, Any]) -> tuple:
        """(sign, gain) in a developmental context."""
        over = self.contexts.get(context, {}) if context else {}
        sign = over.get("sign", self.sign)
        gain = float(resolve(over.get("gain", self.gain), genome, {}))
        return sign, gain


@dataclass
class Profile:
    id: str
    transmitters: List[str] = field(default_factory=list)
    receptors: List[Receptor] = field(default_factory=lambda: [Receptor("classic")])
    description: str = ""

    def __post_init__(self):
        if len(self.transmitters) > MAX_TRANSMITTERS:
            raise ValueError(f"at most {MAX_TRANSMITTERS} transmitters (int8 bitmask)")
        if len(self.receptors) > 255:
            raise ValueError("at most 255 receptor classes (uint8)")
        for r in self.receptors:
            if r.transmitter is not None and r.transmitter not in self.transmitters:
                raise ValueError(f"receptor {r.name!r} binds unknown transmitter {r.transmitter!r}")
            if r.sign not in (1, -1, "pre"):
                raise ValueError(f"receptor {r.name!r}: sign must be +1, -1 or 'pre'")

    def bit(self, transmitter: str) -> int:
        return 1 << self.transmitters.index(transmitter)

    def receptor_index(self, name: Union[str, int]) -> int:
        if isinstance(name, (int, np.integer)):
            return int(name)
        return [r.name for r in self.receptors].index(name)

    def to_dict(self) -> Dict[str, Any]:
        return dict(id=self.id, description=self.description, transmitters=list(self.transmitters),
                    receptors=[{k: v for k, v in r.__dict__.items() if v not in (None, "", {})} for r in self.receptors])

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Profile":
        return cls(id=d["id"], transmitters=list(d.get("transmitters", [])), description=d.get("description", ""),
                   receptors=[Receptor(**r) for r in d.get("receptors", [{"name": "classic"}])])


DEFAULT = Profile("default", description="one classic receptor: weights keep the presynaptic sign (legacy behaviour)")


def load_profile(ref: Union[str, Dict[str, Any], Profile, None]) -> Profile:
    """A profile from a Profile, an inline dict, a path, or an id (searched in $NEUROGENESIS_PROFILES, then
    ./profiles/<id>.json); None or "default" is the default profile."""
    if ref is None or ref == "default":
        return DEFAULT
    if isinstance(ref, Profile):
        return ref
    if isinstance(ref, dict):
        return Profile.from_dict(ref)
    p = Path(ref)
    candidates = [p] if p.suffix == ".json" else []
    for d in [os.environ.get("NEUROGENESIS_PROFILES"), "profiles"]:
        if d:
            candidates.append(Path(d) / f"{ref}.json")
    for c in candidates:
        if c.exists():
            return Profile.from_dict(json.loads(c.read_text()))
    raise FileNotFoundError(f"pharmacology profile {ref!r} not found (looked in {[str(c) for c in candidates]})")


def compile_weights(tissue, profile: Profile, context: Optional[str] = None, genome: Optional[Dict[str, Any]] = None,
                    require_transmitter: bool = True) -> Dict[str, int]:
    """Rewrites synapse weights in place from their receptor classes: |w| x gain with the receptor's sign in
    `context` ("pre": the weight keeps its sign, which stages set from the presynaptic cell). With
    `require_transmitter`, a synapse whose receptor binds a transmitter that the presynaptic cell does not release
    gets weight 0. Signs are recomputed from the receptor at every call, so the function can be applied again in
    another context (e.g. "immature", then "mature"); gains multiply the magnitudes at every call, so give gains other
    than 1 only in one compilation. Returns counts: synapses changed and silenced. O(E)."""
    genome = genome or {}
    c = tissue.connectivity
    c._sync()
    E = len(c.pre)
    if E == 0:
        return dict(changed=0, silenced=0)
    rc = c.receptor_class.astype(np.int64)
    if rc.max() >= len(profile.receptors):
        raise ValueError(f"receptor_class {int(rc.max())} is not in profile {profile.id!r}")
    signs = np.zeros(len(profile.receptors))
    pre_sign = np.zeros(len(profile.receptors), bool)
    gains = np.ones(len(profile.receptors))
    need = np.zeros(len(profile.receptors), np.int64)
    for k, r in enumerate(profile.receptors):
        s, g = r.resolved(context, genome)
        pre_sign[k] = s == "pre"
        signs[k] = 0 if s == "pre" else float(s)
        gains[k] = g
        need[k] = profile.bit(r.transmitter) if r.transmitter is not None else 0
    mag = np.abs(c.weight.astype(np.float64)) * gains[rc]
    keep_sign = np.where(c.weight < 0, -1.0, 1.0)            # weights are made with the presynaptic sign
    sign = np.where(pre_sign[rc], keep_sign, signs[rc])
    w = sign * mag
    silenced = np.zeros(E, bool)
    if require_transmitter:
        released = tissue.transmitter.astype(np.int64)[c.pre] & 0x7F
        silenced = (need[rc] != 0) & ((released & need[rc]) == 0)
        w = np.where(silenced, 0.0, w)
    new = np.round(w).astype(np.int32)
    changed = int(np.sum(new != c.weight))
    c.weight = new
    return dict(changed=changed, silenced=int(silenced.sum()))
