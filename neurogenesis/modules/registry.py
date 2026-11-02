"""Local module registry (G1): versioned modules installed into a catalogue, with toolbox compatibility checks.

    python -m neurogenesis install module.json        # copy into the catalogue (refused if incompatible)
    python -m neurogenesis modules                    # list installed modules
    get("name") / get("name", "1.2.0")                # load the latest compatible (or a given) version

The catalogue lives in $NEUROGENESIS_MODULES (default ~/.cache/neurogenesis/modules): `catalogue.json` plus one
`<name>-<version>.json` file per installed module. A module declares its semantic `version` and the toolbox versions it
works with in `toolbox` (comma-separated clauses with >=, <=, >, <, ==, !=; "*" = any).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import __version__ as TOOLBOX_VERSION
from .module import Module

_CLAUSE = re.compile(r"^\s*(>=|<=|==|!=|>|<)?\s*([0-9]+(?:\.[0-9]+){0,2})\s*$")


class RegistryError(RuntimeError):
    """A module cannot be installed or found (incompatible, conflicting or missing)."""


def parse_version(v: str) -> Tuple[int, int, int]:
    """'1.2.3' -> (1, 2, 3); missing parts are 0; pre-release or build suffixes ('-rc1', '+x') are ignored."""
    core = re.split(r"[-+]", str(v).strip(), maxsplit=1)[0]
    parts = [int(p) for p in core.split(".") if p != ""]
    if not parts or len(parts) > 3:
        raise ValueError(f"not a semantic version: {v!r}")
    return tuple(parts + [0] * (3 - len(parts)))  # type: ignore[return-value]


def satisfies(version: str, spec: str) -> bool:
    """Whether a version satisfies a range spec such as ">=0.1, <0.2" ("*" or empty = any)."""
    if spec is None or spec.strip() in ("", "*"):
        return True
    v = parse_version(version)
    for clause in spec.split(","):
        m = _CLAUSE.match(clause)
        if not m:
            raise ValueError(f"invalid version clause {clause!r} in {spec!r}")
        op, ref = m.group(1) or "==", parse_version(m.group(2))
        ok = {">=": v >= ref, "<=": v <= ref, ">": v > ref, "<": v < ref, "==": v == ref, "!=": v != ref}[op]
        if not ok:
            return False
    return True


def catalogue_dir(path: Optional[str] = None) -> Path:
    return Path(path or os.environ.get("NEUROGENESIS_MODULES", Path.home() / ".cache" / "neurogenesis" / "modules"))


def _read(d: Path) -> Dict[str, Any]:
    f = d / "catalogue.json"
    return json.loads(f.read_text()) if f.exists() else {"format": "neurogenesis-catalogue/1", "modules": []}


def _write(d: Path, cat: Dict[str, Any]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "catalogue.json").write_text(json.dumps(cat, indent=1))


def check_compatible(module: Module, toolbox_version: str = TOOLBOX_VERSION) -> None:
    """Raises RegistryError if the module's `toolbox` range excludes this toolbox, or its version is not semantic."""
    parse_version(module.version)
    if not satisfies(toolbox_version, module.toolbox):
        raise RegistryError(f"module {module.name} {module.version} needs toolbox {module.toolbox}, "
                            f"this is {toolbox_version}")


def install(path: str, catalogue: Optional[str] = None, force: bool = False,
            toolbox_version: str = TOOLBOX_VERSION) -> Dict[str, Any]:
    """Validates, checks compatibility and copies a module file into the catalogue; returns its catalogue entry.
    Re-installing the same name and version with different content is refused unless force."""
    src = Path(path)
    text = src.read_text()
    module = Module.from_dict(json.loads(text))
    check_compatible(module, toolbox_version)
    d = catalogue_dir(catalogue)
    cat = _read(d)
    sha = hashlib.sha256(text.encode()).hexdigest()
    old = [e for e in cat["modules"] if e["name"] == module.name and e["version"] == module.version]
    if old and old[0]["sha256"] != sha and not force:
        raise RegistryError(f"{module.name} {module.version} is already installed with different content (use force)")
    fname = f"{module.name}-{module.version}.json"
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_text(text)
    entry = dict(name=module.name, version=module.version, toolbox=module.toolbox, file=fname, sha256=sha,
                 description=module.description, neuron_model=module.neuron_model)
    cat["modules"] = [e for e in cat["modules"] if not (e["name"] == module.name and e["version"] == module.version)]
    cat["modules"].append(entry)
    cat["modules"].sort(key=lambda e: (e["name"], parse_version(e["version"])))
    _write(d, cat)
    return entry


def list_modules(catalogue: Optional[str] = None) -> List[Dict[str, Any]]:
    """Catalogue entries, sorted by name and version."""
    return list(_read(catalogue_dir(catalogue))["modules"])


def get(name: str, version: Optional[str] = None, catalogue: Optional[str] = None,
        toolbox_version: str = TOOLBOX_VERSION) -> Module:
    """Loads an installed module: the given version, or the latest version compatible with this toolbox. The file's
    checksum is verified against the catalogue."""
    d = catalogue_dir(catalogue)
    entries = [e for e in _read(d)["modules"] if e["name"] == name]
    if version is not None:
        entries = [e for e in entries if e["version"] == version]
    else:
        entries = [e for e in entries if satisfies(toolbox_version, e.get("toolbox", "*"))]
    if not entries:
        raise RegistryError(f"no installed module {name!r}" + (f" version {version}" if version else " compatible with this toolbox"))
    e = max(entries, key=lambda x: parse_version(x["version"]))
    text = (d / e["file"]).read_text()
    if hashlib.sha256(text.encode()).hexdigest() != e["sha256"]:
        raise RegistryError(f"{e['file']} does not match its catalogue checksum")
    return Module.from_dict(json.loads(text))


def uninstall(name: str, version: str, catalogue: Optional[str] = None) -> None:
    d = catalogue_dir(catalogue)
    cat = _read(d)
    keep = [e for e in cat["modules"] if not (e["name"] == name and e["version"] == version)]
    if len(keep) == len(cat["modules"]):
        raise RegistryError(f"{name} {version} is not installed")
    (d / f"{name}-{version}.json").unlink(missing_ok=True)
    cat["modules"] = keep
    _write(d, cat)
