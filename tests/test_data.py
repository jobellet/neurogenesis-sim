"""I1 manifests and downloads, I2 streaming import, I3 coordinates, I4 weight mapping. Synthetic fixtures only: the
downloader is tested against a local HTTP server, never the network."""
import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading
import warnings

import numpy as np
import pytest

from neurogenesis.data import DataError, fetch, import_connectome, load_manifest, map_weights, transform_positions
from neurogenesis.data.importer import _has_pyarrow, read_batches

NEURONS = """root_id,pos_x,pos_y,pos_z,type,class,region,side,nt
101,0,0,0,A1,local,R1,left,glutamate
102,100,0,0,A2,local,R1,right,glutamate
103,0,100,0,B1,projection,R2,left,gaba
104,0,0,100,B2,projection,R2,right,acetylcholine
105,5000,0,0,C,other,R3,left,gaba
"""
EDGES = """pre_root_id,post_root_id,neuropil,syn_count
101,102,N1,4
101,102,N2,3
102,103,N1,2
103,101,N1,10
104,101,N1,1
105,101,N1,50
101,999,N1,8
"""


def _manifest(tmp_path, url="http://127.0.0.1:1/"):
    files = []
    for name, text in (("neurons.csv", NEURONS), ("edges.csv", EDGES)):
        (tmp_path / name).write_bytes(text.encode("utf-8"))
        files.append({"name": name, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "size": len(text.encode("utf-8"))})
    m = {"id": "toy", "title": "toy connectome", "license": "CC-BY-4.0", "citation": "Test et al. 2026", "url": url,
         "files": files,
         "tables": {"neurons": {"file": "neurons.csv", "format": "csv", "columns": {
             "id": "root_id", "x": "pos_x", "y": "pos_y", "z": "pos_z", "cell_type": "type", "class": "class",
             "region": "region", "side": "side", "transmitter": "nt"}},
             "edges": {"file": "edges.csv", "format": "csv", "columns": {"pre": "pre_root_id", "post": "post_root_id",
                                                                         "count": "syn_count"}}},
         "units": {"voxel_size": [0.1, 0.1, 0.1], "origin": [1.0, 0.0, 0.0], "mirror": [], "unit": "um"}}
    (tmp_path / "toy.json").write_bytes(json.dumps(m).encode("utf-8"))
    return m


# I1 ---------------------------------------------------------------------------------------------------------------
class _RangeHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.translate_path(self.path)
        data = open(path, "rb").read()
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            data = data[start:]
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server(tmp_path, monkeypatch):
    for var in ("no_proxy", "NO_PROXY"):                                   # never send localhost through a proxy
        monkeypatch.setenv(var, "127.0.0.1,localhost")
    src = tmp_path / "srv"
    src.mkdir()
    handler = lambda *a, **k: _RangeHandler(*a, directory=str(src), **k)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    yield src, f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


def test_manifest_validation(tmp_path):
    m = _manifest(tmp_path)
    assert load_manifest(tmp_path / "toy.json")["id"] == "toy"
    bad = dict(m, files=[{"name": "x"}])
    with pytest.raises(DataError, match="sha256"):
        load_manifest(bad)
    with pytest.raises(DataError, match="no manifest"):
        load_manifest("nonexistent_dataset")


def test_fetch_verifies_resumes_and_keeps_good_files(tmp_path, server):
    src, url = server
    m = _manifest(src, url)
    target = tmp_path / "cache"
    part = target / "toy" / "edges.csv.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(EDGES[:20].encode("utf-8"))                                             # an interrupted download
    logs = []
    d = fetch(m, target=target, log=logs.append)
    assert (d / "edges.csv").read_bytes().decode("utf-8") == EDGES and (d / "neurons.csv").read_bytes().decode("utf-8") == NEURONS
    assert "CC-BY-4.0" in logs[0]
    logs.clear()
    fetch(m, target=target, log=logs.append)
    assert sum("present, checksum ok" in l for l in logs) == 2              # nothing downloaded twice
    bad = json.loads(json.dumps(m))
    bad["files"][0]["sha256"] = "0" * 64
    (target / "toy" / "neurons.csv").unlink()
    with pytest.raises(DataError, match="checksum"):
        fetch(bad, target=target, log=lambda s: None)
    with pytest.raises(DataError, match="cancelled"):
        fetch(m, target=tmp_path / "other", confirm=lambda s: False, log=lambda s: None)


