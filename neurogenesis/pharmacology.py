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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from .tissue import Tissue

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
                    require_transmitter: bool = True, drugs: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Rewrites synapse weights in place from their receptor classes: |w| x gain with the receptor's sign in
    `context` ("pre": the weight keeps its sign, which stages set from the presynaptic cell). With
    `require_transmitter`, a synapse whose receptor binds a transmitter that the presynaptic cell does not release
    gets weight 0. Signs are recomputed from the receptor at every call, so the function can be applied again in
    another context (e.g. "immature", then "mature"); gains multiply the magnitudes at every call, so give gains other
    than 1 only in one compilation. Supports drug dose modulation via `drugs` argument or `genome["drugs"]`.
    Returns counts: synapses changed and silenced. O(E)."""
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

    # Drug dose modulation
    raw_drugs = drugs if drugs is not None else (genome.get("drugs") or (genome.get("pharmacology") or {}).get("drugs") or {})
    active_drugs = dict(raw_drugs) if isinstance(raw_drugs, (dict, list, tuple)) else {}
    if active_drugs:
        for k, r in enumerate(profile.receptors):
            r_name = r.name.lower()
            t_name = (r.transmitter or "").lower()
            for d_name, d_val in active_drugs.items():
                d_key = str(d_name).lower()
                target_match = False
                effect = "antagonist"
                dose = 0.0
                if isinstance(d_val, dict):
                    rec_spec = str(d_val.get("receptor") or d_val.get("target") or "").lower()
                    if rec_spec and (rec_spec == r_name or rec_spec == t_name):
                        target_match = True
                    elif not rec_spec and (d_key in r_name or r_name in d_key or (t_name and (d_key in t_name or t_name in d_key))):
                        target_match = True
                    effect = str(d_val.get("effect", "antagonist")).lower()
                    dose = float(resolve(d_val.get("dose", 0.0), genome, {}))
                else:
                    if d_key in r_name or r_name in d_key or (t_name and (d_key in t_name or t_name in d_key)) or d_key == "drug":
                        target_match = True
                    if "agonist" in d_key or "potentiator" in d_key:
                        effect = "agonist"
                    else:
                        effect = "antagonist"
                    dose = float(resolve(d_val, genome, {}))

                if target_match:
                    if effect == "antagonist":
                        gains[k] *= max(0.0, 1.0 - dose)
                    elif effect == "agonist":
                        gains[k] *= max(0.0, 1.0 + dose)
                    else:
                        gains[k] *= max(0.0, float(dose))
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
    if any(r.reversal_mV is not None or (context and context in r.contexts and "reversal_mV" in r.contexts[context])
           for r in profile.receptors):
        e_rev = np.full(len(profile.receptors), np.nan, dtype=np.float32)
        for k, r in enumerate(profile.receptors):
            over = r.contexts.get(context, {}) if context else {}
            rv = over.get("reversal_mV", r.reversal_mV)
            if rv is not None:
                e_rev[k] = float(resolve(rv, genome, {}))
        c.e_rev = e_rev[rc]
    if any(r.tau_ms is not None or (context and context in r.contexts and "tau_ms" in r.contexts[context])
           for r in profile.receptors):
        tau_decay = np.full(len(profile.receptors), np.nan, dtype=np.float32)
        for k, r in enumerate(profile.receptors):
            over = r.contexts.get(context, {}) if context else {}
            tm = over.get("tau_ms", r.tau_ms)
            if tm is not None:
                tau_decay[k] = float(resolve(tm, genome, {}))
        c.tau_decay = tau_decay[rc]
    return dict(changed=changed, silenced=int(silenced.sum()))


def compile_conductances(tissue, profile: Profile, context: Optional[str] = None, genome: Optional[Dict[str, Any]] = None,
                         require_transmitter: bool = True) -> Dict[str, int]:
    """Maps each synapse's (transmitter, receptor_class, context) into reversal potential E_rev (mV, float32),
    tau_decay (ms, float32), and signed weight using the profile entries."""
    c = tissue.connectivity
    c._sync()
    E = len(c.pre)
    if E == 0:
        return dict(changed=0, silenced=0)
    res = compile_weights(tissue, profile, context=context, genome=genome, require_transmitter=require_transmitter)
    if c.e_rev is None:
        c.e_rev = np.full(E, np.nan, dtype=np.float32)
    if c.tau_decay is None:
        c.tau_decay = np.full(E, np.nan, dtype=np.float32)
    return res


def apply_drug(tissue, profile: Profile, drug: str = "drug", dose: float = 0.0,
               effect: str = "antagonist", receptor: Optional[str] = None) -> Dict[str, int]:
    """Applies a drug dose to tissue in place, modifying weights."""
    drug_spec = {drug: {"dose": dose, "effect": effect, "receptor": receptor} if receptor else {"dose": dose, "effect": effect}}
    return compile_weights(tissue, profile, genome={"drugs": drug_spec}, drugs=drug_spec)


from .stages.base import register_stage


@register_stage("apply_drug")
class ApplyDrug:
    """Applies a pharmacological drug dose to modulate receptor gains and synapse weights."""
    title = "Apply Drug"
    repeatable = True
    conditional = True

    def __init__(self, drug: str = "drug", dose: Any = 0.0, effect: str = "antagonist",
                 receptor: Optional[str] = None, profile: Union[str, Profile] = "default"):
        self.drug = drug
        self.dose = dose
        self.effect = effect
        self.receptor = receptor
        self.profile = profile

    def run(self, tissue: Tissue, params: Optional[Dict[str, Any]] = None,
            genome: Optional[Dict[str, Any]] = None, fields: Optional[Dict[str, Any]] = None,
            rng: Optional[np.random.Generator] = None) -> Tissue:
        params = params or {}
        genome = genome or {}
        fields = fields or {}
        prof_val = params.get("profile", getattr(self, "profile", "default"))
        prof = load_profile(resolve(prof_val, genome, fields))
        drug_val = params.get("drug", getattr(self, "drug", "drug"))
        drug = str(resolve(drug_val, genome, fields))
        dose_val = params.get("dose", getattr(self, "dose", 0.0))
        dose = float(resolve(dose_val, genome, fields))
        effect_val = params.get("effect", getattr(self, "effect", "antagonist"))
        effect = str(resolve(effect_val, genome, fields))
        receptor_val = params.get("receptor", getattr(self, "receptor", None))
        receptor = str(resolve(receptor_val, genome, fields)) if receptor_val is not None else None
        apply_drug(tissue, prof, drug, dose, effect=effect, receptor=receptor)
        return tissue

    def __call__(self, tissue, plan=None, genome=None, rng=None):
        return self.run(tissue, {}, genome or {}, {}, rng)

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return (E * 4, E * 2)

