"""The examples run and do what they claim."""
import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def test_topographic_map_example(tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "topographic_map.py"), "--cpu", "--out", str(tmp_path)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.startswith("stimulus")]
    u0, u1 = (float(l.rsplit(" ", 1)[1]) for l in lines)
    assert u0 < 0.3 and u1 > 0.7                                           # the map is topographic
    assert (tmp_path / "network.json").exists() and (tmp_path / "module.json").exists()


def test_layered_sheet_example(tmp_path):
    import json
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "layered_sheet.py"), "--cpu", "--out", str(tmp_path)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "project.json").exists()
    assert (tmp_path / "network.json").exists()
    assert (tmp_path / "stats.json").exists()

    with open(tmp_path / "stats.json", "r", encoding="utf-8") as f:
        stats = json.load(f)

    # Validate cell types (excitatory across layers + superficial inhibitory interneurons)
    cells_per_type = stats["cells_per_type"]
    assert len(cells_per_type) == 4
    assert all(c > 0 for c in cells_per_type)
    assert stats["total_cells"] == sum(cells_per_type)

    # Validate both excitatory and inhibitory synapses exist
    assert stats["inhibitory_synapses"] > 0
    assert stats["excitatory_synapses"] > 0
    assert stats["inhibitory_synapses"] + stats["excitatory_synapses"] == stats["total_synapses"]

    # Validate layer-to-layer connection matrix
    conn_matrix = stats["connection_matrix"]
    assert len(conn_matrix) == 4 and all(len(row) == 4 for row in conn_matrix)
    assert stats["total_synapses"] > 0
    assert sum(sum(row) for row in conn_matrix) == stats["total_synapses"]

    # Validate delay distribution
    assert stats["delay_min"] >= 1
    assert stats["delay_max"] <= 31
    assert stats["delay_min"] <= stats["delay_mean"] <= stats["delay_max"]

    # Validate birth cycle predicts laminar depth (rank correlation >= 0.8)
    assert stats["birth_order_rank_corr"] >= 0.8


def test_layered_sheet_birth_order_predicts_layer_across_seeds(tmp_path):
    """Birth cycle consistently predicts laminar depth (inside-out, Spearman r >= 0.8) across 5 seeds."""
    from neurogenesis.stages.base import run_schedule
    sys.path.insert(0, str(ROOT))
    from examples.layered_sheet import build_project, _spearmanr

    proj = build_project()
    proj_dict = proj.to_dict()

    correlations = []
    for seed in [42, 101, 7, 1234, 999]:
        tissue = run_schedule(proj_dict, genome=proj.genome, seed=seed)
        corr, _ = _spearmanr(tissue.generation, tissue.positions[:, 2])
        correlations.append(corr)
        # Verify both excitatory and inhibitory synapses are formed in every seed
        assert np.sum(tissue.connectivity.weight < 0) > 0
        assert np.sum(tissue.connectivity.weight > 0) > 0

    assert all(c >= 0.8 for c in correlations)
    assert np.mean(correlations) >= 0.85




def _run_example(name, tmp_path, *args):
    import json
    r = subprocess.run([sys.executable, str(ROOT / "examples" / name), "--cpu", "--out", str(tmp_path), *args],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "project.json").exists() and (tmp_path / "network.json").exists()
    return json.loads((tmp_path / "stats.json").read_text())


def test_hand_built_network_example(tmp_path):
    """G2.4: a fully hand-built ring compiles, validates (Dale) and propagates activity in order."""
    stats = _run_example("hand_built_network.py", tmp_path)
    assert stats["neurons"] == 17 and stats["synapses"] > 12
    assert stats["propagates_in_order"]


def test_hand_drawn_column_example(tmp_path):
    """G2.1: cells per layer follow the hand-drawn thicknesses; genes set the inhibitory fraction of each layer."""
    stats = _run_example("hand_drawn_column.py", tmp_path)
    counts = np.asarray(stats["cells_per_layer"], float)
    np.testing.assert_allclose(counts / counts.sum(), [0.3, 0.3, 0.4], atol=0.06)
    f = stats["inhibitory_fraction"]
    assert f[0] < 0.15 and 0.2 < f[1] < 0.6 and f[2] > 0.7               # genes -3, 0, +1.5
    assert stats["genes"] == [["inhibitory_bias", "L0"], ["inhibitory_bias", "L1"], ["inhibitory_bias", "L2"]]


