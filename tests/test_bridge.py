"""The bridge (neurogenesis.bridge): every command of the protocol (desktop/common/PROTOCOL.md), the NGB1 format, the
resource refusals, and one round trip through a real server process."""
import io
import json
import subprocess
import sys

import numpy as np
import pytest

from neurogenesis.bridge import METHODS, NGB_VERSION, PROTOCOL_VERSION, read_network, server, write_network
from neurogenesis.development import BodyPlan, FixedPlacement, Region
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.stages import register_stage


@register_stage("bridge_toy_seed")
class BridgeToySeed:
    """Toy stage for the bridge test: adds `count` cells at random positions."""
    def run(self, tissue, params, genome, fields, rng):
        c = params.get("count")
        tissue.add_cells(int(getattr(c, "value", c or 4)), positions=rng.random((int(getattr(c, "value", c or 4)), 3)))
        return tissue


def call(method, params=None):
    """Runs one request through the dispatcher; returns the reply message."""
    out = io.StringIO()
    old, server._OUT = server._OUT, out
    try:
        server.handle({"id": 1, "method": method, "params": params or {}})
    finally:
        server._OUT = old
    msgs = [json.loads(l) for l in out.getvalue().splitlines()]
    return [m for m in msgs if m.get("id") == 1][-1]


def ok(method, params=None):
    r = call(method, params)
    assert "error" not in r, r
    return r["result"]


def plan_dict():
    sheet = [[(i + 0.5) / 3, (j + 0.5) / 3, 0.5] for i in range(3) for j in range(3)]
    return BodyPlan("toy", [Region("sheet", (0, 0, 0), (10, 10, 2), FixedPlacement(sheet), role=1),
                            Region("map", (20, 0, 0), (10, 10, 10))], [("sheet", "map"), ("map", "map")]).to_dict()


@pytest.fixture(scope="module")
def genome():
    return ok("plan_defaults", {"plan": plan_dict(), "genome": {"count": {"map": 20}}})["genome"]


@pytest.fixture(scope="module")
def ngb(tmp_path_factory):
    path = tmp_path_factory.mktemp("ngb") / "net.ngb"
    write_network(MorphogeneticEngine.generate_cortical_column(60, seed=1, weight_scale=0.2, refractory=3), path)
    return str(path)


TESTED = set()


@pytest.fixture(autouse=True)
def _track(request):
    yield
    TESTED.update(getattr(request.function, "methods", ()))


def covers(*methods):
    def deco(fn):
        fn.methods = methods
        return fn
    return deco


@covers("ping", "capabilities")
def test_ping_and_capabilities():
    assert ok("ping") == "pong"
    c = ok("capabilities")
    assert c["protocol"] == PROTOCOL_VERSION and c["ngb"] == NGB_VERSION
    tasks = {t["task"]: t["available"] for t in c["tasks"]}
    assert tasks["A1"] and tasks["A4"] and "C4" in tasks
    assert tasks["A5"] and tasks["D2"] and tasks["F7"]


@covers()
def test_ngb_round_trip_keeps_every_field(tmp_path):
    net = MorphogeneticEngine.generate_cortical_column(50, seed=6)
    write_network(net, tmp_path / "n.ngb")
    back = read_network(tmp_path / "n.ngb")
    assert [vars(n) for n in back.neurons] == [vars(n) for n in net.neurons]
    assert [vars(s) for s in back.synapses] == [vars(s) for s in net.synapses]
    (tmp_path / "bad.ngb").write_bytes(b"NGB1" + bytes(20))
    with pytest.raises(ValueError):
        read_network(tmp_path / "bad.ngb")


@covers()
def test_ngb_extension_columns_are_optional_and_skipped(tmp_path):
    from neurogenesis.bridge import read_extensions
    net = MorphogeneticEngine.generate_cortical_column(40, seed=2)
    receptor = np.arange(net.num_synapses, dtype=np.uint8) % 3
    nodes = np.arange(2 * net.num_synapses, dtype=np.int32).reshape(-1, 2)
    write_network(net, tmp_path / "x.ngb", extensions={"receptor": ("synapse", receptor), "nodes": ("synapse", nodes),
                                                       "layer": ("neuron", np.ones(40, np.float32))})
    back = read_network(tmp_path / "x.ngb")
    assert [vars(s) for s in back.synapses] == [vars(s) for s in net.synapses]
    ext = read_extensions(tmp_path / "x.ngb")
    assert (ext["receptor"][1] == receptor).all() and (ext["nodes"][1] == nodes).all() and ext["layer"][0] == "neuron"
    raw = bytearray((tmp_path / "x.ngb").read_bytes())
    raw[12] |= 2                                            # a reserved flag bit: refused, not misread
    (tmp_path / "y.ngb").write_bytes(bytes(raw))
    with pytest.raises(ValueError):
        read_network(tmp_path / "y.ngb")
    write_network(net, tmp_path / "plain.ngb")
    assert read_extensions(tmp_path / "plain.ngb") == {}


