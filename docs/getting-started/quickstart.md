# Quickstart (5 minutes)

## 1. A network from the command line
```bash
python -m neurogenesis generate --neurons 500 --morphology column --weight-scale 0.2 --refractory 3 --out column.json
python -m neurogenesis simulate --network column.json --ticks 1000 --raster raster.png
python -m neurogenesis stats --network column.json
```

```{figure} ../_static/media/cli_raster.png
:width: 80%

The raster written by `simulate --raster` (one tick = 1 ms).
```

## 2. Grow a circuit from a genome (Python)
The example below grows a sensor sheet that projects topographically onto a map, stimulates two opposite corners of
the sheet and checks where the map responds.

```bash
python examples/topographic_map.py --cpu
```

```text
stimulus at corner (0, 0): 4 map neurons fire, spike-weighted mean u of the map 0.09
stimulus at corner (1, 1): 7 map neurons fire, spike-weighted mean u of the map 0.74
wrote example_out/network.json and example_out/module.json
```

`u` is the position along the map's first axis (0 to 1). In this simulation, stimulating the corner (0, 0) of the
sheet activates the near side of the map, and the opposite corner the far side. The core of the script:

```python
import numpy as np
from neurogenesis.development import BodyPlan, FixedPlacement, Region, grow, region_of
from neurogenesis.spiking.batch import simulate_counts

side = 6
sheet = [[(i + 0.5) / side, (j + 0.5) / side, 0.5] for i in range(side) for j in range(side)]
plan = BodyPlan(name="topographic map", regions=[
    Region("sensor", origin=(0, 0, 0), size=(30, 30, 5), placement=FixedPlacement(sheet), role=1),
    Region("map", origin=(50, 0, 0), size=(30, 30, 10))],
    projections=[("sensor", "map")])

genome = dict(count=dict(map=200), inh_weight_factor=2.0, w_clip=2047,
              migration=dict(map=dict(mean=np.full(3, 0.5), spread=0.35)),
              inhibitory=dict(map=dict(a0=-6.0, a=np.zeros(3))),
              guidance={("sensor", "map"): dict(B=np.diag([2.0, 2.0, 0.0]), c=np.zeros(3),
                                                 sigma=0.12, p0=0.9, w=900.0)})

net = grow(plan, genome, seed=0)                  # deterministic for a given seed
sensor = region_of(net, plan, "sensor")
ext = np.zeros((1, net.num_neurons), np.int32)
ext[0, sensor[0]] = 120                           # constant current into one sensor neuron
counts = simulate_counts([net], [ext], ticks=50)[0]
net.save_json("network.json")
```

## 3. Look at it
```bash
cd viz && npm run dev
```
Open <http://localhost:5173>, click **Import** and choose `example_out/network.json`.

```{figure} ../_static/media/viewer_network.png
:width: 80%

The browser viewer with an imported network.
```

## 4. Know the cost before scaling up
```bash
python -m neurogenesis estimate --neurons 1e5 --synapses-per-neuron 1000 --seconds 1
```
```text
100,000 neurons, 100,000,000 synapses, 1 simulated s (1,000 ticks of 1 ms)
  lif_int          fits (memory 2.5 GB of 66.8 GB available); about 24.7 min for 1000 ticks (24.7 min per simulated second)
  two_compartment  fits (memory 2.5 GB of 66.8 GB available); about 27.5 min for 1000 ticks (27.5 min per simulated second)
  hh               fits (memory 2.5 GB of 66.8 GB available); about 24.7 min for 1000 ticks (24.7 min per simulated second)
```
(Output on a 64-GB CPU node; your numbers depend on your machine.)

## Next steps
- {doc}`concepts` — the vocabulary: plans, genomes, stages, Params, tissues, modules.
- {doc}`../tutorials/index` — step-by-step tutorials.
