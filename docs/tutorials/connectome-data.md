# Tutorial 13 — Import a connectome

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/connectome-data.ipynb)

The data layer (`neurogenesis.data`, Phase I) reads public connectome datasets described by a **manifest**, without
naming any dataset in the code.

## Describe a dataset
A manifest `datasets/<id>.json` lists the files (URL, SHA-256, size), the license and citation, the column names of
the neuron and edge tables, and the units:
```json
{"id": "my_dataset", "license": "CC-BY-4.0", "citation": "...", "url": "https://example.org/data/",
 "files": [{"name": "neurons.csv", "sha256": "...", "size": 123456},
           {"name": "edges.csv", "sha256": "...", "size": 7890123}],
 "tables": {"neurons": {"file": "neurons.csv", "format": "csv",
                        "columns": {"id": "root_id", "x": "pos_x", "y": "pos_y", "z": "pos_z",
                                    "cell_type": "type", "region": "region", "side": "side", "transmitter": "nt"}},
            "edges": {"file": "edges.csv", "format": "csv",
                      "columns": {"pre": "pre_root_id", "post": "post_root_id", "count": "syn_count"}}},
 "units": {"voxel_size": [0.004, 0.004, 0.04], "origin": [0, 0, 0], "mirror": [], "unit": "um"}}
```

## Fetch
```
python -m neurogenesis data info my_dataset              # size, license, citation
python -m neurogenesis data fetch my_dataset             # asks before downloading; --yes to skip the question
```
Files go to `$NEUROGENESIS_DATA` (default `~/.cache/neurogenesis/data/<id>/`), never into the repository. An
interrupted download is resumed; every file is checked against its SHA-256.

## Import a sub-circuit
```python
from neurogenesis.data import import_connectome

tissue, info = import_connectome(
    "my_dataset",
    filters={"cell_type": ["T1", "re:^T2"], "side": ["left"], "min_synapses": 5,
             "bbox": [[0, 0, 0], [200, 200, 100]]},                     # bbox in space units, after registration
    weight_map={"kind": "hill", "w_max": 800, "k": 20, "n": 1},
    transmitter_signs={"gaba": -1, "glutamate": 1},
    conduction_velocity=1.0)                                             # space units per tick
info["license"], info["citation"], info["source_ids"], info["type_names"]
```
- Tables are streamed in batches: CSV with NumPy (no quoted commas inside fields), or Parquet / Feather / CSV with
  pyarrow (`pip install -e ".[data]"`). Only edges between selected neurons are kept, summed over neuropils.
- Positions are registered: raw × `voxel_size` + `origin`, then `mirror` axes negated. Delays are soma distance /
  velocity, clipped to 31 ticks with a counted warning.
- Weights: `linear` (gain × count), `hill` (w_max cⁿ / (kⁿ + cⁿ)) or `log` (gain log(1 + c)), clipped to
  `w_clip` (512–2047); the sign comes from the presynaptic transmitter (`transmitter_signs`). With a pharmacology
  `profile` the transmitter bits of the cells are set too, so `assign_receptors` and `pharmacology` stages can follow.

The result is an ordinary `Tissue`: freeze it (`neurogenesis.stages.freeze.freeze`) to simulate it, or use it as a
target for fitting (`neurogenesis.fitting`).
