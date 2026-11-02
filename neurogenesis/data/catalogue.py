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
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

PACKAGE_DATASETS = Path(__file__).resolve().parent / "datasets"
CHUNK = 1 << 20


class DataError(RuntimeError):
    """A manifest is missing or invalid, a download failed, or a checksum does not match."""


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
