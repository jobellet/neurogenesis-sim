"""Tests for F3: Guidance through Params, string projection keys, and expression-gradient driven axon growth."""
import json
import numpy as np

from neurogenesis.stages.base import run_schedule


def test_grow_axons_accepts_guidance_param_with_string_keys():
    """grow_axons must accept guidance as a Param with 'src->dst' string keys (no tuple keys)."""
    project = {
        "version": "1.0.0",
        "geometry": {
            "source_box": {"type": "Box", "center": [0, 0, 0], "size": [10, 10, 10]},
            "target_box": {"type": "Box", "center": [30, 0, 0], "size": [10, 10, 10]}
        },
        "fields": {},
        "schedule": [
            {
                "operator": "seed_cells",
                "params": {"N": 15, "geometry": "source_box", "region": 0}
            },
            {
                "operator": "seed_cells",
                "params": {"N": 15, "geometry": "target_box", "region": 1}
            },
            {
                "operator": "grow_axons",
                "params": {
                    "projections": ["0->1"],
                    "guidance": {
                        "0->1": {
                            "B": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                            "c": [0.0, 0.0, 0.0],
                            "sigma": 0.3,
                            "p0": 0.9,
                            "w": 100,
                            "wc": 256
                        }
                    }
                }
            }
        ]
    }

    # Verify JSON round-trip of project specification
    json_str = json.dumps(project)
    project_reloaded = json.loads(json_str)

    tissue = run_schedule(project_reloaded, genome={}, seed=42)
    assert len(tissue.connectivity.pre) > 0
    # Pre neurons must all be in region 0, post in region 1
    assert np.all(tissue.region[tissue.connectivity.pre] == 0)
    assert np.all(tissue.region[tissue.connectivity.post] == 1)


def test_grow_axons_driven_by_gene_expression_gradient_and_json_roundtrip():
    """End-to-end test: grow_axons driven by a gene expression gradient, verified through JSON round-trip."""
    # Source region [0, 10] along x, target region [40, 50] along x
    project = {
        "version": "1.0.0",
        "geometry": {
            "retina": {"type": "Box", "center": [5, 5, 5], "size": [10, 10, 10]},
            "tectum": {"type": "Box", "center": [45, 5, 5], "size": [10, 10, 10]}
        },
        "fields": {
            "morphogen_gradient": {
                "type": "AnalyticField",
                "expr": "x / 10.0"  # x in [0, 10] gives gradient from 0 to 1
            }
        },
        "schedule": [
            {
                "name": "seed_retina",
                "operator": "seed_cells",
                "params": {"N": 30, "geometry": "retina", "region": 0}
            },
            {
                "name": "seed_tectum",
                "operator": "seed_cells",
                "params": {"N": 30, "geometry": "tectum", "region": 1}
            },
            {
                "name": "express_morphogen",
                "operator": "express",
                "params": {
                    "K": 1,
                    "morphogens": [
                        {
                            "field": {"type": "Field", "name": "morphogen_gradient"},
                            "weights": [1.0]
                        }
                    ],
                    "dt": 1.0,
                    "decay": 0.0
                }
            },
            {
                "name": "differentiate_by_expression",
                "operator": "differentiate",
                "params": {
                    "types": [
                        {
                            "type_id": 1,
                            "condition": "expr[0] > 0.6",
                            "sign": 1
                        },
                        {
                            "type_id": 0,
                            "condition": "expr[0] <= 0.6",
                            "sign": 1
                        }
                    ]
                }
            },
            {
                "name": "guided_axon_growth",
                "operator": "grow_axons",
                "params": {
                    "projections": ["0->1"],
                    "rules_shift": ["identity_offset"],
                    "guidance": {
                        "0->1": {
                            "B": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                            "c": [0.0, 0.0, 0.0],
                            "type_c": [
                                [-0.4, 0.0, 0.0],  # Identity 0 (low expr): shift target toward low x
                                [0.4, 0.0, 0.0]    # Identity 1 (high expr): shift target toward high x
                            ],
                            "sigma": 0.25,
                            "p0": 0.85,
                            "w": 50
                        }
                    }
                }
            }
        ]
    }

    # 1. Verify JSON serializability
    project_json_str = json.dumps(project, indent=2)
    deserialized_project = json.loads(project_json_str)

    # 2. Run schedule on both original and deserialized projects
    tissue1 = run_schedule(project, genome={}, seed=101)
    tissue2 = run_schedule(deserialized_project, genome={}, seed=101)

    # 3. Check bit-for-bit identical outputs from JSON round-trip
    np.testing.assert_array_equal(tissue1.connectivity.pre, tissue2.connectivity.pre)
    np.testing.assert_array_equal(tissue1.connectivity.post, tissue2.connectivity.post)
    np.testing.assert_array_equal(tissue1.connectivity.weight, tissue2.connectivity.weight)
    np.testing.assert_array_equal(tissue1.connectivity.delay, tissue2.connectivity.delay)

    # 4. Verify that gene expression gradient drove spatial connectivity
    assert len(tissue1.connectivity.pre) > 0

    pre_idx = tissue1.connectivity.pre
    post_idx = tissue1.connectivity.post

    # Identity 0 (low morphogen / low x) vs Identity 1 (high morphogen / high x)
    low_expr_mask = (tissue1.cell_type[pre_idx] == 0)
    high_expr_mask = (tissue1.cell_type[pre_idx] == 1)

    assert np.any(low_expr_mask), "Should have synapses from low-expression cells"
    assert np.any(high_expr_mask), "Should have synapses from high-expression cells"

    # Target x positions for low-expression vs high-expression source cells
    target_x_for_low = tissue1.positions[post_idx[low_expr_mask], 0]
    target_x_for_high = tissue1.positions[post_idx[high_expr_mask], 0]

    # Because identity 1 shifts target by +0.4 along x and identity 0 shifts by -0.4,
    # the mean target x for high-expression source cells should be strictly greater than for low-expression cells!
    assert np.mean(target_x_for_high) > np.mean(target_x_for_low)

