"""The UI schema contract (desktop/common/UI_SCHEMA.md): its JSON Schema accepts the complete example document and
rejects broken ones. Exporters (python -m neurogenesis ui-schema, task H3) validate their output with validate()."""
import copy
import json
import re
from pathlib import Path

import pytest

COMMON = Path(__file__).resolve().parents[1] / "desktop" / "common"
SCHEMA = json.loads((COMMON / "ui_schema.schema.json").read_text())
EXAMPLE = json.loads((COMMON / "ui_schema.example.json").read_text())

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(value, t):
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[t])


def errors(value, schema, root=SCHEMA, where="$"):
    """Errors of a value against the subset of JSON Schema the UI schema uses ($ref, type, const, enum, pattern,
    minimum, maximum, minItems, required, properties, items, anyOf). Dependency-free, so CI needs nothing new."""
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        return errors(value, node, root, where)
    out = []
    if "anyOf" in schema and not any(not errors(value, s, root, where) for s in schema["anyOf"]):
        out.append(f"{where}: matches none of anyOf")
    if "type" in schema and not _is(value, schema["type"]):
        return out + [f"{where}: expected {schema['type']}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        out.append(f"{where}: must be {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{where}: not one of {schema['enum']}")
    if "pattern" in schema and isinstance(value, str) and not re.search(schema["pattern"], value):
        out.append(f"{where}: does not match {schema['pattern']}")
    if "minimum" in schema and _is(value, "number") and value < schema["minimum"]:
        out.append(f"{where}: below {schema['minimum']}")
    if "maximum" in schema and _is(value, "number") and value > schema["maximum"]:
        out.append(f"{where}: above {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{where}: fewer than {schema['minItems']} items")
        for k, item in enumerate(value):
            if "items" in schema:
                out += errors(item, schema["items"], root, f"{where}[{k}]")
    if isinstance(value, dict):
        out += [f"{where}: missing {key!r}" for key in schema.get("required", []) if key not in value]
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                out += errors(value[key], sub, root, f"{where}.{key}")
    return out


def validate(document):
    errs = errors(document, SCHEMA)
    if errs:
        raise ValueError("invalid UI schema:\n" + "\n".join(errs[:20]))


def test_example_is_valid():
    validate(EXAMPLE)


def test_example_valid_for_the_reference_validator_too():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(EXAMPLE, SCHEMA)


def test_example_covers_every_param_type_and_source():
    params = [p for s in EXAMPLE["stages"] for p in s["params"]]
    assert {p["type"] for p in params} >= {"float", "int", "bool", "choice", "vec3", "geometry", "field", "json"}
    assert {s["type"] for s in EXAMPLE["param_sources"]} == {"Const", "Gene", "Field", "Fit", "Expr"}
    known = {s["type"] for s in EXAMPLE["param_sources"]}
    assert all(set(p["sources"]) <= known and p["default"]["type"] in p["sources"] for p in params)
    assert any(s["available"] for s in EXAMPLE["stages"]) and any(not s["available"] for s in EXAMPLE["stages"])
    assert {m["name"] for m in EXAMPLE["models"]} == {"lif_int", "two_compartment", "hh"}


def test_example_models_match_the_toolbox():
    from neurogenesis.cost import PARAM_BYTES, SYNAPSE_BYTES, SYNAPSE_WORK_BYTES
    from neurogenesis.spiking.models import MODELS
    for m in EXAMPLE["models"]:
        tb = MODELS[m["name"]]
        assert (m["substeps"], m["state_bytes"], m["flops"]) == (tb.substeps, tb.state_bytes, tb.flops)
        assert m["cost"]["bytes_per_neuron"] == PARAM_BYTES + tb.state_bytes + 4
        assert m["cost"]["bytes_per_synapse"] == SYNAPSE_BYTES + SYNAPSE_WORK_BYTES


def test_example_rules_match_the_toolbox():
    from neurogenesis.development.plan import DEFAULT_RULES
    default_rules = {(phase, rule) for phase, rules in DEFAULT_RULES.items() for rule in rules}
    assert {(r["phase"], r["name"]) for r in EXAMPLE["rules"]} == default_rules
    assert [p["name"] for p in EXAMPLE["rule_phases"]] == list(DEFAULT_RULES)


@pytest.mark.parametrize("break_it", [
    lambda d: d.pop("stages"),
    lambda d: d.update(format="something else"),
    lambda d: d.update(version="2.0"),
    lambda d: d["stages"][0]["params"][0].pop("doc"),
    lambda d: d["stages"][0].update(cost={"declared": True}),
    lambda d: d["stages"][0]["params"][1].update(default=3),
    lambda d: d["models"][0].update(substeps=0),
    lambda d: d["models"][0]["cost"].update(seconds_per_synapse_tick="fast"),
    lambda d: d["schedule_genes"][0].update(path=[]),
    lambda d: d["schedule_genes"][0].update(path=["count", 1.5]),
    lambda d: d["rules"][0].pop("default"),
])
def test_broken_documents_are_rejected(break_it):
    d = copy.deepcopy(EXAMPLE)
    break_it(d)
    with pytest.raises(ValueError):
        validate(d)


def test_spec_documents_every_top_level_key():
    spec = (COMMON / "UI_SCHEMA.md").read_text()
    assert all(f"`{k}`" in spec or f'"{k}"' in spec for k in SCHEMA["required"])

def test_export_ui_schema_validates():
    from neurogenesis.project.ui_schema import export_ui_schema
    doc = export_ui_schema()
    validate(doc)
    
    # Check that known stages are there and available
    stage_ops = [s["operator"] for s in doc["stages"] if s["available"]]
    assert "seed_cells" in stage_ops
    assert "proliferate" in stage_ops
    assert "migrate" in stage_ops
    assert "grow_axons" in stage_ops
    assert "refine_by_activity" in stage_ops
    
    # Check cost parsing on a known stage
    seed = next(s for s in doc["stages"] if s["operator"] == "seed_cells")
    assert seed["cost"] is not None
    assert seed["cost"]["declared"] is True
    assert len(seed["cost"]["samples"]) == 2

def test_export_ui_schema_with_project():
    from neurogenesis.project.ui_schema import export_ui_schema
    project = {
        "schedule": [
            {
                "operator": "seed_cells",
                "name": "1_seed_cells",
                "params": {
                    "count": {"type": "Gene", "path": ["count", "map"], "lo": 10, "hi": 2000, "integer": True}
                }
            }
        ]
    }
    doc = export_ui_schema(project=project)
    validate(doc)
    
    genes = doc["schedule_genes"]
    assert len(genes) == 1
    assert genes[0]["path"] == ["count", "map"]
    assert genes[0]["lo"] == 10
    assert genes[0]["hi"] == 2000
    assert genes[0]["integer"] is True
    assert genes[0]["used_by"] == [{"stage": "1_seed_cells", "param": "count"}]

def test_bridge_m_ui_schema():
    from neurogenesis.bridge.server import m_ui_schema
    doc = m_ui_schema({})
    validate(doc)

def test_cli_ui_schema(capsys):
    import sys
    from unittest.mock import patch
    from neurogenesis.cli import main

    with patch.object(sys, 'argv', ['neurogenesis', 'ui-schema']):
        main()

    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    validate(doc)


def test_export_ui_schema_includes_targets():
    from neurogenesis.project.ui_schema import export_ui_schema
    doc = export_ui_schema()
    validate(doc)

    assert "targets" in doc
    targets = {t["name"]: t for t in doc["targets"]}
    assert "cell_count" in targets
    assert "modularity" in targets
    assert "nearest_neighbour_regularity" in targets
    assert "within_group_fraction" in targets
    assert "pinwheel_density" in targets
    assert "field_correlation" in targets

    mod = targets["modularity"]
    assert mod["title"] == "Network Modularity Q"
    assert mod["requires_spiking"] is False
    assert "options" in mod


def test_export_ui_schema_multi_domain_schedule_genes():
    from neurogenesis.project.ui_schema import export_ui_schema
    project = {
        "schedule": [
            {
                "operator": "seed_cells",
                "name": "seed",
                "params": {
                    "count": {"type": "Gene", "path": ["count", "map"], "lo": 10, "hi": 2000, "integer": True}
                }
            }
        ],
        "fields": {
            "morphogen": {
                "type": "AnalyticField",
                "expr": "x * gain",
                "gain": {"type": "Gene", "path": ["fields", "gain"], "lo": 0.5, "hi": 2.0}
            }
        },
        "drugs": {
            "bicuculline": {
                "dose": {"type": "Gene", "path": ["drugs", "bicuculline"], "lo": 0.0, "hi": 1.0},
                "effect": "antagonist"
            }
        }
    }
    doc = export_ui_schema(project=project)
    validate(doc)

    genes = doc["schedule_genes"]
    paths = [g["path"] for g in genes]
    assert ["count", "map"] in paths
    assert ["fields", "gain"] in paths
    assert ["drugs", "bicuculline"] in paths

    for g in genes:
        assert len(g["used_by"]) >= 1
        for u in g["used_by"]:
            assert "stage" in u and isinstance(u["stage"], str)
            assert "param" in u and isinstance(u["param"], str)

