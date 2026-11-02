"""Streaming connectome import (I2), coordinate registration (I3) and synapse-count to weight mapping (I4).

    tissue, info = import_connectome("toy", filters={"cell_type": ["A", "re:^B"], "min_synapses": 3},
                                     weight_map={"kind": "linear", "gain": 20}, transmitter_signs={"gaba": -1})

Tables are read in record batches (`chunk_rows` rows): CSV with NumPy (`np.loadtxt`, no quoted commas inside fields),
or Parquet / Feather / CSV with pyarrow when it is installed (`pip install -e ".[data]"`, imported lazily). Neurons are
filtered batch by batch; edges are kept only between selected neurons and summed per (pre, post) pair, so memory is
O(selected neurons + selected edges). The cost of the network is printed before it is allocated.

Coordinates (I3): x = mirror(raw * voxel_size + origin) from the manifest's `units` (space units, e.g. micrometres),
so soma distances set conduction delays: delay = round(distance / conduction_velocity) ticks, clipped to [1, 31] with
a counted warning (kernel limit until multi-word spike histories, K4).

Weights (I4): |w| = map(synapse count) with `weight_map` {"kind": "linear", "gain"} (gain x count), {"kind": "hill",
"w_max", "k", "n"} (w_max c^n / (k^n + c^n)) or {"kind": "log", "gain"} (gain log(1 + c)); values may be `Param`s;
|w| is rounded, at least 1, and clipped to `w_clip` (512 to 2047). The sign comes from the presynaptic transmitter:
`transmitter_signs` {name: +1 / -1} (default +1), and with a pharmacology `profile` the cells' transmitter bits are
set too. The license, citation and source ids are returned in `info` (provenance).
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

import numpy as np

from ..params import resolve
from ..tissue import SparseConnectivity, Tissue
from .catalogue import DataError, data_dir, load_manifest

MAX_DELAY = 31
NUMERIC = ("id", "x", "y", "z", "pre", "post", "count")


def _pyarrow():
    try:
        import pyarrow  # noqa: F401
        return pyarrow
    except ImportError as e:
        raise DataError("reading Parquet / Feather tables needs pyarrow: pip install -e \".[data]\"") from e


def _header(path: Path) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [h.strip().strip('"') for h in f.readline().rstrip("\n").split(",")]


def read_batches(path: Union[str, Path], fmt: str, columns: Dict[str, str], chunk_rows: int = 1 << 16
                 ) -> Iterator[Dict[str, np.ndarray]]:
    """Batches of a table as {our name: array} for the mapped columns (numeric for ids, positions and counts)."""
    path = Path(path)
    ours, theirs = list(columns), [columns[k] for k in columns]

    def convert(batch: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        out = {}
        for k, v in batch.items():
            if k in ("id", "pre", "post"):
                out[k] = np.asarray(v).astype(np.float64).astype(np.int64) if np.asarray(v).dtype.kind in "USO" else np.asarray(v, np.int64)
            elif k in NUMERIC:
                out[k] = np.asarray(v, np.float64)
            else:
                out[k] = np.asarray(v).astype(str)
        return out

    if fmt == "csv" and not _has_pyarrow():
        head = _header(path)
        missing = [t for t in theirs if t not in head]
        if missing:
            raise DataError(f"{path.name}: columns {missing} not found (header: {head})")
        idx = [head.index(t) for t in theirs]
        with open(path, "r", encoding="utf-8") as f:
            f.readline()
            while True:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)              # "input contained no data" at the end
                    a = np.loadtxt(f, delimiter=",", dtype=str, max_rows=chunk_rows, ndmin=2, usecols=idx, quotechar='"')
                if a.size == 0:
                    return
                yield convert({k: a[:, j] for j, k in enumerate(ours)})
                if len(a) < chunk_rows:
                    return
    pa = _pyarrow()
    if fmt == "csv":
        import pyarrow.csv as pcsv
        reader = pcsv.open_csv(path, read_options=pcsv.ReadOptions(block_size=1 << 22),
                               convert_options=pcsv.ConvertOptions(include_columns=theirs))
        batches = iter(reader)
    elif fmt == "parquet":
        import pyarrow.parquet as pq
        batches = pq.ParquetFile(path).iter_batches(batch_size=chunk_rows, columns=theirs)
    elif fmt == "feather":
        import pyarrow.feather as pf
        batches = iter(pf.read_table(path, columns=theirs).to_batches(chunk_rows))
    else:
        raise DataError(f"unknown table format {fmt!r} (csv, parquet, feather)")
    for b in batches:
        yield convert({k: b.column(b.schema.get_field_index(t)).to_numpy(zero_copy_only=False) for k, t in zip(ours, theirs)})


def _has_pyarrow() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def transform_positions(xyz: np.ndarray, units: Dict[str, Any]) -> np.ndarray:
    """Raw (voxel) coordinates to space units: x * voxel_size + origin, then the listed `mirror` axes negated."""
    out = np.asarray(xyz, np.float64) * np.asarray(units.get("voxel_size", [1.0, 1.0, 1.0]), np.float64)
    out = out + np.asarray(units.get("origin", [0.0, 0.0, 0.0]), np.float64)
    for ax in units.get("mirror", []):
        out[:, int(ax)] = -out[:, int(ax)]
    return out


def map_weights(count: np.ndarray, weight_map: Optional[Dict[str, Any]], genome: Optional[Dict[str, Any]] = None,
                w_clip: int = 512) -> np.ndarray:
    """|weight| (int32, >= 1, <= w_clip) of each synapse from its anatomical synapse count."""
    if not 512 <= int(w_clip) <= 2047:
        raise ValueError("w_clip must be in [512, 2047]")
    wm = dict(weight_map or {"kind": "linear", "gain": 1.0})
    g = lambda k, d: float(resolve(wm.get(k, d), genome or {}, {}))
    c = np.asarray(count, np.float64)
    kind = wm.get("kind", "linear")
    if kind == "linear":
        w = g("gain", 1.0) * c
    elif kind == "hill":
        n, k = g("n", 1.0), g("k", 10.0)
        w = g("w_max", float(w_clip)) * c ** n / (k ** n + c ** n)
    elif kind == "log":
        w = g("gain", 100.0) * np.log1p(c)
    else:
        raise ValueError(f"unknown weight map {kind!r} (linear, hill, log)")
    return np.clip(np.round(w), 1, int(w_clip)).astype(np.int32)


def _match(values: np.ndarray, wanted) -> np.ndarray:
    """values in a list of names; entries 're:<pattern>' are regular expressions (applied to the distinct values)."""
    wanted = [wanted] if isinstance(wanted, str) else list(wanted)
    plain = [w for w in wanted if not (isinstance(w, str) and w.startswith("re:"))]
    mask = np.isin(values, np.asarray(plain, dtype=str)) if plain else np.zeros(len(values), bool)
    pats = [re.compile(w[3:]) for w in wanted if isinstance(w, str) and w.startswith("re:")]
    if pats:
        uniq = np.unique(values)
        hit = uniq[[any(p.search(u) for p in pats) for u in uniq]]
        mask |= np.isin(values, hit)
    return mask


def import_connectome(ref, directory: Optional[Union[str, Path]] = None, filters: Optional[Dict[str, Any]] = None,
                      weight_map: Optional[Dict[str, Any]] = None, transmitter_signs: Optional[Dict[str, int]] = None,
                      profile=None, conduction_velocity: float = 1.0, w_clip: int = 512, chunk_rows: int = 1 << 16,
                      genome: Optional[Dict[str, Any]] = None, log: Callable[[str], None] = print
                      ) -> Tuple[Tissue, Dict[str, Any]]:
    """Imports the selected sub-circuit of a dataset (manifest id, path or dict) as a Tissue; see the module doc.
    `directory`: where the files are (default: the fetch cache for this dataset). Returns (tissue, info)."""
    m = load_manifest(ref)
    d = Path(directory) if directory is not None else data_dir() / m["id"]
    filters = dict(filters or {})
    nt, et = m["tables"]["neurons"], m["tables"]["edges"]
    ncols = dict(nt["columns"])
    for key in ("cell_type", "class", "superclass", "region", "side"):
        if key in filters and key not in ncols:
            raise DataError(f"filter {key!r} needs a {key!r} column in the manifest's neuron table")
    units = m.get("units", {})
    parts: Dict[str, List[np.ndarray]] = {k: [] for k in ncols}
    for b in read_batches(d / nt["file"], nt.get("format", "csv"), ncols, chunk_rows):
        keep = np.ones(len(b["id"]), bool)
        for key in ("cell_type", "class", "superclass", "region", "side"):
            if key in filters:
                keep &= _match(b[key], filters[key])
        if "ids" in filters:
            keep &= np.isin(b["id"], np.asarray(filters["ids"], np.int64))
        if all(k in b for k in "xyz"):
            xyz = transform_positions(np.stack([b["x"], b["y"], b["z"]], 1), units)
            b["x"], b["y"], b["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
            if "bbox" in filters:
                lo, hi = (np.asarray(v, np.float64) for v in filters["bbox"])
                keep &= np.all((xyz >= lo) & (xyz <= hi), axis=1)
        for k in parts:
            parts[k].append(b[k][keep])
    nd = {k: (np.concatenate(v) if v else np.zeros(0)) for k, v in parts.items()}
    ids = nd["id"].astype(np.int64)
    if len(np.unique(ids)) != len(ids):
        raise DataError("neuron ids are not unique in the selection")
    order = np.argsort(ids)
    sorted_ids = ids[order]
    N = len(ids)

    keys, counts = [], []
    ecols = dict(et["columns"])
    for b in read_batches(d / et["file"], et.get("format", "csv"), ecols, chunk_rows):
        pi = np.searchsorted(sorted_ids, b["pre"])
        qi = np.searchsorted(sorted_ids, b["post"])
        pi_c, qi_c = np.minimum(pi, max(N - 1, 0)), np.minimum(qi, max(N - 1, 0))
        if N == 0:
            ok = np.zeros(len(pi), bool)
        else:
            ok = (sorted_ids[pi_c] == b["pre"]) & (sorted_ids[qi_c] == b["post"])
        cnt = b["count"][ok] if "count" in b else np.ones(int(ok.sum()))
        keys.append(order[pi_c[ok]].astype(np.int64) * max(N, 1) + order[qi_c[ok]])
        counts.append(cnt)
    keys = np.concatenate(keys) if keys else np.zeros(0, np.int64)
    counts = np.concatenate(counts) if counts else np.zeros(0)
    uk, inv = np.unique(keys, return_inverse=True)
    total = np.bincount(inv, weights=counts, minlength=len(uk)) if len(uk) else np.zeros(0)
    sel = total >= float(filters.get("min_synapses", 1))
    uk, total = uk[sel], total[sel]
    pre, post = (uk // max(N, 1)).astype(np.int32), (uk % max(N, 1)).astype(np.int32)
    E = len(pre)
    log(f"import {m['id']}: {N:,} neurons, {E:,} synapses; network about {(N * 136 + E * 16) / 1e6:.1f} MB")

    t = Tissue.empty()
    types = nd.get("cell_type", np.full(N, "", dtype=str)).astype(str)
    type_names, type_idx = np.unique(types, return_inverse=True)
    regions = nd.get("region", np.full(N, "", dtype=str)).astype(str)
    region_names, region_idx = np.unique(regions, return_inverse=True)
    tx = nd.get("transmitter", np.full(N, "", dtype=str)).astype(str)
    signs = np.ones(N, np.int8)
    for name, sgn in (transmitter_signs or {}).items():
        signs[tx == name] = -1 if sgn < 0 else 1
    pos = np.stack([nd.get("x", np.zeros(N)), nd.get("y", np.zeros(N)), nd.get("z", np.zeros(N))], 1)
    bits = np.zeros(N, np.int8)
    if profile is not None:
        from ..pharmacology import load_profile
        prof = load_profile(profile)
        for name in prof.transmitters:
            bits[tx == name] |= np.int8(prof.bit(name))
    t.add_cells(N, positions=pos, cell_type=type_idx.astype(np.int32), region=region_idx.astype(np.int32), sign=signs,
                transmitter=bits)
    w = map_weights(total, weight_map, genome, w_clip) * np.where(signs[pre] < 0, -1, 1).astype(np.int32)
    dist = np.linalg.norm(pos[post] - pos[pre], axis=1) if E else np.zeros(0)
    delay = np.round(dist / float(conduction_velocity)).astype(np.int64)
    n_clip = int(np.sum(delay > MAX_DELAY))
    if n_clip:
        warnings.warn(f"import_connectome: {n_clip} synapses clipped to maximum delay {MAX_DELAY} ticks (kernel limit)",
                      UserWarning, stacklevel=2)
    t.connectivity = SparseConnectivity(pre, post, w.astype(np.int32), np.clip(delay, 1, MAX_DELAY).astype(np.int32))
    info = dict(dataset=m["id"], title=m.get("title", ""), license=m["license"], citation=m.get("citation", ""),
                source_ids=ids, type_names=type_names.tolist(), region_names=region_names.tolist(),
                synapse_counts=total, delays_clipped=n_clip, filters=filters)
    return t, info