def test_cli_data_info_and_fetch(tmp_path, server):
    src, url = server
    _manifest(src, url)
    env = {**os.environ, "NEUROGENESIS_DATA": str(tmp_path / "cache"), "JAX_PLATFORMS": "cpu", "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "data", "info", str(src / "toy.json")],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "license: CC-BY-4.0" in r.stdout
    r = subprocess.run([sys.executable, "-m", "neurogenesis", "data", "fetch", str(src / "toy.json"), "--yes"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "cache" / "toy" / "edges.csv").read_bytes().decode("utf-8") == EDGES


# I2 ---------------------------------------------------------------------------------------------------------------
def test_read_batches_streams_in_chunks(tmp_path):
    _manifest(tmp_path)
    batches = list(read_batches(tmp_path / "edges.csv", "csv", {"pre": "pre_root_id", "count": "syn_count"}, chunk_rows=3))
    assert [len(b["pre"]) for b in batches] == [3, 3, 1]
    assert batches[0]["pre"].dtype == np.int64 and batches[-1]["count"].tolist() == [8.0]


def test_import_filters_aggregates_and_records_provenance(tmp_path):
    _manifest(tmp_path)
    t, info = import_connectome(tmp_path / "toy.json", directory=tmp_path, chunk_rows=2, log=lambda s: None,
                                filters={"cell_type": ["A1", "re:^B"], "side": ["left"]})
    assert info["source_ids"].tolist() == [101, 103] and info["type_names"] == ["A1", "B1"]
    assert info["license"] == "CC-BY-4.0" and info["citation"] == "Test et al. 2026"
    c = t.connectivity
    assert list(zip(c.pre, c.post)) == [(1, 0)] and info["synapse_counts"].tolist() == [10.0]
    t, info = import_connectome(tmp_path / "toy.json", directory=tmp_path, log=lambda s: None,
                                filters={"region": ["R1", "R2"]})
    pairs = dict(zip(zip(info["source_ids"][t.connectivity.pre].tolist(), info["source_ids"][t.connectivity.post].tolist()),
                     info["synapse_counts"].tolist()))
    assert pairs == {(101, 102): 7.0, (102, 103): 2.0, (103, 101): 10.0, (104, 101): 1.0}   # neuropils summed
    t, info = import_connectome(tmp_path / "toy.json", directory=tmp_path, log=lambda s: None,
                                filters={"region": ["R1", "R2"], "min_synapses": 3})
    assert len(t.connectivity.pre) == 2
    with pytest.raises(DataError, match="superclass"):
        import_connectome(tmp_path / "toy.json", directory=tmp_path, filters={"superclass": ["x"]}, log=lambda s: None)


def test_parquet_needs_pyarrow_or_reads_it(tmp_path):
    _manifest(tmp_path)
    if _has_pyarrow():
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.table({"pre_root_id": [1, 2], "syn_count": [3, 4]}), tmp_path / "e.parquet")
        b = list(read_batches(tmp_path / "e.parquet", "parquet", {"pre": "pre_root_id", "count": "syn_count"}))
        assert b[0]["pre"].tolist() == [1, 2]
    else:
        (tmp_path / "e.parquet").write_bytes(b"")
        with pytest.raises(DataError, match="pyarrow"):
            list(read_batches(tmp_path / "e.parquet", "parquet", {"pre": "pre_root_id"}))


# I3 ---------------------------------------------------------------------------------------------------------------
def test_coordinates_bbox_and_delay_clipping(tmp_path):
    _manifest(tmp_path)
    np.testing.assert_allclose(transform_positions(np.array([[10.0, 20, 30]]), {"voxel_size": [0.1, 0.1, 0.1],
                                                                                "origin": [1, 0, 0], "mirror": [0]}),
                               [[-2.0, 2.0, 3.0]])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        t, info = import_connectome(tmp_path / "toy.json", directory=tmp_path, conduction_velocity=1.0, log=lambda s: None)
    np.testing.assert_allclose(t.positions[info["source_ids"].tolist().index(102)], [11.0, 0, 0])
    d = dict(zip(zip(info["source_ids"][t.connectivity.pre].tolist(), info["source_ids"][t.connectivity.post].tolist()),
                 t.connectivity.delay.tolist()))
    assert d[(101, 102)] == 10 and d[(105, 101)] == 31 and info["delays_clipped"] == 1
    assert any("clipped" in str(x.message) for x in w)
    t, info = import_connectome(tmp_path / "toy.json", directory=tmp_path, log=lambda s: None,
                                filters={"bbox": [[0, -1, -1], [20, 20, 20]]})
    assert 105 not in info["source_ids"].tolist()


# I4 ---------------------------------------------------------------------------------------------------------------
def test_weight_maps_and_transmitter_signs(tmp_path):
    c = np.array([1, 10, 100, 1000])
    assert map_weights(c, {"kind": "linear", "gain": 2.0}).tolist() == [2, 20, 200, 512]
    assert map_weights(c, {"kind": "hill", "w_max": 1000, "k": 10, "n": 1}, w_clip=2047).tolist() == [91, 500, 909, 990]
    assert map_weights(c, {"kind": "log", "gain": 10}).tolist() == [7, 24, 46, 69]
    assert map_weights(c, {"kind": "linear", "gain": {"type": "Gene", "path": ["g"], "lo": 0, "hi": 5}}, {"g": 3.0}).tolist() == [3, 30, 300, 512]
    with pytest.raises(ValueError, match="w_clip"):
        map_weights(c, None, w_clip=100)
    _manifest(tmp_path)
    profile = {"id": "p", "transmitters": ["glutamate", "gaba", "acetylcholine"], "receptors": [{"name": "classic"}]}
    t, info = import_connectome(tmp_path / "toy.json", directory=tmp_path, log=lambda s: None,
                                weight_map={"kind": "linear", "gain": 10}, transmitter_signs={"gaba": -1},
                                profile=profile, filters={"region": ["R1", "R2"]})
    ids = info["source_ids"].tolist()
    w = dict(zip(zip([ids[i] for i in t.connectivity.pre], [ids[i] for i in t.connectivity.post]), t.connectivity.weight.tolist()))
    assert w == {(101, 102): 70, (102, 103): 20, (103, 101): -100, (104, 101): 10}
    assert t.transmitter.tolist() == [1, 1, 2, 4]
    from neurogenesis.stages.freeze import freeze
    assert freeze(t, dale=True).num_synapses == 4


# Track 3: Catalogue Cards & CLI Share Pipeline ----------------------------------------------------
def _dummy_card():
    project = {
        "version": "1.2.0",
        "geometry": {"box": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}},
        "fields": {},
        "schedule": [{"name": "seed", "operator": "seed_cells", "params": {"N": 20, "geometry": "box"}}],
        "genome": {"drug_dose": 1.0, "drugs": {"dose": 1.0}},
        "plugins": [],
        "metadata": {"name": "test-microcircuit"},
    }
    return {
        "format": "neurogenesis-card/1",
        "id": "test-microcircuit",
        "version": "1.0.0",
        "project": project,
        "genome": {"drug_dose": 1.0, "drugs": {"dose": 1.0}},
        "targets": [{"metric": "cell_count", "value": 20.0}],
        "compute_cost": {"memory_bytes": 1024, "ops_per_tick": 200.0, "verdict": "fits"},
        "provenance": {
            "authors": [{"name": "Alice Scientist", "orcid": "0000-0002-1825-0097"}],
            "doi": "10.1101/2026.01.01.123456",
        },
        "validation": {"seeds": [1000, 1001, 1002], "scores": [{"cell_count": 20.0}] * 3},
    }


