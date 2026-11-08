"""Dataset manifests and the resumable, checksum-verified downloader (I1).

A manifest (`datasets/<id>.json`) describes a public dataset without naming it in the code:

    {"id": "toy", "title": "...", "license": "CC-BY-4.0", "citation": "...", "url": "https://.../",
     "files": [{"name": "neurons.csv", "url": "https://.../neurons.csv", "sha256": "...", "size": 1234}],
     "tables": {"neurons": {"file": "neurons.csv", "format": "csv",
                            "columns": {"id": "root_id", "x": "pos_x", "y": "pos_y", "z": "pos_z",
                                        "cell_type": "type", "class": "class", "region": "region",
                                        "side": "side", "transmitter": "nt"}},
                "edges": {"file": "edges.csv", "format": "csv",
                          "columns": {"pre": "pre_root_id", "post": "post_root_id", "count": "syn_count"}}},
     "units": {"voxel_size": [0.004, 0.004, 0.04], "origin": [0, 0, 0], "mirror": [], "unit": "um"}}

A file's `url` may be omitted when the manifest has a base `url` (then base + name). Manifests are found as a path,
in $NEUROGENESIS_DATASETS, in ./datasets/, or in the package's `datasets/` folder. Downloads go to
$NEUROGENESIS_DATA (default ~/.cache/neurogenesis/data)/<id>/, outside the repository; a partial file is resumed
with an HTTP Range request, and every file is verified against its SHA-256 before use.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

PACKAGE_DATASETS = Path(__file__).resolve().parent / "datasets"
CHUNK = 1 << 20

CARD_FORMAT = "neurogenesis-card/1"
ORCID_REGEX = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
DOI_REGEX = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$")


class DataError(RuntimeError):
    """A manifest is missing or invalid, a download failed, or a checksum does not match."""


class CardError(ValueError, DataError):
    """A catalogue card is missing, invalid, or malformed."""


def data_dir(target: Optional[Union[str, Path]] = None) -> Path:
    return Path(target or os.environ.get("NEUROGENESIS_DATA", Path.home() / ".cache" / "neurogenesis" / "data"))


def validate_manifest(m: Dict[str, Any]) -> None:
    for key in ("id", "license", "files"):
        if key not in m:
            raise DataError(f"manifest is missing {key!r}")
    for f in m["files"]:
        if "name" not in f or "sha256" not in f:
            raise DataError(f"manifest file entry {f!r} needs 'name' and 'sha256'")
        if "url" not in f and "url" not in m:
            raise DataError(f"file {f['name']!r} has no url and the manifest has no base url")
    names = {f["name"] for f in m["files"]}
    for t, spec in m.get("tables", {}).items():
        if spec.get("file") not in names:
            raise DataError(f"table {t!r} refers to {spec.get('file')!r}, not a manifest file")


def load_manifest(ref: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """A manifest from a dict, a path, or a dataset id."""
    if isinstance(ref, dict):
        m = ref
    else:
        p = Path(ref)
        candidates = [p] if p.suffix == ".json" else []
        for d in (os.environ.get("NEUROGENESIS_DATASETS"), "datasets", PACKAGE_DATASETS):
            if d:
                candidates.append(Path(d) / f"{ref}.json")
        found = next((c for c in candidates if c.exists()), None)
        if found is None:
            raise DataError(f"no manifest for {ref!r} (looked in {[str(c) for c in candidates]})")
        m = json.loads(found.read_text())
    validate_manifest(m)
    return m


def total_size(m: Dict[str, Any]) -> Optional[int]:
    sizes = [f.get("size") for f in m["files"]]
    return None if any(s is None for s in sizes) else int(sum(sizes))


def describe(m: Dict[str, Any]) -> str:
    size = total_size(m)
    s = "unknown size" if size is None else f"{size / 1e6:.1f} MB"
    return (f"{m['id']}: {m.get('title', '')}\n  {len(m['files'])} files, {s}\n  license: {m['license']}\n"
            f"  cite: {m.get('citation', '(none given)')}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    """Downloads url to dest, resuming a partial dest.part with a Range request (restarts if the server ignores it)."""
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resumed = start > 0 and getattr(r, "status", 200) == 206
            with open(part, "ab" if resumed else "wb") as f:
                shutil.copyfileobj(r, f, CHUNK)
    except Exception as e:                                  # network errors: keep the partial file for a later resume
        raise DataError(f"download of {url} failed: {e}") from e
    part.replace(dest)


def fetch(ref: Union[str, Path, Dict[str, Any]], target: Optional[Union[str, Path]] = None,
          confirm: Optional[Callable[[str], bool]] = None, log: Callable[[str], None] = print) -> Path:
    """Downloads every file of a dataset into <target or data_dir()>/<id>/ and verifies them; files already present
    with the right checksum are kept. `confirm(description)` is asked first (return False to cancel). Returns the
    dataset directory."""
    m = load_manifest(ref)
    d = data_dir(target) / m["id"]
    log(describe(m))
    if confirm is not None and not confirm(describe(m)):
        raise DataError("download cancelled")
    d.mkdir(parents=True, exist_ok=True)
    for f in m["files"]:
        dest = d / f["name"]
        if dest.exists() and sha256(dest) == f["sha256"]:
            log(f"  {f['name']}: present, checksum ok")
            continue
        url = f.get("url") or m["url"].rstrip("/") + "/" + f["name"]
        log(f"  {f['name']}: downloading {url}")
        _download(url, dest)
        got = sha256(dest)
        if got != f["sha256"]:
            dest.unlink()
            raise DataError(f"{f['name']}: checksum {got} does not match the manifest ({f['sha256']})")
        log(f"  {f['name']}: checksum ok")
    (d / "manifest.json").write_text(json.dumps(m, indent=1))
    return d


def validate_card(card: Dict[str, Any]) -> None:
    """Validate that the given dictionary conforms to the neurogenesis-card/1 schema."""
    if not isinstance(card, dict):
        raise CardError("Card must be a dictionary")

    if card.get("format") != CARD_FORMAT:
        raise CardError(f"Card format must be {CARD_FORMAT!r}, got {card.get('format')!r}")

    required = ("format", "id", "version", "project", "genome", "targets", "compute_cost", "provenance", "validation")
    for key in required:
        if key not in card:
            raise CardError(f"Card is missing required field: {key!r}")

    if not isinstance(card["id"], str) or not card["id"].strip():
        raise CardError("Card 'id' must be a non-empty string")
    if not isinstance(card["version"], str) or not card["version"].strip():
        raise CardError("Card 'version' must be a non-empty string")

    # Project validation
    if not isinstance(card["project"], dict):
        raise CardError("Card 'project' must be a dictionary")
    try:
        from ..project import schema
        schema.validate(card["project"])
    except Exception as e:
        raise CardError(f"Card 'project' is invalid: {e}") from e

    # Genome validation
    if not isinstance(card["genome"], dict):
        raise CardError("Card 'genome' must be a dictionary")

    # Targets validation
    if not isinstance(card["targets"], list):
        raise CardError("Card 'targets' must be a list")
    for t in card["targets"]:
        if not isinstance(t, dict):
            raise CardError(f"Each target entry must be a dict, got {type(t).__name__}")

    # Compute cost validation
    cc = card["compute_cost"]
    if not isinstance(cc, dict):
        raise CardError("Card 'compute_cost' must be a dictionary")
    for field in ("memory_bytes", "ops_per_tick", "verdict"):
        if field not in cc:
            raise CardError(f"Card 'compute_cost' missing required field {field!r}")
    if not isinstance(cc["memory_bytes"], (int, float)) or cc["memory_bytes"] <= 0:
        raise CardError("Card compute_cost.memory_bytes must be a positive number")
    if not isinstance(cc["ops_per_tick"], (int, float)) or cc["ops_per_tick"] <= 0:
        raise CardError("Card compute_cost.ops_per_tick must be a positive number")
    if not isinstance(cc["verdict"], str):
        raise CardError("Card compute_cost.verdict must be a string")

    # Provenance validation
    prov = card["provenance"]
    if not isinstance(prov, dict):
        raise CardError("Card 'provenance' must be a dictionary")
    authors = prov.get("authors")
    if not isinstance(authors, list) or len(authors) == 0:
        raise CardError("Card provenance must contain a non-empty 'authors' list")
    for author in authors:
        if not isinstance(author, dict):
            raise CardError("Author in provenance must be a dict")
        if not author.get("name"):
            raise CardError("Author must have a non-empty 'name'")
        orcid = author.get("orcid")
        if not orcid or not ORCID_REGEX.match(str(orcid)):
            raise CardError(f"Invalid or missing ORCID {orcid!r} for author {author.get('name')!r} (must match 0000-0000-0000-0000)")
    if "doi" in prov and prov["doi"] is not None:
        if not DOI_REGEX.match(str(prov["doi"])):
            raise CardError(f"Invalid DOI {prov['doi']!r} in provenance (must match 10.xxxx/...)")

    # Validation records
    val = card["validation"]
    if not isinstance(val, dict):
        raise CardError("Card 'validation' must be a dictionary")
    if "seeds" not in val or not isinstance(val["seeds"], list) or len(val["seeds"]) == 0:
        raise CardError("Card validation must contain a non-empty 'seeds' list")


def load_card(ref: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """Load and validate a catalogue card from dict, file path, or card id."""
    if isinstance(ref, dict):
        validate_card(ref)
        return ref

    p = Path(ref)
    candidates = []
    if p.exists() and p.is_file():
        candidates.append(p)
    elif p.suffix == ".json" and p.exists():
        candidates.append(p)
    else:
        search_dirs = [
            os.environ.get("NEUROGENESIS_CATALOGUE"),
            "catalogue",
            Path(__file__).resolve().parents[2] / "catalogue",
            Path(__file__).resolve().parent / "catalogue",
        ]
        cand_names = [str(ref)]
        if not str(ref).endswith(".json"):
            cand_names.extend([
                f"{ref}.json",
                f"{str(ref).replace('-', '_')}.json",
                f"{str(ref).replace('_', '-')}.json",
            ])
        for d in search_dirs:
            if d:
                for fname in cand_names:
                    cand = Path(d) / fname
                    if cand.exists():
                        candidates.append(cand)
                        break
                if candidates:
                    break
        if not candidates:
            for fname in cand_names:
                if Path(fname).exists():
                    candidates.append(Path(fname))
                    break

    if not candidates:
        raise CardError(f"Catalogue card {ref!r} not found")

    found = candidates[0]
    try:
        data = json.loads(found.read_text(encoding="utf-8"))
    except Exception as e:
        raise CardError(f"Failed to read catalogue card at {found}: {e}") from e

    validate_card(data)
    return data


def save_card(card: Dict[str, Any], path: Union[str, Path]) -> None:
    """Validate and save a catalogue card to a JSON file."""
    validate_card(card)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(card, indent=2), encoding="utf-8")


def pull(ref: Union[str, Path, Dict[str, Any]]) -> Any:
    """Pull a catalogued microcircuit into an evolvable Project (remix loop).
    
    Loads card, instantiates Project, merges evolved genome into project.genome,
    sets metadata, and enables:
        proj = pull("cortical-alpha-microcircuit")
        proj.genome["drugs"]["dose"] = 2.0
    """
    card = load_card(ref)
    from ..project import schema
    from ..project.io import Project
    schema._enable_project_extensions()

    proj_dict = json.loads(json.dumps(card["project"]))
    proj_genome = proj_dict.setdefault("genome", {})
    card_genome = card.get("genome", {})
    for k, v in card_genome.items():
        if isinstance(v, dict) and isinstance(proj_genome.get(k), dict):
            proj_genome[k].update(v)
        else:
            proj_genome[k] = v
    proj_dict["genome"] = proj_genome

    # Ensure drugs sub-dict is accessible if present or referenced
    if "drugs" not in proj_genome and "drug_dose" in proj_genome:
        proj_genome["drugs"] = {"dose": proj_genome["drug_dose"]}

    meta = proj_dict.setdefault("metadata", {})
    meta["card"] = card["id"]
    meta["card_version"] = card["version"]

    if "targets" not in proj_dict and "targets" in card:
        proj_dict["targets"] = card["targets"]
    if "compute_cost" not in proj_dict and "compute_cost" in card:
        proj_dict["compute_cost"] = card["compute_cost"]
    if "provenance" not in proj_dict and "provenance" in card:
        proj_dict["provenance"] = card["provenance"]

    return Project(**proj_dict)

