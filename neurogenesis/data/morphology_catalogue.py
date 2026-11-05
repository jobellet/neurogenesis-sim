"""Morphology reconstruction catalogue and verified downloader (M2).

Mirrors `neurogenesis.data.catalogue` for public SWC reconstruction banks (e.g. NeuroMorpho.Org, MICrONS).
Manifests (`datasets/morphology/<id>.json`) declare file metadata, SHA-256 checksums, citation and licence,
with per-cell condition labels (region, layer, age, species, etc.).
Downloads go to $NEUROGENESIS_MORPHOLOGY_DATA (default `~/.cache/neurogenesis/data/morphology/<id>/`).
Verified with SHA-256; partial downloads resume via HTTP Range requests. NEVER downloads in tests.
Core logic remains strictly generic (no hardcoded species or organ names).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from ..arbors import ArborStore, read_swc

PACKAGE_DATASETS = Path(__file__).resolve().parent.parent.parent / "datasets" / "morphology"
CHUNK = 1 << 20


class MorphologyDataError(RuntimeError):
    """A morphology manifest is missing or invalid, a download failed, or a checksum does not match."""


def morphology_data_dir(target: Optional[Union[str, Path]] = None) -> Path:
    """Root cache directory for morphology reconstruction downloads."""
    return Path(target or os.environ.get("NEUROGENESIS_MORPHOLOGY_DATA",
                                        Path.home() / ".cache" / "neurogenesis" / "data" / "morphology"))


def validate_morphology_manifest(m: Dict[str, Any]) -> None:
    for key in ("id", "license", "files"):
        if key not in m:
            raise MorphologyDataError(f"morphology manifest is missing {key!r}")
    for f in m["files"]:
        if "name" not in f or "sha256" not in f:
            raise MorphologyDataError(f"morphology file entry {f!r} needs 'name' and 'sha256'")
        if "url" not in f and "url" not in m:
            raise MorphologyDataError(f"file {f['name']!r} has no url and the manifest has no base url")


def load_morphology_manifest(ref: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """Loads a morphology manifest from a dict, a file path, or a manifest id."""
    if isinstance(ref, dict):
        m = ref
    else:
        p = Path(ref)
        candidates = [p] if p.suffix == ".json" else []
        for d in (os.environ.get("NEUROGENESIS_MORPHOLOGY_DATASETS"), "datasets/morphology", "datasets", PACKAGE_DATASETS):
            if d:
                candidates.append(Path(d) / f"{ref}.json")
                candidates.append(Path(d) / str(ref))
        found = next((c for c in candidates if c.exists()), None)
        if found is None:
            raise MorphologyDataError(f"no morphology manifest found for {ref!r} (looked in {[str(c) for c in candidates]})")
        m = json.loads(found.read_text(encoding="utf-8"))
    validate_morphology_manifest(m)
    return m


def total_morphology_size(m: Dict[str, Any]) -> Optional[int]:
    sizes = [f.get("size") for f in m["files"]]
    return None if any(s is None for s in sizes) else int(sum(sizes))


def describe_morphology_manifest(m: Dict[str, Any]) -> str:
    size = total_morphology_size(m)
    s = "unknown size" if size is None else f"{size / 1e3:.1f} KB" if size < 1e6 else f"{size / 1e6:.1f} MB"
    return (f"{m['id']}: {m.get('title', '')}\n  {len(m['files'])} files, {s}\n  license: {m['license']}\n"
            f"  cite: {m.get('citation', '(none given)')}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _download_swc(url: str, dest: Path) -> None:
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
    try:
        with urllib.request.urlopen(req) as resp, open(part, "ab" if start else "wb") as f:
            if start and resp.status == 200:
                f.seek(0)
                f.truncate()
            shutil.copyfileobj(resp, f, length=CHUNK)
        part.rename(dest)
    except Exception as e:
        raise MorphologyDataError(f"download failed for {url}: {e}") from e


def fetch_morphology_manifest(ref: Union[str, Path, Dict[str, Any]], target: Optional[Union[str, Path]] = None,
                              progress: Optional[Callable[[str, int, Optional[int]], None]] = None) -> Path:
    """Downloads and verifies the SWC files declared by a morphology manifest."""
    m = load_morphology_manifest(ref)
    dest_dir = morphology_data_dir(target) / m["id"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Print catalogue info and verified checksum before download
    print(describe_morphology_manifest(m))
    for f in m["files"]:
        target_file = dest_dir / f["name"]
        expected = f["sha256"].lower()
        if target_file.exists():
            got = sha256_file(target_file).lower()
            if got == expected:
                continue
            target_file.unlink()
        url = f.get("url") or (m["url"].rstrip("/") + "/" + f["name"].lstrip("/"))
        print(f"Downloading {f['name']} (SHA256: {expected})...")
        _download_swc(url, target_file)
        got = sha256_file(target_file).lower()
        if got != expected:
            target_file.unlink(missing_ok=True)
            raise MorphologyDataError(f"checksum mismatch on {f['name']}: expected {expected}, got {got}")
    return dest_dir


def load_catalogue_cells(ref_or_dir: Union[str, Path, Dict[str, Any]],
                         base_dir: Optional[Union[str, Path]] = None) -> Tuple[List[ArborStore], List[Dict[str, Any]]]:
    """Loads catalogue SWC reconstructions and per-cell condition metadata.

    If `ref_or_dir` is a manifest or manifest id, reads the declared SWC files from `base_dir`
    (or downloaded cache directory).
    If `ref_or_dir` is a directory of SWC files, reads all `.swc` files with empty conditions.
    """
    stores: List[ArborStore] = []
    conditions: List[Dict[str, Any]] = []

    if isinstance(ref_or_dir, dict):
        m = ref_or_dir
    else:
        p = Path(ref_or_dir)
        if p.is_dir():
            swc_files = sorted(p.glob("*.swc"))
            for i, sf in enumerate(swc_files):
                stores.append(read_swc(sf, cell=i))
                conditions.append({"file": sf.name})
            return stores, conditions
        m = load_morphology_manifest(ref_or_dir)
    root = Path(base_dir) if base_dir is not None else (morphology_data_dir() / m["id"])
    for i, f in enumerate(m["files"]):
        swc_path = root / f["name"]
        if not swc_path.exists():
            raise MorphologyDataError(f"catalogue file {swc_path} does not exist (run fetch or provide base_dir)")
        s = read_swc(swc_path, cell=i)
        stores.append(s)
        cond = dict(f.get("conditions", {}))
        cond["file"] = f["name"]
        conditions.append(cond)
    return stores, conditions
