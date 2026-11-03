"""Annotation atlases as geometries (part of roadmap J8): read a labelled volume and its structure ontology, and turn
one structure (with its descendants) into a `VoxelMaskGeometry` that stages can seed cells in.

    volume, origin, spacing = read_volume("annotation.nrrd")          # (X, Y, Z) labels; origin and voxel size
    onto = Ontology.load("structures.json")
    geom = structure_geometry(volume, onto, ["XYZ"], origin, spacing)  # cropped to the structure's bounding box

Volumes: NRRD (raw or gzip encoding, attached or detached data) and MetaImage (.mhd + raw data, optionally zlib
compressed), as atlases are usually distributed, or `.npz` with `annotation`, `origin`, `voxel_size`. Arrays are
returned with the first index along the file's fastest axis (x). Ontologies: a JSON tree whose nodes have `id`,
`acronym` and `children` (possibly wrapped as {"msg": [...]}), or a flat list with `parent_structure_id`. Nothing here
names an atlas or a species: dataset manifests and structure names live with the examples that use them.
"""
from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from ..geometry.voxel import VoxelMaskGeometry

_NRRD_TYPES = {"uchar": "u1", "unsigned char": "u1", "uint8": "u1", "uint8_t": "u1", "signed char": "i1", "int8": "i1",
               "short": "i2", "int16": "i2", "signed short": "i2", "ushort": "u2", "unsigned short": "u2",
               "uint16": "u2", "int": "i4", "int32": "i4", "signed int": "i4", "uint": "u4", "unsigned int": "u4",
               "uint32": "u4", "longlong": "i8", "int64": "i8", "ulonglong": "u8", "uint64": "u8",
               "float": "f4", "double": "f8"}
_MET_TYPES = {"MET_UCHAR": "u1", "MET_CHAR": "i1", "MET_USHORT": "u2", "MET_SHORT": "i2", "MET_UINT": "u4",
              "MET_INT": "i4", "MET_ULONG": "u8", "MET_LONG": "i8", "MET_FLOAT": "f4", "MET_DOUBLE": "f8"}


def _from_buffer(raw: bytes, dtype: np.dtype, sizes: Sequence[int]) -> np.ndarray:
    """Array (sizes[0], sizes[1], ...) from data whose first axis varies fastest (Fortran order)."""
    n = int(np.prod(sizes))
    a = np.frombuffer(raw, dtype=dtype, count=n)
    return a.reshape(tuple(sizes), order="F")