def test_hand_drawn_column_genes_change_fates():
    sys.path.insert(0, str(ROOT))
    from examples.hand_drawn_column import build_project, layer_stats
    from neurogenesis.stages.base import run_schedule
    p = build_project(inh_genes=(3.0, 3.0, -3.0))
    f = layer_stats(run_schedule(p.to_dict(), p.genome, 1))["inhibitory_fraction"]
    assert f[0] > 0.8 and f[1] > 0.8 and f[2] < 0.15


def test_pinwheel_sheet_example(tmp_path):
    """G2.2: density follows the hand-placed pinwheels and the map's pinwheels are recovered."""
    stats = _run_example("pinwheel_sheet.py", tmp_path)
    assert stats["density_ratio"] > 1.5
    assert sorted(stats["pinwheel_charges"]) == [-0.5, -0.5, 0.5, 0.5]
    found = np.asarray(stats["pinwheels_found"])
    centres = np.array([[3.0, 3.0], [7.0, 7.0], [3.0, 7.0], [7.0, 3.0]])
    assert np.all(np.min(np.linalg.norm(found[:, None] - centres[None], axis=-1), axis=0) < 0.2)


def test_evolved_development_example(tmp_path):
    """G2.3: a fully genetic schedule (genes collected automatically) improves under island evolution."""
    stats = _run_example("evolved_development.py", tmp_path)
    assert stats["final_best"] > stats["first_best"] + 0.3
    assert ["div"] in stats["genes"] and ["p0"] in stats["genes"] and ["div2"] in stats["genes"]
    assert stats["cells_type1"] > 0 and stats["synapses"] > 0


def test_retinothalamic_example(tmp_path):
    """Retina -> relay example: the four conditions develop (small tissue, 2 seeds) and every metric is finite."""
    import json
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "retinothalamic.py"), "--cpu", "--small", "--seeds", "2",
                        "--out", str(tmp_path)], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    stats = json.loads((tmp_path / "stats.json").read_text())
    assert (tmp_path / "project.json").exists()
    assert set(stats["summary"]) == {"WT", "b2KO", "TTX", "EphAKO"}
    for cond, rows in stats["per_seed"].items():
        assert len(rows) == 2
        for row in rows:
            assert all(np.isfinite(row[k]) for k in ("mosaic_nnri", "r_x", "r_y", "topo_error", "separation")), (cond, row)
            assert row["n_rgc"] > 10 and row["n_retinal_synapses"] > 0
    assert stats["summary"]["WT"]["r_x"][0] > 0.5 and abs(stats["summary"]["EphAKO"]["r_x"][0]) < 0.3


def test_retinothalamic_map_from_expression():
    """--map-source expression: the expression_gradient rule reads EphA / EphB (B = 0), so WT has a map and the EphA
    knockout (gene at 0 in every cell) loses its x axis; the default B projects are not affected."""
    sys.path.insert(0, str(ROOT))
    from examples.retinothalamic import build_project, run, summary
    from neurogenesis.stages.base import run_schedule
    p = build_project("EphAKO", 0, n_prog=45, n_relay=100, n_waves=1, wave_ticks=250, map_source="expression")
    t = run_schedule(p.to_dict(), p.genome, 0)
    assert t.expression_names == ["fate", "EphA", "EphB"] and not t.expression[:, 1].any()
    assert "expression_gradient" not in str(build_project("WT", 0).to_dict())
    s = summary(run(range(2), small=True, conditions=("WT", "EphAKO"), map_source="expression"))
    assert s["WT"]["r_x"][0] > 0.5 and s["WT"]["r_y"][0] > 0.5 and abs(s["EphAKO"]["r_x"][0]) < 0.3


def test_retinothalamic_waves_reach_the_stage():
    """The example's refinement stage honours its `waves` settings from a schedule (wave speed changes the weights)."""
    sys.path.insert(0, str(ROOT))
    from examples.retinothalamic import build_project
    from neurogenesis.stages.base import run_schedule
    sums = []
    for speed in (0.4, 100.0):
        p = build_project("WT", 0, n_prog=45, n_relay=100, n_waves=1, wave_ticks=250).to_dict()
        names = [s["name"] for s in p["schedule"]]
        p["schedule"] = p["schedule"][:names.index("refine_0") + 1]
        p["schedule"][-1]["params"]["waves"]["speed"] = speed
        sums.append(int(np.abs(run_schedule(p, p["genome"], 0).connectivity.weight).sum()))
    assert sums[0] != sums[1]


