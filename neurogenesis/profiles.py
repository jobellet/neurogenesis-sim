"""Parameter profiles with declared provenance, and profiles that extend other profiles.

A profile is a JSON file of default parameters for one stage or example (a species, a region, an age range). Nothing
in the stage code depends on a profile: every value can be replaced by a `Param` (a constant, a `Gene`, a `Field`, a
`Fit`). A profile only says what the sensible default is and where it comes from, so that a value taken from a paper, a
value derived from one, an assumption and a free parameter are never confused.

Every top-level key of a profile, except the metadata keys, needs an entry in its `provenance` object, either for the
key itself or (for a list or a dict) for each of its elements, written `key`, `key[2]` or `key.sub`. A trailing `*` matches
key names (`reference_*`). An entry has:
- `status`: `measured` (a value or statement in a paper), `derived` (computed from measured values, with the `method`),
  `assumed` (a modelling choice or an illustrative value, with a `note`) or `free` (a virtual parameter without
  biological counterpart, with a `note`, optionally `bounds` [lo, hi]);
- `quantity`: what the number is (an E_GABA is not an E_Cl);
- `source`: for `measured` and `derived`, a list of `"doi:10...."` or `"ref:Author Year, venue"` strings;
- `evidence`: when there are sources, what was actually read of them: `full_text`, `abstract`, `title_only` or `not_checked`;
- optional `species`, `region`, `age`, `method`, `note`, `bounds`.

A profile may `extends` another one (an id or a path): its keys are merged over the parent's (dicts merge, anything else
is replaced) and its `provenance` entries over the parent's. A key that a child sets or overrides needs a provenance
entry in the child itself, since the parent's entry would describe another species or region.

Profiles are searched by file name or `id` in $NEUROGENESIS_PROFILES, ./profiles and `examples/profiles` of the
repository. This is not the transmitter / receptor profile of `neurogenesis.pharmacology`, which has its own loader,
although such a file can carry a `provenance` block too.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

STATUSES = ("measured", "derived", "assumed", "free")
EVIDENCE = ("full_text", "abstract", "title_only", "not_checked")
META_KEYS = {"id", "description", "citations", "provenance", "age_unit", "notes", "extends"}
_DOI = re.compile(r"^doi:10\.\d{4,9}/\S+$")
_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _search_dirs() -> List[Path]:
    dirs = []
    if os.environ.get("NEUROGENESIS_PROFILES"):
        dirs.append(Path(os.environ["NEUROGENESIS_PROFILES"]))
    dirs += [Path("profiles"), Path(__file__).resolve().parents[1] / "examples" / "profiles"]
    return [d for d in dirs if d.is_dir()]


def find_profile(ref: Union[str, Path]) -> Path:
    """The path of a profile given a path, a file name without extension, or an `id`."""
    p = Path(ref)
    if p.suffix == ".json" and p.exists():
        return p
    for d in _search_dirs():
        if (d / f"{ref}.json").exists():
            return d / f"{ref}.json"
    for d in _search_dirs():
        for f in sorted(d.glob("*.json")):
            try:
                if json.loads(f.read_text(encoding="utf-8")).get("id") == str(ref):
                    return f
            except (ValueError, OSError):
                continue
    raise FileNotFoundError(f"profile {ref!r} not found (looked in {[str(d) for d in _search_dirs()]})")


def _merge(parent: Dict[str, Any], child: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(parent)
    for k, v in child.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _read(ref: Union[str, Path], chain: Tuple[str, ...]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(resolved profile, the profile as written); `chain` guards against `extends` cycles."""
    path = find_profile(ref)
    if str(path.resolve()) in chain:
        raise ValueError(f"profile `extends` cycle: {' -> '.join(chain + (str(path.resolve()),))}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    parent = raw.get("extends")
    if not parent:
        return raw, raw
    base, _ = _read(parent, chain + (str(path.resolve()),))
    resolved = _merge(base, {k: v for k, v in raw.items() if k != "provenance"})
    resolved["provenance"] = {**base.get("provenance", {}), **raw.get("provenance", {})}
    return resolved, raw


def load_parameter_profile(ref: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """The profile with its `extends` chain resolved (a dict is returned as is)."""
    if isinstance(ref, dict):
        return ref
    return _read(ref, ())[0]


def _matches(entry_key: str, path: str) -> bool:
    return entry_key == path or ("*" in entry_key and fnmatch.fnmatchcase(path, entry_key))


def _covered(value: Any, path: str, keys: Iterable[str]) -> bool:
    if any(_matches(k, path) for k in keys):
        return True
    if isinstance(value, dict) and value:
        return all(_covered(v, f"{path}.{k}", keys) for k, v in value.items())
    if isinstance(value, list) and value:
        return all(_covered(v, f"{path}[{i}]", keys) for i, v in enumerate(value))
    return False


def _resolves(profile: Dict[str, Any], key: str) -> bool:
    if "*" in key:
        return any(fnmatch.fnmatchcase(k, key) for k in profile)
    node: Any = profile
    for name, index in _SEGMENT.findall(key):
        if name:
            if not isinstance(node, dict) or name not in node:
                return False
            node = node[name]
        else:
            if not isinstance(node, list) or int(index) >= len(node):
                return False
            node = node[int(index)]
    return True


def _check_entry(key: str, e: Any) -> List[str]:
    if not isinstance(e, dict):
        return [f"provenance[{key!r}]: must be an object"]
    errs: List[str] = []
    status = e.get("status")
    if status not in STATUSES:
        errs.append(f"provenance[{key!r}]: status {status!r} is not one of {STATUSES}")
    if not (isinstance(e.get("quantity"), str) and e["quantity"].strip()):
        errs.append(f"provenance[{key!r}]: `quantity` (what the number is) is required")
    sources = e.get("source", [])
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        errs.append(f"provenance[{key!r}]: `source` must be a list of strings")
        sources = []
    for s in sources:
        if not (_DOI.match(s) or s.startswith("ref:")):
            errs.append(f"provenance[{key!r}]: source {s!r} must be 'doi:10.xxxx/...' or 'ref:<citation>'")
    if status == "measured" and not sources:
        errs.append(f"provenance[{key!r}]: a measured value needs at least one `source`")
    if sources and e.get("evidence") not in EVIDENCE:
        errs.append(f"provenance[{key!r}]: `evidence` must be one of {EVIDENCE} (what was actually read of the sources)")
    if status == "derived" and not (isinstance(e.get("method"), str) and e["method"].strip()):
        errs.append(f"provenance[{key!r}]: a derived value needs a `method`")
    if status in ("assumed", "free") and not (isinstance(e.get("note"), str) and e["note"].strip()):
        errs.append(f"provenance[{key!r}]: an {status} value needs a `note` saying why this value")
    if "bounds" in e:
        b = e["bounds"]
        if not (isinstance(b, list) and len(b) == 2 and all(isinstance(x, (int, float)) for x in b) and b[0] < b[1]):
            errs.append(f"provenance[{key!r}]: `bounds` must be [lo, hi] with lo < hi")
    return errs


def check_profile(ref: Union[str, Path, Dict[str, Any]]) -> List[str]:
    """The problems of a profile (an empty list when it is valid)."""
    if isinstance(ref, dict):
        resolved, raw = ref, ref
    else:
        try:
            resolved, raw = _read(ref, ())
        except (ValueError, FileNotFoundError) as exc:
            return [str(exc)]
    errs: List[str] = []
    if not resolved.get("id"):
        errs.append("`id` is required")
    prov = resolved.get("provenance")
    if not isinstance(prov, dict) or not prov:
        return errs + ["`provenance` is missing: every parameter needs a status and a source"]
    for key, e in prov.items():
        errs += _check_entry(key, e)
        if not _resolves(resolved, key):
            errs.append(f"provenance[{key!r}]: no such key in the profile")
    for k, v in resolved.items():
        if k not in META_KEYS and not _covered(v, k, prov):
            errs.append(f"{k!r}: no provenance entry (add one for the key, or for each element)")
    if raw is not resolved:  # an extending profile: what it sets itself needs its own provenance
        own = raw.get("provenance", {})
        for k, v in raw.items():
            if k not in META_KEYS and not _covered(v, k, own):
                errs.append(f"{k!r}: this profile overrides it but has no provenance entry of its own")
    return errs


def provenance_counts(refs: Iterable[Union[str, Path, Dict[str, Any]]]) -> Dict[str, int]:
    """Number of provenance entries by status over profiles: how much of a set of parameters is measured, derived,
    assumed or free. An entry is a parameter or a group of parameters that share a source."""
    counts = {s: 0 for s in STATUSES}
    for ref in refs:
        for e in load_parameter_profile(ref).get("provenance", {}).values():
            if isinstance(e, dict) and e.get("status") in counts:
                counts[e["status"]] += 1
    return counts


def check_online(ref: Union[str, Path, Dict[str, Any]], timeout: float = 15.0) -> List[str]:
    """Problems found by asking Crossref whether each DOI exists (network; never used by the tests)."""
    import urllib.error
    import urllib.request
    errs: List[str] = []
    for key, e in load_parameter_profile(ref).get("provenance", {}).items():
        for s in e.get("source", []) if isinstance(e, dict) else []:
            if _DOI.match(s):
                try:
                    urllib.request.urlopen(f"https://api.crossref.org/works/{s[4:]}", timeout=timeout).close()
                except urllib.error.HTTPError as exc:
                    errs.append(f"provenance[{key!r}]: {s} not found at Crossref (HTTP {exc.code})")
                except OSError as exc:
                    errs.append(f"provenance[{key!r}]: {s} could not be checked ({exc})")
    return errs


def project_report(project: Dict[str, Any]) -> Dict[str, Any]:
    """What a project's parameters rest on: the profiles it declares in `metadata["profiles"]` (ids or paths of the
    profiles whose defaults it uses), the status of their entries, what was actually read of their sources, and the
    genes and `Fit` parameters it leaves free. A declaration, not a check: the project's own values may differ from the
    profiles', and then the profiles describe only the defaults it started from."""
    from neurogenesis.params import collect_fits, collect_project_genes

    ids = list((project.get("metadata") or {}).get("profiles", []))
    profs = [load_parameter_profile(i) for i in ids]
    evidence = {e: 0 for e in EVIDENCE}
    open_items: List[Dict[str, str]] = []
    for prof in profs:
        for key, e in prof.get("provenance", {}).items():
            if e.get("evidence") in evidence:
                evidence[e["evidence"]] += 1
            if e.get("status") in ("assumed", "free"):
                open_items.append({"profile": str(prof.get("id")), "key": key, "status": e["status"],
                                   "quantity": e.get("quantity", "")})
    return {"profiles": [str(p.get("id")) for p in profs], "counts": provenance_counts(profs), "evidence": evidence,
            "assumed_or_free": open_items, "genes": len(collect_project_genes(project)),
            "fits": len(collect_fits(project))}


def format_report(report: Dict[str, Any]) -> str:
    """The report of `project_report` as text for a log, a README or a use-case page."""
    c = report["counts"]
    lines = [f"profiles: {', '.join(report['profiles']) or 'none declared'}",
             f"entries: {c['measured']} measured, {c['derived']} derived, {c['assumed']} assumed, {c['free']} free",
             "evidence read: " + ", ".join(f"{n} {k}" for k, n in report["evidence"].items() if n) if any(
                 report["evidence"].values()) else "evidence read: none declared",
             f"left to genes: {report['genes']}; to Fit: {report['fits']}"]
    lines += [f"  {i['status']:7s} {i['profile']}.{i['key']}: {i['quantity']}" for i in report["assumed_or_free"]]
    return "\n".join(lines)
