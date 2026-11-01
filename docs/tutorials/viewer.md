# Tutorial 10 — The browser viewer

The viewer (`viz/`, TypeScript + three.js) shows networks in 3D and simulates them live in the browser with the same
integer kernel as Python (identical spikes).

```bash
cd viz
npm ci
npm run build:kernel
npm run dev          # http://localhost:5173
```

1. **Import** a network JSON (from `net.save_json(...)`, the CLI `generate` command, or `export-presets`).
2. Orbit, pan and zoom; click a neuron to inspect and edit its parameters.
3. Colour neurons by region, role, sign, mode or compartment.
4. Run the simulation; watch spikes in 3D and in the raster of selected populations.

```{figure} ../_static/media/viewer_network.png
:width: 85%

The grown topographic map of tutorial 2 (seed 0, 236 neurons, 124 synapses) imported into the viewer: sensor sheet
(left) and map (right).
```

```{figure} ../_static/media/viewer_raster.png
:width: 85%

The CLI column (`generate --neurons 500 --weight-scale 0.2 --refractory 3`) simulated live in the browser; white
neurons are spiking, and the population raster scrolls at the bottom right.
```

```{admonition} PLACEHOLDER
:class: placeholder
A GIF of the viewer simulating a network while the camera orbits (`docs/_scripts/viewer_capture.py` writes it, but
headless software-WebGL capture was too heavy for the documentation build machine; capture it on a desktop
with a GPU).
```

The viewer is the reference implementation of the browser kernel and the lightweight web demo. Full editors
(projects, geometry, fields, schedules) live in the desktop apps ({doc}`desktop-apps`).

```{admonition} PLACEHOLDER
:class: placeholder
A hosted web demo on GitHub Pages (the built viewer with preset networks), embedded in this page.
```