def test_retinothalamic_with_an_atlas_shaped_relay(tmp_path):
    """The relay can take its shape from an annotation atlas (synthetic here): cut a structure, fit it into the
    model's relay box, grow the example in it; every relay cell lies inside the atlas shape."""
    import json
    vol = np.zeros((30, 20, 16), np.uint16)
    i, j, k = np.meshgrid(np.arange(30), np.arange(20), np.arange(16), indexing="ij")
    vol[((i - 15) / 12.0) ** 2 + ((j - 10) / 7.0) ** 2 + ((k - 8) / 5.0) ** 2 <= 1] = 7      # toy nucleus
    np.savez(tmp_path / "atlas.npz", annotation=vol, origin=np.zeros(3), voxel_size=np.full(3, 20.0))
    (tmp_path / "onto.json").write_text(json.dumps({"msg": [{"id": 1, "acronym": "root", "children": [
        {"id": 7, "acronym": "TOY", "name": "toy nucleus", "children": []}]}]}))
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "atlas_relay_mask.py"), "--annotation",
                        str(tmp_path / "atlas.npz"), "--ontology", str(tmp_path / "onto.json"), "--structure", "TOY",
                        "--out", str(tmp_path / "mask.npz")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    sys.path.insert(0, str(ROOT))
    from examples.retinothalamic import RELAY, build_project, measure, volume_matched_box
    from neurogenesis.geometry.voxel import VoxelMaskGeometry
    from neurogenesis.stages.base import run_schedule
    mask = tmp_path / "mask.npz"
    p = build_project("WT", 0, n_prog=45, n_relay=100, n_waves=1, wave_ticks=250, relay_mask=mask)
    t = run_schedule(p.to_dict(), p.genome, 0)
    geom = VoxelMaskGeometry.from_npz(str(mask))
    assert np.all(geom.contains(t.positions[t.cell_type == RELAY]))
    m = measure(t, relay_mask=mask)
    assert m["n_retinal_synapses"] > 0 and m["r_x"] > 0.5 and m["r_y"] > 0.5
    assert np.isfinite(m["topo_error_feasible"])
    center, size = volume_matched_box(mask)
    assert np.isclose(np.prod(size), geom.mask.sum() * np.prod(geom.pitch), rtol=1e-6)
    box = dict(center=center.tolist(), size=size.tolist())
    bp = build_project("WT", 0, n_prog=45, n_relay=100, n_waves=1, wave_ticks=250, relay_box=box)
    bt = run_schedule(bp.to_dict(), bp.genome, 0)
    blo = center - size / 2
    assert np.all((bt.positions[bt.cell_type == RELAY] >= blo) &
                  (bt.positions[bt.cell_type == RELAY] <= blo + size))
    bm = measure(bt, relay_box=box)
    assert np.isfinite(bm["topo_error_feasible"])


def test_allen_annotation_unpack_and_manifest(tmp_path):
    """The P4 atlas manifest is valid, and the unpack script writes only annotation.mhd / .raw from a (toy) zip that
    neurogenesis.data.atlas then reads."""
    import zipfile
    from neurogenesis.data import load_manifest
    from neurogenesis.data.atlas import read_volume
    m = load_manifest(ROOT / "examples" / "datasets" / "allen-devmouse-p4.json")
    assert {f["name"] for f in m["files"]} == {"P4_DevMouse2012_annotation.zip", "structure_graph_17.json"}
    assert all(len(f["sha256"]) == 64 and f["size"] > 0 for f in m["files"])
    vol = np.arange(4 * 3 * 2, dtype="<u4").reshape(2, 3, 4)                   # file order: x fastest
    mhd = ("ObjectType = Image\nNDims = 3\nBinaryData = True\nBinaryDataByteOrderMSB = False\nCompressedData = False\n"
           "Offset = 0 0 0\nElementSpacing = 16 16 20\nDimSize = 4 3 2\nElementType = MET_UINT\n"
           "ElementDataFile = annotation.raw\n")
    with zipfile.ZipFile(tmp_path / "toy.zip", "w") as z:
        z.writestr("annotation.mhd", mhd)
        z.writestr("annotation.raw", vol.tobytes())
        z.writestr("../outside.txt", "not extracted")
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "allen_unpack_annotation.py"), str(tmp_path / "toy.zip"),
                        "--out", str(tmp_path / "out")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["annotation.mhd", "annotation.raw"]
    assert not (tmp_path / "outside.txt").exists()
    v, origin, spacing = read_volume(tmp_path / "out" / "annotation.mhd")
    assert v.size == 24 and set(np.unique(v)) == set(range(24)) and np.allclose(spacing, [16, 16, 20])
