"""UI schema export (H3): `export_ui_schema` describes the stage registry (Params, kinds, bounds, docs, cost
samples), the neuron models with cost estimates, the guidance and placement rules, the genes of a Project and its
schema as JSON for the desktop apps (`python -m neurogenesis ui-schema`, bridge method `ui_schema`).
"""
import datetime
import inspect
import platform
import typing
import json
from pathlib import Path
from typing import Dict, Any, Optional

import neurogenesis
from neurogenesis.project.schema import SCHEMA_VERSION
from neurogenesis.params import collect_genes, _walk_genes
from neurogenesis.stages.base import STAGE_REGISTRY
from neurogenesis.bridge.server import STAGE_TASKS
from neurogenesis.spiking.models import MODELS
from neurogenesis.cost import estimate as cost_estimate
from neurogenesis.cost import PARAM_BYTES, SYNAPSE_BYTES, SYNAPSE_WORK_BYTES, _device
from neurogenesis.development.rules import RULES
from neurogenesis.development.plan import DEFAULT_RULES


def export_ui_schema(project: Optional[Dict[str, Any]] = None, calibrated: bool = False) -> Dict[str, Any]:
    """Generates a UI schema conforming to desktop/common/ui_schema.schema.json."""
    doc = {
        "format": "neurogenesis-ui-schema",
        "version": "1.0",
        "generated_by": {
            "toolbox": neurogenesis.__version__,
            "python": platform.python_version(),
            "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        },
        "project_schema_version": SCHEMA_VERSION,
        "param_sources": [
            {
                "type": "Const", "title": "By hand", "doc": "A value set by hand.",
                "inputs": [{"name": "value", "type": "value", "doc": "The value (its type is the parameter's)."}]
            },
            {
                "type": "Gene", "title": "Gene", "doc": "Read from the genome at a gene path; evolution searches it between lo and hi.",
                "inputs": [
                    {"name": "path", "type": "gene_path", "doc": "Where the gene is in the genome, e.g. count / map."},
                    {"name": "lo", "type": "float", "doc": "Smallest value evolution may give the gene."},
                    {"name": "hi", "type": "float", "doc": "Largest value evolution may give the gene."},
                    {"name": "integer", "type": "bool", "doc": "Round the gene to an integer."}
                ]
            },
            {
                "type": "Field", "title": "Field", "doc": "Sampled from a project field at each cell's position.",
                "inputs": [
                    {"name": "name", "type": "field", "doc": "Which project field."},
                    {"name": "transform", "type": "string", "doc": "Optional formula applied to the sampled value x, e.g. 2*x + 1."}
                ]
            },
            {
                "type": "Fit", "title": "Fitted", "doc": "Fitted to data (task E2), starting from init, within lo and hi.",
                "inputs": [
                    {"name": "target", "type": "string", "doc": "The measurement it is fitted to, e.g. density."},
                    {"name": "init", "type": "float", "doc": "Starting value."},
                    {"name": "lo", "type": "float", "doc": "Lower bound."},
                    {"name": "hi", "type": "float", "doc": "Upper bound."}
                ]
            },
            {
                "type": "Expr", "title": "Formula", "doc": "A formula of other parameters and fields.",
                "inputs": [{"name": "formula", "type": "string", "doc": "E.g. 0.5 * density + 0.1."}]
            }
        ]
    }

    # Stages
    stages_out = []
    task_map = {n: t for t, n in STAGE_TASKS}
    all_stages = set(STAGE_REGISTRY.keys()).union(set(task_map.keys()))
    
    common = Path(__file__).resolve().parents[2] / "desktop" / "common"
    
    example_doc = {}
    try:
        example_doc = json.loads((common / "ui_schema.example.json").read_text())
    except Exception:
        pass
        
    example_stages = {s["operator"]: s for s in example_doc.get("stages", [])}
    
    for op in sorted(list(all_stages)):
        available = op in STAGE_REGISTRY
        task = task_map.get(op, "plugin")
        
        ex_s = example_stages.get(op, {})
        
        if available:
            cls = STAGE_REGISTRY[op]
            title = getattr(cls, "title", ex_s.get("title", op.replace("_", " ").capitalize()))
            doc_str = getattr(cls, "__doc__", "") or ""
            desc = doc_str.split("\n\n")[0].strip().replace('\n', ' ') if doc_str else ""
            if not desc:
                desc = ex_s.get("description", "")
            
            params = ex_s.get("params", [])
            
            cost = None
            if hasattr(cls, "cost"):
                try:
                    c1 = cls.cost(1000, 10000, {})
                    c2 = cls.cost(100000, 1000000, {})
                    cost = {
                        "declared": True,
                        "samples": [
                            {"N": 1000, "E": 10000, "bytes": c1[0], "ops": c1[1]},
                            {"N": 100000, "E": 1000000, "bytes": c2[0], "ops": c2[1]}
                        ]
                    }
                except Exception:
                    cost = None
                    
            stages_out.append({
                "operator": op,
                "title": title,
                "description": desc,
                "task": task,
                "available": True,
                "params": params,
                "cost": cost,
                "repeatable": getattr(cls, "repeatable", ex_s.get("repeatable", op in ["proliferate", "migrate"])),
                "conditional": getattr(cls, "conditional", ex_s.get("conditional", True))
            })
        else:
            stages_out.append({
                "operator": op,
                "title": ex_s.get("title", op.replace("_", " ").capitalize()),
                "description": ex_s.get("description", ""),
                "task": task,
                "available": False,
                "params": ex_s.get("params", []),
                "cost": None,
                "repeatable": ex_s.get("repeatable", op in ["proliferate", "migrate"]),
                "conditional": ex_s.get("conditional", True)
            })
            
    doc["stages"] = stages_out

    # Models
    models_out = []
    for name, m in MODELS.items():
        desc = getattr(m, "description", None)
        if desc is None:
            doc_str = getattr(m, "__doc__", "") or ""
            desc = doc_str.split("\n\n")[0].strip().replace('\n', ' ') if doc_str else ""
        
        # Load calibration if available (even if calibrated=False, estimate handles this via cal check internally, but we need raw constants)
        from neurogenesis.cost import calibrate, _load, _device
        cal = calibrate(name) if calibrated else _load().get(f"{name}@{_device()}")
        
        models_out.append({
            "name": name,
            "title": getattr(m, "title", name),
            "description": desc,
            "substeps": m.substeps,
            "state_bytes": m.state_bytes,
            "flops": m.flops,
            "native": name == "lif_int",
            "cost": {
                "bytes_per_neuron": PARAM_BYTES + m.state_bytes + 4,
                "bytes_per_synapse": SYNAPSE_BYTES + SYNAPSE_WORK_BYTES,
                "seconds_per_neuron_substep": cal.get("b") if cal else None,
                "seconds_per_synapse_tick": cal.get("c") if cal else None,
                "seconds_per_tick_overhead": cal.get("a") if cal else None,
                "device": _device() if cal else None
            }
        })
    doc["models"] = models_out

    # Rules
    rule_phases_out = [
        {"name": "placement", "title": "Placement", "doc": "Moves cells after they are placed."},
        {"name": "shift", "title": "Target shift", "doc": "Shifts where axons aim."},
        {"name": "target", "title": "Target", "doc": "Sets the target point of each axon."},
        {"name": "probability", "title": "Connection probability", "doc": "Changes the probability of each connection."},
        {"name": "weight", "title": "Weight", "doc": "Changes synaptic weights."}
    ]
    doc["rule_phases"] = rule_phases_out
    
    rules_out = []
    default_rules_set = {(phase, rule) for phase, rules in DEFAULT_RULES.items() for rule in rules}
    for phase, rules in RULES.items():
        for name, fn in rules.items():
            doc_str = getattr(fn, "__doc__", "") or ""
            desc = doc_str.split("\n\n")[0].strip().replace('\n', ' ') if doc_str else ""
            
            ex_r = next((r for r in example_doc.get("rules", []) if r["phase"] == phase and r["name"] == name), {})
            genes = ex_r.get("genes", [])
            
            rules_out.append({
                "phase": phase,
                "name": name,
                "doc": desc,
                "genes": genes,
                "default": (phase, name) in default_rules_set
            })
    doc["rules"] = rules_out
    
    # Schedule Genes
    schedule_genes = []
    if project is not None:
        raw_genes = collect_genes(project.get("schedule", []))
        for path, lo, hi, integer in raw_genes:
            path_list = ["->".join(str(x) for x in k) if isinstance(k, tuple) else k for k in path]
            
            # Need to figure out used_by. For each gene, we check all stages.
            used_by = []
            for i, config in enumerate(project.get("schedule", [])):
                stage_name = config.get("name", f"stage_{i}")
                for param_name, param_val in config.get("params", {}).items():
                    # Check if this param uses this gene
                    param_genes = {}
                    _walk_genes(param_val, param_genes)
                    if path in param_genes:
                        used_by.append({"stage": stage_name, "param": param_name})
                        
            schedule_genes.append({
                "path": path_list,
                "lo": float(lo),
                "hi": float(hi),
                "integer": bool(integer),
                "used_by": used_by
            })
        
    doc["schedule_genes"] = schedule_genes
    return doc
