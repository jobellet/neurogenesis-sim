# Tutorial 6 — Geometry and fields (experimental)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/fields-geometry.ipynb)

```{admonition} Experimental
:class: warning
Geometries and fields (roadmap phase B) are new and their API may still change. Geometries and fields declared in
a Project's `fields` are built when the schedule runs, and unknown types raise an error.
```

## Geometries
Shapes in 2D or 3D, used to seed cells, constrain migration and define regions.

```python
import numpy as np
from neurogenesis.geometry import Box, Sphere, Union, Difference, geometry_from_dict

shell = Difference(Box([0, 0, 0], [2, 2, 2]), Sphere([0, 0, 0], 0.5))   # a cube with a spherical hole
pts = shell.sample(1000, np.random.default_rng(0))                      # 1000 points inside, shape (1000, 3)
shell.contains(np.zeros((1, 3)))                                        # array([False])
d = shell.to_dict()          # {'type': 'Difference', 'a': {'type': 'Box', ...}, 'b': {'type': 'Sphere', ...}}
same = geometry_from_dict(d)                                            # JSON round trip
```

| Type | Parameters |
|---|---|
| `Box` | `center`, `size` |
| `Sphere` | `center`, `radius` |
| `Ellipsoid`, `Cylinder` | see {doc}`../reference/api` |
| `Sheet2D`, `CurvedSheet` | 2D sheets, flat or curved, for retinas, cortical sheets, skin |
| `Union`, `Difference` | constructive solid geometry |
| `mesh`, `voxel_mask` | triangle meshes and voxel masks (roadmap B2) |

Every geometry gives `contains(points)`, `sample(n, rng)`, `bounding_box()`, `local_coordinates(points)` and
`to_dict()`.

## Fields
Fields are values on space: morphogen gradients, layers, maps. A field is sampled at cell positions,
`field.sample(points)`, and can drive any stage parameter through a `Field` Param.

```python
from neurogenesis.fields.core import AnalyticField, LayerStackField

depth = AnalyticField("z")                                   # a linear gradient along z
layers = LayerStackField(depth, thicknesses=[0.2, 0.3, 0.5]) # three layers by depth
lw = layers.sample(pts)            # shape (n, 2): layer label, relative depth inside the layer (0..1)
label, rel_depth = lw[:, 0], lw[:, 1]
```

Operations (`Add`, `Threshold`, `GaussianSmooth`, `DistanceTransform`) build new fields from others; `maps`
provides orientation-like maps from pinwheel centres.

```{figure} ../_static/media/fields_geometry_gallery.png
:width: 98%

Three geometry and field primitives: (left) CSG `Difference(Box, Sphere)` sampled points in cutaway; (centre) a `LayerStackField` evaluated on a `CurvedSheet`; (right) an orientation `PinwheelField` with $\pm 1/2$ singularities recovered by `find_pinwheels`.
```

## Pinwheel orientation maps
```python
import numpy as np
from neurogenesis.fields import PinwheelField, find_pinwheels, pinwheel_map

centres = np.asarray([[3.0, 3.0], [7.0, 7.0], [3.0, 7.0], [7.0, 3.0]])
charges = np.asarray([0.5, 0.5, -0.5, -0.5])
_, angles, _ = pinwheel_map((np.zeros(2), np.full(2, 10.0)), 0.1, centres, charges)
found, recovered_charges = find_pinwheels(angles, [0.0, 0.0], 0.1)
```
See `examples/pinwheel_sheet.py` for a full semi-supervised schedule where cell proliferation and chemotactic migration
couple to hand-placed pinwheel centres.

## Stopping migration with a field
`migrate` evaluates `stop_field` at each candidate position and halts cells where the field is `True` or `> 0`:

```python
from neurogenesis.stages import run_schedule

project = {
    "geometry": {
        "box": {"type": "Box", "center": [5, 5, 5], "size": [10, 10, 10]},
        "seed_zone": {"type": "Box", "center": [5, 5, 1], "size": [8.4, 8.4, 1]},
    },
    "fields": {"stop": {"type": "AnalyticField", "expr": "z - (0.4 * x + 2.8)"}},
    "schedule": [
        {"name": "seed", "operator": "seed_cells", "params": {"N": 90, "geometry": "seed_zone"}},
        {"name": "migrate", "operator": "migrate", "repeat": 16,
         "params": {"direction": [0, 0, 1], "speed": 0.4,
                    "stop_field": {"type": "Field", "name": "stop"}, "boundary": "box"}},
    ],
}
checkpoints = run_schedule(project, {}, seed=0, checkpoints=True)
```

```{figure} ../_static/media/migrate_stop_field.gif
:width: 65%
:class: gif-demo

Cells seeded near $z = 1$ migrate upwards until they cross the slanted `stop_field` surface $z = 0.4x + 2.8$.
```
