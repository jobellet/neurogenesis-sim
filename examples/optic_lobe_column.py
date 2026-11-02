import argparse
import numpy as np
from typing import Dict, Any, List

from neurogenesis.tissue import Tissue
from neurogenesis.data.importer import import_connectome
from neurogenesis.data.catalogue import load_manifest
from neurogenesis.data.targets import extract_fitting_targets, compare_type_statistics
from neurogenesis.fitting import fit, evaluate
from neurogenesis.project.io import Project
from neurogenesis.stages.base import run_schedule

# Mock dataset and manifest for testing without network download
import json
import os
import shutil
from pathlib import Path

def setup_mock_dataset(target_dir: Path, seed: int = 42) -> Path:
    rng = np.random.default_rng(seed)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 7 hexagonal columns
    cols = []
    dx = 10.0
    dy = dx * np.sqrt(3) / 2
    cols.append([0.0, 0.0, 0.0])
    cols.append([dx, 0.0, 0.0])
    cols.append([-dx, 0.0, 0.0])
    cols.append([dx/2, dy, 0.0])
    cols.append([-dx/2, dy, 0.0])
    cols.append([dx/2, -dy, 0.0])
    cols.append([-dx/2, -dy, 0.0])
    
    hex_centres = np.array(cols)
    
    # Generate cells
    cell_types = ["Mi1", "Tm3", "Mi4", "Mi9", "T4"]
    N_per_col = [2, 2, 2, 2, 1]  # roughly to get 9 per column
    
    neurons = []
    cell_id = 0
    
    for i, c in enumerate(cols):
        for ct_idx, num in enumerate(N_per_col):
            for _ in range(num):
                jx = float(rng.uniform(-1, 1))
                jy = float(rng.uniform(-1, 1))
                neurons.append({
                    "id": cell_id,
                    "x": c[0] + jx,
                    "y": c[1] + jy,
                    "z": c[2],
                    "cell_type": cell_types[ct_idx],
                    "transmitter": "ACh" if cell_types[ct_idx] in ("Mi1", "Tm3") else "GABA" if cell_types[ct_idx] == "Mi4" else "Glu",
                    "region": "medulla",
                    "class": "neuron"
                })
                cell_id += 1
                
    import csv
    with open(target_dir / "neurons.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "x", "y", "z", "cell_type", "transmitter", "region", "class"])
        writer.writeheader()
        writer.writerows(neurons)
        
    edges = []
    
    def get_cells(ct):
        return [n for n in neurons if n["cell_type"] == ct]
        
    t4s = get_cells("T4")
    mi1s = get_cells("Mi1")
    tm3s = get_cells("Tm3")
    mi4s = get_cells("Mi4")
    mi9s = get_cells("Mi9")
    
    for t4 in t4s:
        c_pos = np.array([t4["x"], t4["y"], t4["z"]])
        for pre_list, prob, w in [(mi1s, 0.8, 10), (tm3s, 0.8, 10), (mi4s, 0.6, 5), (mi9s, 0.6, 5)]:
            for pre in pre_list:
                p_pos = np.array([pre["x"], pre["y"], pre["z"]])
                dist = np.linalg.norm(c_pos - p_pos)
                if dist < 12.0 and rng.random() < prob:
                    edges.append({
                        "pre": pre["id"],
                        "post": t4["id"],
                        "count": w
                    })
                    
    for pre in mi1s:
        c_pos = np.array([pre["x"], pre["y"], pre["z"]])
        for post in tm3s:
            p_pos = np.array([post["x"], post["y"], post["z"]])
            dist = np.linalg.norm(c_pos - p_pos)
            if dist < 8.0 and rng.random() < 0.5:
                edges.append({
                    "pre": pre["id"],
                    "post": post["id"],
                    "count": 3
                })
                
    with open(target_dir / "edges.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["pre", "post", "count"])
        writer.writeheader()
        writer.writerows(edges)
        
    manifest = {
        "id": "optic_mock",
        "title": "Mock Optic Lobe",
        "license": "CC-BY-4.0",
        "url": "http://localhost/", # mock url to pass validation
        "files": [
            {"name": "neurons.csv", "sha256": "mock1"},
            {"name": "edges.csv", "sha256": "mock2"}
        ],
        "tables": {
            "neurons": {
                "file": "neurons.csv",
                "format": "csv",
                "columns": {
                    "id": "id",
                    "x": "x",
                    "y": "y",
                    "z": "z",
                    "cell_type": "cell_type",
                    "transmitter": "transmitter",
                    "region": "region",
                    "class": "class"
                }
            },
            "edges": {
                "file": "edges.csv",
                "format": "csv",
                "columns": {
                    "pre": "pre",
                    "post": "post",
                    "count": "count"
                }
            }
        },
        "units": {
            "voxel_size": [1.0, 1.0, 1.0],
            "origin": [0.0, 0.0, 0.0],
            "unit": "um"
        }
    }
    
    with open(target_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)
        
    return hex_centres

def create_project(hex_centres, t_baseline, info):
    # Map imported strings to integers (0: Mi1, 1: Mi4, 2: Mi9, 3: T4, 4: Tm3) 
    # based on the importer's alphabetic sorting of types
    type_map = {n: i for i, n in enumerate(info["type_names"])}
    
    # To use `grow_axons` which connects based on `region` IDs, 
    # we'll map `region = cell_type` in our `place_by_hand`.
    
    # We want exact number per column to match cell_count exactly
    # 2 Mi1, 2 Mi4, 2 Mi9, 1 T4, 2 Tm3 per column
    
    n_per_type = {
        type_map["Mi1"]: 2,
        type_map["Tm3"]: 2,
        type_map["Mi4"]: 2,
        type_map["Mi9"]: 2,
        type_map["T4"]: 1
    }
    
    pos = []
    c_types = []
    rng = np.random.default_rng(123)
    
    for c in hex_centres:
        for t, n in n_per_type.items():
            for _ in range(n):
                pos.append(c + rng.uniform(-1, 1, size=3))
                c_types.append(t)
                
    pos = np.array(pos)
    c_types = np.array(c_types)

    project = {
        "schedule": [
            {
                "name": "proliferate_and_differentiate",
                "operator": "place_by_hand",
                "params": {
                    "positions": {"type": "Const", "value": pos.tolist()},
                    "cell_type": {"type": "Const", "value": c_types.tolist()},
                    "region": {"type": "Const", "value": c_types.tolist()}  # Make region = cell_type for grow_axons!
                }
            },
            {
                "name": "differentiate",
                "operator": "differentiate",
                "params": {}
            },
            {
                "name": "guidance",
                "operator": "grow_axons",
                "params": {
                    "projections": [
                        f"{type_map['Mi1']}->{type_map['T4']}",
                        f"{type_map['Tm3']}->{type_map['T4']}",
                        f"{type_map['Mi4']}->{type_map['T4']}",
                        f"{type_map['Mi9']}->{type_map['T4']}",
                        f"{type_map['Mi1']}->{type_map['Tm3']}"
                    ],
                    "guidance": {
                        f"{type_map['Mi1']}->{type_map['T4']}": {
                            "p0": {"type": "Fit", "target": "p_0_4", "init": 0.5, "lo": 0.0, "hi": 1.0},
                            "sigma": {"type": "Fit", "target": "s_0_4", "init": 10.0, "lo": 2.0, "hi": 30.0},
                            "w": 10
                        },
                        f"{type_map['Tm3']}->{type_map['T4']}": {
                            "p0": {"type": "Fit", "target": "p_1_4", "init": 0.5, "lo": 0.0, "hi": 1.0},
                            "sigma": {"type": "Fit", "target": "s_1_4", "init": 10.0, "lo": 2.0, "hi": 30.0},
                            "w": 10
                        },
                        f"{type_map['Mi4']}->{type_map['T4']}": {
                            "p0": {"type": "Fit", "target": "p_2_4", "init": 0.5, "lo": 0.0, "hi": 1.0},
                            "sigma": {"type": "Fit", "target": "s_2_4", "init": 10.0, "lo": 2.0, "hi": 30.0},
                            "w": 5
                        },
                        f"{type_map['Mi9']}->{type_map['T4']}": {
                            "p0": {"type": "Fit", "target": "p_3_4", "init": 0.5, "lo": 0.0, "hi": 1.0},
                            "sigma": {"type": "Fit", "target": "s_3_4", "init": 10.0, "lo": 2.0, "hi": 30.0},
                            "w": 5
                        },
                        f"{type_map['Mi1']}->{type_map['Tm3']}": {
                            "p0": {"type": "Fit", "target": "p_0_1", "init": 0.5, "lo": 0.0, "hi": 1.0},
                            "sigma": {"type": "Fit", "target": "s_0_1", "init": 10.0, "lo": 2.0, "hi": 30.0},
                            "w": 3
                        }
                    }
                }
            },
            {
                "name": "freeze",
                "operator": "freeze",
                "params": {}
            }
        ]
    }
    
    return project

def main():
    parser = argparse.ArgumentParser(description="Optic Lobe Column Benchmark")
    parser.add_argument("--dir", type=str, default="/tmp/mock_optic", help="Dir for mock connectome")
    args = parser.parse_args()
    
    target_dir = Path(args.dir)
    hex_centres = setup_mock_dataset(target_dir)
    
    import neurogenesis.data.catalogue as cat
    original_sha256 = cat.sha256
    cat.sha256 = lambda p: "mock1" if "neurons" in str(p) else "mock2"
    
    manifest_dict = json.load(open(target_dir / "manifest.json"))
    t_baseline, info = import_connectome(
        manifest_dict, 
        directory=target_dir,
        transmitter_signs={"ACh": 1, "Glu": -1, "GABA": -1}, 
        log=lambda s: None
    )
    
    # Restore original sha256 function just in case
    cat.sha256 = original_sha256
    
    targets = extract_fitting_targets(t_baseline, columns=hex_centres, min_synapses=1)
    
    fit_targets = [t for t in targets if t["metric"] != "cell_count"]
    
    project = create_project(hex_centres, t_baseline, info)
    
    print("Starting fit...")
    fit_result = fit(project, fit_targets, seeds=(0, 1), iterations=30, popsize=10)
    print("Fit completed.")
    
    t_grown = run_schedule(project, fit_result.genome, seed=2)
    
    stats = compare_type_statistics(t_grown, t_baseline)
    
    print(f"Comparison Stats:")
    print(f"Cosine Similarity: {stats['matrix_cosine_similarity']:.3f}")
    print(f"Degree Rel Error: {stats['degree_mean_rel_error']:.3f}")
    
    from neurogenesis.stages.refinement import simulate_tissue
    simulate_tissue(t_baseline, 10, 0, np.zeros(len(t_baseline.alive), np.int32))
    simulate_tissue(t_grown, 10, 0, np.zeros(len(t_grown.alive), np.int32))
    
    print("Simulation complete. Success.")

if __name__ == "__main__":
    main()
