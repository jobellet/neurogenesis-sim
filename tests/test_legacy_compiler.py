import numpy as np
import pytest
from neurogenesis.development.legacy_compiler import (
    compile_plan_to_schedule,
    compile_plan_to_project
)
from neurogenesis.stages.base import run_schedule
from neurogenesis.tissue import Tissue
from neurogenesis.development.plan import BodyPlan, Count, FixedPlacement, Region
from neurogenesis.development.grow import grow, knockout
from test_development import sheet_plan, toy_genome, fp


def test_legacy_compiler_equivalence():
    p, g = sheet_plan(), toy_genome()
    net_grow = grow(p, g, seed=42)
    
    # Official library project execution
    project = compile_plan_to_project(p, g)
    tissue = run_schedule(project, g, seed=42, legacy_stream=True)
    net_compiler = tissue.to_network()
    
    assert fp(net_grow) == fp(net_compiler), "Fingerprints do not match!"


def test_legacy_compiler_equivalence_different_seed():
    p, g = sheet_plan(), toy_genome()
    net_grow = grow(p, g, seed=123)
    
    project = compile_plan_to_project(p, g)
    tissue = run_schedule(project, g, seed=123, legacy_stream=True)
    net_compiler = tissue.to_network()
    
    assert fp(net_grow) == fp(net_compiler), "Fingerprints do not match!"


def test_legacy_compiler_with_knockout():
    p, g = sheet_plan(), toy_genome()
    g_ko = knockout(g, regions=["map"])
    net_grow = grow(p, g_ko, seed=7)
    
    project = compile_plan_to_project(p, g_ko)
    tissue = run_schedule(project, g_ko, seed=7, legacy_stream=True)
    net_compiler = tissue.to_network()
    
    assert fp(net_grow) == fp(net_compiler), "Fingerprints do not match with knockout!"


def test_legacy_compiler_topographic_map_example():
    # Test on topographic map from examples/topographic_map.py
    side = 4
    sheet = [[(i + 0.5) / side, (j + 0.5) / side, 0.5] for i in range(side) for j in range(side)]
    p = BodyPlan(
        name="topographic map",
        regions=[
            Region("sensor", origin=(0, 0, 0), size=(30, 30, 5), placement=FixedPlacement(sheet), role=1),
            Region("map", origin=(50, 0, 0), size=(30, 30, 10))
        ],
        projections=[("sensor", "map")]
    )
    g = dict(
        count=dict(map=40),
        inh_weight_factor=2.0,
        w_clip=1024,
        migration=dict(map=dict(mean=np.full(3, 0.5), spread=0.35)),
        inhibitory=dict(map=dict(a0=-6.0, a=np.zeros(3))),
        guidance={("sensor", "map"): dict(B=np.diag([2.0, 2.0, 0.0]), c=np.zeros(3), sigma=0.12, p0=0.9, w=900.0)}
    )
    net_grow = grow(p, g, seed=99)
    project = compile_plan_to_project(p, g)
    tissue = run_schedule(project, g, seed=99, legacy_stream=True)
    net_compiler = tissue.to_network()

    assert fp(net_grow) == fp(net_compiler), "Topographic map fingerprints do not match!"


def test_legacy_compiler_project_serializable_json():
    import json
    p, g = sheet_plan(), toy_genome()
    project = compile_plan_to_project(p, g)
    
    # Must roundtrip cleanly through JSON without loss
    serialized = json.dumps(project)
    deserialized = json.loads(serialized)
    
    tissue = run_schedule(deserialized, g, seed=42, legacy_stream=True)
    net_rt = tissue.to_network()
    net_grow = grow(p, g, seed=42)
    assert fp(net_grow) == fp(net_rt), "JSON-deserialized project fingerprint does not match!"
