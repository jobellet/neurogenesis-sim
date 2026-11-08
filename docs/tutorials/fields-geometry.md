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

```{admonition} PLACEHOLDER
:class: placeholder
Figures: a gallery of geometries (sampled points), a layer stack painted on a curved sheet, and a pinwheel map with
its charges; a GIF of cells migrating along a gradient until a stop field. Tutorial for painting fields in the
desktop apps' field painter.
```