@covers("generate", "load_network", "save_network", "wire", "stats")
def test_network_sources(ngb, tmp_path):
    for kind in ("column", "layered", "microcircuit"):
        assert ok("generate", {"morphology": kind, "neurons": 40})["neurons"] == 40
    out = str(tmp_path / "n.json")
    ok("save_network", {"ngb": ngb, "path": out})
    assert ok("load_network", {"path": out})["neurons"] == 60
    assert ok("wire", {"ngb": ngb, "seed": 1})["neurons"] == 60
    assert "num_neurons" in json.dumps(ok("stats", {"ngb": ngb})) or ok("stats", {"ngb": ngb})


@covers("plan_defaults", "grow", "grow_steps", "plan_save", "plan_load", "rules", "estimate_grow", "resources", "genes")
def test_plans_and_growth(genome, tmp_path):
    g = ok("grow", {"plan": plan_dict(), "genome": genome, "seed": 3})
    assert g["neurons"] == 9 + 20 and g["regions"] == ["sheet", "map"]
    assert ok("grow", {"plan": plan_dict(), "genome": genome, "seed": 3}) | {"path": ""} == g | {"path": ""}
    steps = ok("grow_steps", {"plan": plan_dict(), "genome": genome, "seed": 3})["steps"]
    assert len(steps) == 3 and steps[0]["synapses"] == 0 and steps[-1]["synapses"] == g["synapses"]
    ok("plan_save", {"plan": plan_dict(), "path": str(tmp_path / "p.json")})
    assert ok("plan_load", {"path": str(tmp_path / "p.json")})["plan"]["name"] == "toy"
    assert "placement" in ok("rules")
    est = ok("estimate_grow", {"plan": plan_dict(), "genome": genome})
    assert est["neurons"] == 29 and est["fits"]
    assert ok("resources")["available"] > 0
    paths = [tuple(x["path"]) for x in ok("genes", {"genome": genome})["genes"]]
    assert ("count", "map") in paths and ("guidance", "sheet->map", "sigma") in paths


@covers("project_new", "project_save", "project_load", "project_validate")
def test_projects(tmp_path):
    p = ok("project_new")["project"]
    p["metadata"] = {"note": "bridge test"}
    ok("project_save", {"project": p, "path": str(tmp_path / "proj.json")})
    assert ok("project_load", {"path": str(tmp_path / "proj.json")})["project"]["metadata"] == {"note": "bridge test"}
    assert ok("project_validate", {"project": p})["ok"]
    assert not ok("project_validate", {"project": {"version": "1.0.0"}})["ok"]


@covers("geometry_types", "geometry_preview", "geometry_cells")
def test_geometry():
    types = {t["type"] for t in ok("geometry_types")["types"]}
    assert {"Box", "Sphere"} <= types
    sphere = {"type": "Sphere", "center": [0, 0, 0], "radius": 5}
    pts = np.asarray(ok("geometry_preview", {"geometry": sphere, "n": 50})["points"])
    assert pts.shape == (50, 3) and (np.linalg.norm(pts, axis=1) <= 5.001).all()
    assert ok("geometry_cells", {"geometry": sphere, "n": 30})["neurons"] == 30
    empty = {"type": "Difference", "a": sphere, "b": {"type": "Box", "center": [0, 0, 0], "size": [20, 20, 20]}}
    r = call("geometry_preview", {"geometry": empty, "n": 5})
    assert "error" in r


@covers("stages", "run_schedule", "schedule_info", "ui_schema")
def test_stages_and_schedules():
    st = ok("stages")
    assert st["available"] and any(s["name"] == "bridge_toy_seed" and s["available"] for s in st["stages"])
    project = {"schedule": [{"name": "seed", "operator": "bridge_toy_seed", "params": {"count": {"type": "Const", "value": 7}}, "repeat": 2}]}
    r = ok("run_schedule", {"project": project, "seed": 0})
    assert [s["neurons"] for s in r["steps"]] == [7, 14]
    info = ok("schedule_info", {"project": {"schedule": [{"operator": "bridge_toy_seed", "params": {
        "count": {"type": "Gene", "path": ["count", "map"], "lo": 1, "hi": 50, "integer": True}}}]}})
    assert info["gene_list"][0]["path"] == ["count", "map"]
    assert "error" in call("run_schedule", {"project": {"schedule": [{"operator": "not_a_stage"}]}})

    schema = ok("ui_schema", {"project": project})
    assert "format" in schema
    assert schema["format"] == "neurogenesis-ui-schema"