def _read_nrrd(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    with open(path, "rb") as f:
        magic = f.readline()
        if not magic.startswith(b"NRRD"):
            raise ValueError(f"{path}: not an NRRD file")
        header: Dict[str, str] = {}
        while True:
            line = f.readline()
            if not line or line in (b"\n", b"\r\n"):
                break
            text = line.decode("ascii", "replace").strip()
            if text.startswith("#") or ":" not in text:
                continue
            key, _, val = text.partition(":")
            header[key.strip().lower()] = val.lstrip("=").strip()
        data = f.read()
    sizes = [int(s) for s in header["sizes"].split()]
    endian = "<" if header.get("endian", "little") == "little" else ">"
    dtype = np.dtype(endian + _NRRD_TYPES[header["type"].lower()])
    if "data file" in header or "datafile" in header:
        data = (path.parent / (header.get("data file") or header["datafile"])).read_bytes()
    enc = header.get("encoding", "raw").lower()
    if enc in ("gzip", "gz"):
        data = gzip.decompress(data)
    elif enc != "raw":
        raise ValueError(f"{path}: NRRD encoding {enc!r} not supported (raw, gzip)")
    vol = _from_buffer(data, dtype, sizes)
    spacing = np.ones(len(sizes))
    if "space directions" in header:
        vecs = [v for v in header["space directions"].replace("(", " (").split() if v != "none"]
        dirs = [np.array([float(x) for x in v.strip("()").split(",")]) for v in vecs]
        spacing = np.array([np.linalg.norm(d) for d in dirs])
    elif "spacings" in header:
        spacing = np.array([float(x) for x in header["spacings"].split()])
    origin = np.zeros(len(sizes))
    if "space origin" in header:
        origin = np.array([float(x) for x in header["space origin"].strip("()").split(",")])
    return vol, origin, spacing


def _read_mhd(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    header: Dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            header[k.strip()] = v.strip()
    sizes = [int(s) for s in header["DimSize"].split()]
    endian = ">" if header.get("BinaryDataByteOrderMSB", header.get("ElementByteOrderMSB", "False")) == "True" else "<"
    dtype = np.dtype(endian + _MET_TYPES[header["ElementType"]])
    data = (path.parent / header["ElementDataFile"]).read_bytes()
    if header.get("CompressedData", "False") == "True":
        data = zlib.decompress(data)
    vol = _from_buffer(data, dtype, sizes)
    spacing = np.array([float(x) for x in header.get("ElementSpacing", " ".join(["1"] * len(sizes))).split()])
    origin = np.array([float(x) for x in header.get("Offset", header.get("Origin", " ".join(["0"] * len(sizes)))).split()])
    return vol, origin, spacing


def read_volume(path: Union[str, Path]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(labels (X, Y, Z), origin (3,), voxel size (3,)) of an annotation volume (.nrrd, .mhd or .npz)."""
    path = Path(path)
    if path.suffix == ".nrrd":
        return _read_nrrd(path)
    if path.suffix == ".mhd":
        return _read_mhd(path)
    if path.suffix == ".npz":
        with np.load(path) as z:
            return z["annotation"], z["origin"], z["voxel_size"]
    raise ValueError(f"{path}: unknown volume format (use .nrrd, .mhd or .npz)")


class Ontology:
    """A structure hierarchy: ids, acronyms and parents."""

    def __init__(self, parent: Dict[int, Optional[int]], acronym: Dict[int, str], name: Optional[Dict[int, str]] = None):
        self.parent = parent
        self.acronym = acronym
        self.name = name or {}
        self.by_acronym = {a: i for i, a in acronym.items()}
        self.children: Dict[int, List[int]] = {i: [] for i in parent}
        for i, p in parent.items():
            if p is not None and p in self.children:
                self.children[p].append(i)

    @classmethod
    def from_json(cls, data) -> "Ontology":
        if isinstance(data, dict) and "msg" in data:
            data = data["msg"]
        nodes = data if isinstance(data, list) else [data]
        parent, acronym, name = {}, {}, {}
        stack = [(n, None) for n in nodes]
        while stack:
            node, par = stack.pop()
            i = int(node["id"])
            p = node.get("parent_structure_id", par)
            parent[i] = int(p) if p is not None else None
            acronym[i] = str(node.get("acronym", i))
            name[i] = str(node.get("name", ""))
            stack.extend((c, i) for c in node.get("children", []) or [])
        return cls(parent, acronym, name)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Ontology":
        return cls.from_json(json.loads(Path(path).read_text()))

    def resolve(self, structure: Union[int, str]) -> int:
        if isinstance(structure, (int, np.integer)):
            return int(structure)
        if structure not in self.by_acronym:
            raise KeyError(f"no structure with acronym {structure!r}")
        return self.by_acronym[structure]

    def descendants(self, structure: Union[int, str]) -> List[int]:
        """The structure's id and the ids of every structure below it."""
        out, stack = [], [self.resolve(structure)]
        while stack:
            i = stack.pop()
            out.append(i)
            stack.extend(self.children.get(i, []))
        return out


def structure_geometry(volume: np.ndarray, ontology: Optional[Ontology], structures: Iterable[Union[int, str]],
                       origin: Sequence[float], spacing: Sequence[float], include_descendants: bool = True,
                       crop: bool = True) -> VoxelMaskGeometry:
    """Voxel geometry of the voxels labelled with the given structures (and, by default, their descendants), cropped
    to their bounding box. Positions are in the volume's physical units (origin + index x voxel size). Raises if no
    voxel carries those labels."""
    ids: List[int] = []
    for s in structures:
        if ontology is None:
            ids.append(int(s))
        else:
            ids.extend(ontology.descendants(s) if include_descendants else [ontology.resolve(s)])
    mask = np.isin(volume, np.asarray(sorted(set(ids)), dtype=volume.dtype))
    if not mask.any():
        raise ValueError(f"no voxel is labelled with {list(structures)} (ids {sorted(set(ids))[:10]}...)")
    origin = np.asarray(origin, dtype=np.float64)[:3]
    spacing = np.asarray(spacing, dtype=np.float64)[:3]
    if crop:
        nz = np.nonzero(mask)
        lo = np.array([a.min() for a in nz])
        hi = np.array([a.max() for a in nz]) + 1
        mask = mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
        origin = origin + lo * spacing
    return VoxelMaskGeometry(mask, origin, spacing)


def fit_to_box(geometry: VoxelMaskGeometry, center: Sequence[float], extent: float) -> VoxelMaskGeometry:
    """The same shape, scaled uniformly so that its largest bounding-box side is `extent` and centred on `center`
    (to place an atlas shape in a model's own space units while keeping its proportions)."""
    lo, hi = geometry.bounding_box()
    size = np.asarray(hi, float) - np.asarray(lo, float)
    s = float(extent) / float(size.max())
    pitch = np.asarray(geometry.pitch, float) * s
    origin = np.asarray(center, float) - size * s / 2
    return VoxelMaskGeometry(geometry.mask, origin, pitch)
