"""Atlas volumes and ontologies as geometries (J8 part): NRRD / MetaImage readers, descendants, structure masks."""
import gzip
import json
import zlib

import numpy as np
import pytest

from neurogenesis.data.atlas import Ontology, fit_to_box, read_volume, structure_geometry

TREE = {"msg": [{"id": 1, "acronym": "root", "children": [
    {"id": 10, "acronym": "A", "children": [{"id": 11, "acronym": "A1", "children": []},
                                            {"id": 12, "acronym": "A2", "children": []}]},
    {"id": 20, "acronym": "B", "children": []}]}]}


def _volume():
    v = np.zeros((6, 5, 4), np.uint16)
    v[1:3, 1:3, 1:2] = 11            # A1
    v[3, 3, 2] = 12                  # A2
    v[5, 4, 3] = 20                  # B
    return v


def _write_nrrd(path, vol, encoding="raw", detached=False):
    raw = vol.tobytes(order="F")
    payload = gzip.compress(raw) if encoding == "gzip" else raw
    head = ["NRRD0004", "type: uint16", "dimension: 3", f"sizes: {' '.join(map(str, vol.shape))}", "endian: little",
            f"encoding: {encoding}", "space: left-posterior-superior",
            "space directions: (25,0,0) (0,25,0) (0,0,25)", "space origin: (100,200,300)"]
    if detached:
        (path.parent / "data.raw").write_bytes(payload)
        head.append("data file: data.raw")
    path.write_bytes(("\n".join(head) + "\n\n").encode() + (b"" if detached else payload))


@pytest.mark.parametrize("encoding,detached", [("raw", False), ("gzip", False), ("raw", True)])
def test_read_nrrd(tmp_path, encoding, detached):
    vol = _volume()
    _write_nrrd(tmp_path / "a.nrrd", vol, encoding, detached)
    v, origin, spacing = read_volume(tmp_path / "a.nrrd")
    np.testing.assert_array_equal(v, vol)
    np.testing.assert_allclose(origin, [100, 200, 300])
    np.testing.assert_allclose(spacing, [25, 25, 25])


@pytest.mark.parametrize("compressed", [False, True])
def test_read_mhd(tmp_path, compressed):
    vol = _volume()
    raw = vol.tobytes(order="F")
    (tmp_path / "a.raw").write_bytes(zlib.compress(raw) if compressed else raw)
    (tmp_path / "a.mhd").write_text(
        "ObjectType = Image\nNDims = 3\nDimSize = 6 5 4\nElementType = MET_USHORT\nElementSpacing = 20 20 20\n"
        f"Offset = 0 0 0\nCompressedData = {compressed}\nBinaryDataByteOrderMSB = False\nElementDataFile = a.raw\n")
    v, origin, spacing = read_volume(tmp_path / "a.mhd")
    np.testing.assert_array_equal(v, vol)
    np.testing.assert_allclose(spacing, [20, 20, 20])


def test_ontology_tree_and_flat_list():
    onto = Ontology.from_json(TREE)
    assert sorted(onto.descendants("A")) == [10, 11, 12] and onto.descendants(20) == [20]
    flat = [{"id": 1, "acronym": "root", "parent_structure_id": None},
            {"id": 10, "acronym": "A", "parent_structure_id": 1}, {"id": 11, "acronym": "A1", "parent_structure_id": 10}]
    assert sorted(Ontology.from_json(flat).descendants("root")) == [1, 10, 11]
    with pytest.raises(KeyError):
        onto.resolve("nope")


def test_structure_geometry_includes_descendants_and_crops(tmp_path):
    vol = _volume()
    onto = Ontology.from_json(TREE)
    g = structure_geometry(vol, onto, ["A"], origin=[100, 200, 300], spacing=[25, 25, 25])
    assert g.mask.shape == (3, 3, 2) and g.mask.sum() == 5                     # 4 voxels of A1 + 1 of A2
    np.testing.assert_allclose(g.origin, [125, 225, 325])
    p = g.sample_points(200, np.random.default_rng(0))
    assert np.all(g.contains(p))
    with pytest.raises(ValueError, match="no voxel"):
        structure_geometry(vol, onto, ["A"], [0, 0, 0], [1, 1, 1], include_descendants=False)   # id 10 itself unused
    fitted = fit_to_box(g, center=[0, 0, 0], extent=60.0)
    lo, hi = fitted.bounding_box()
    assert float(np.max(np.asarray(hi) - np.asarray(lo))) == pytest.approx(60.0)
    np.testing.assert_allclose((np.asarray(hi) + np.asarray(lo)) / 2, 0, atol=1e-4)
    path = tmp_path / "g.npz"
    fitted.save_npz(path)
    from neurogenesis.geometry.voxel import VoxelMaskGeometry
    assert VoxelMaskGeometry.from_npz(str(path)).mask.sum() == 5