@covers("models", "simulate", "estimate", "fi_curve", "regularity")
def test_simulation_and_analysis(ngb):
    assert {"lif_int", "two_compartment", "hh"} <= {m["name"] for m in ok("models")["models"]}
    r = ok("simulate", {"ngb": ngb, "model": "lif_int", "ticks": 100, "ext": {"0": 40}})
    assert len(r["t"]) == len(r["i"]) > 0
    assert len(ok("estimate", {"neurons": 1000, "synapses": 10000})["estimates"]) >= 3
    fi = ok("fi_curve", {"hi": 20, "step": 10, "ticks": 200})
    assert fi["rate_hz"][0] == 0 and fi["rate_hz"][-1] > 0
    assert ok("regularity", {"ngb": ngb})["cells"] == 60


@covers("plasticity_rules", "plasticity")
def test_plasticity(ngb):
    rules = {r["name"] for r in ok("plasticity_rules")["rules"]}
    assert "STDPRule" in rules
    r = ok("plasticity", {"ngb": ngb, "rule": "STDPRule", "ticks": 20, "t": [1, 3, 5], "i": [0, 1, 2]})
    assert len(r["weights"]) == read_network(ngb).num_synapses


@covers("evolve")
def test_evolve(genome):
    genes = [{"path": ["guidance", "sheet->map", "w"], "lo": 20, "hi": 400}]
    r = ok("evolve", {"plan": plan_dict(), "genome": genome, "genes": genes, "gens": 1, "pop": 2, "seeds": 1, "ticks": 30})
    assert len(r["history"]) == 1 and "guidance" in r["genome"]


@covers("module_save", "module_load", "module_compose")
def test_modules(genome, tmp_path):
    ok("module_save", {"name": "toy", "plan": plan_dict(), "genome": genome, "inputs": ["sheet"], "outputs": ["map"],
                       "path": str(tmp_path / "toy.module.json")})
    m = ok("module_load", {"path": str(tmp_path / "toy.module.json")})
    assert m["inputs"] == ["sheet"] and m["network"]["neurons"] == 29
    path = str(tmp_path / "toy.module.json")
    c = ok("module_compose", {"paths": [path, path], "name": "c", "links": [["toy.map", "toy2.map"]]})
    assert c["prefixes"] == ["toy", "toy2"] and c["network"]["neurons"] == 58


def test_resource_refusal_is_reported_as_resource():
    r = call("generate", {"neurons": 10 ** 9})
    assert r["kind"] == "resource" and "memory" in r["error"]


def test_every_command_is_tested():
    """Runs last (file order): adding a command to the protocol requires a test of it here."""
    assert set(METHODS) <= TESTED, sorted(set(METHODS) - TESTED)


def test_server_process_round_trip():
    p = subprocess.run([sys.executable, "-m", "neurogenesis.bridge"], input='{"id": 5, "method": "ping"}\n',
                       capture_output=True, text=True, timeout=300, env={**__import__("os").environ, "JAX_PLATFORMS": "cpu"})
    msgs = [json.loads(l) for l in p.stdout.splitlines()]
    assert msgs[0]["event"] == "ready" and msgs[0]["data"]["protocol"] == PROTOCOL_VERSION
    assert {"id": 5, "result": "pong"} in msgs


def test_capabilities_report_status_for_every_roadmap_phase():
    """Protocol 1.1: each task has a status; partial tasks say what is missing; every roadmap phase is listed."""
    tasks = server.m_capabilities({})["tasks"]
    assert all(t["status"] in ("done", "partial", "missing") for t in tasks)
    assert all(t["available"] == (t["status"] != "missing") for t in tasks)
    assert all(t.get("note") for t in tasks if t["status"] == "partial")
    phases = {t["task"].rstrip("0123456789") for t in tasks}
    assert {"A", "B", "C", "D", "E", "F", "G", "H", "K", "I", "P", "N", "J"} <= {p.rstrip("b") for p in phases}
    by = {t["task"]: t for t in tasks}
    assert by["E3"]["status"] == "done" and by["D4"]["status"] == "done" and by["C8"]["status"] == "partial"
    assert by["K5"]["status"] == "missing"