def test_card_validation_and_rejection():
    from neurogenesis.data.catalogue import CARD_FORMAT, CardError, validate_card

    card = _dummy_card()
    validate_card(card)  # must pass

    # Bad format
    bad = dict(card, format="invalid-card/1")
    with pytest.raises(CardError, match="Card format"):
        validate_card(bad)

    # Missing required field
    bad = dict(card)
    del bad["compute_cost"]
    with pytest.raises(CardError, match="missing required field"):
        validate_card(bad)

    # Bad ORCID
    bad = json.loads(json.dumps(card))
    bad["provenance"]["authors"][0]["orcid"] = "invalid-orcid"
    with pytest.raises(CardError, match="ORCID"):
        validate_card(bad)

    # Bad DOI
    bad = json.loads(json.dumps(card))
    bad["provenance"]["doi"] = "invalid-doi"
    with pytest.raises(CardError, match="DOI"):
        validate_card(bad)

    # Non-positive compute cost
    bad = json.loads(json.dumps(card))
    bad["compute_cost"]["memory_bytes"] = -1
    with pytest.raises(CardError, match="memory_bytes"):
        validate_card(bad)


def test_card_save_load_pull(tmp_path):
    from neurogenesis.data.catalogue import load_card, pull, save_card

    card = _dummy_card()
    path = tmp_path / "card.json"
    save_card(card, path)
    assert path.exists()

    loaded = load_card(path)
    assert loaded["id"] == card["id"]

    proj = pull(path)
    assert proj.version == "1.2.0"
    assert proj.metadata.get("card") == "test-microcircuit"
    # Remix loop: pharmacological perturbation
    assert "drugs" in proj.genome
    proj.genome["drugs"]["dose"] = 3.5
    assert proj.genome["drugs"]["dose"] == 3.5


def test_cli_share_command(tmp_path):
    from neurogenesis.project.io import Project

    p = Project(
        geometry={"box": {"type": "Box", "center": [0.5, 0.5, 0.5], "size": [1.0, 1.0, 1.0]}},
        schedule=[{"name": "seed", "operator": "seed_cells", "params": {"N": 20, "geometry": "box"}}],
        genome={"drug_dose": 1.0, "drugs": {"dose": 1.0}},
    )
    p_file = tmp_path / "project.json"
    p.save(p_file)
    out_card = tmp_path / "shared.card.json"

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "JAX_PLATFORMS": "cpu"}
    cmd = [
        sys.executable, "-m", "neurogenesis", "share",
        "--project", str(p_file),
        "--author", "Test Researcher",
        "--orcid", "0000-0002-1825-0097",
        "--doi", "10.1101/2026.01.01.123456",
        "--name", "test-shared-card",
        "--out", str(out_card),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert out_card.exists()

    card_data = json.loads(out_card.read_text(encoding="utf-8"))
    assert card_data["format"] == "neurogenesis-card/1"
    assert card_data["id"] == "test-shared-card"
    assert card_data["compute_cost"]["memory_bytes"] > 0
    assert card_data["validation"]["seeds"] == [1000, 1001, 1002]

    # Test rejection with invalid ORCID
    bad_cmd = list(cmd)
    bad_cmd[cmd.index("--orcid") + 1] = "bad-orcid"
    r_bad = subprocess.run(bad_cmd, capture_output=True, text=True, env=env)
    assert r_bad.returncode != 0
    assert "Invalid ORCID" in r_bad.stderr
