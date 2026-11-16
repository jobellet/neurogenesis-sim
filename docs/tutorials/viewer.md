# Tutorial 10 — The browser viewer

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/viewer.ipynb)

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

```{figure} ../_static/media/viewer_rotate.gif
:width: 85%
:class: gif-demo

The 500-neuron column running live in the browser viewer while the camera orbits (captured headless with `docs/_scripts/viewer_capture.py`).
```

The viewer is the reference implementation of the browser kernel and the lightweight web demo. Full editors
(projects, geometry, fields, schedules) live in the desktop apps ({doc}`desktop-apps`).

## Live browser demo
You can interact with the built 3D viewer directly below (loading a 1,000-neuron cortical column preset with the
bit-identical `lif_int` kernel) or [open it in a full tab](../_static/viewer/index.html?preset=column&no-modal):

```{raw} html
<div style="margin: 14px 0 22px 0; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; background: #070b14;">
  <iframe
    src="../_static/viewer/index.html?preset=column&no-modal"
    title="neurogenesis-sim 3D browser viewer"
    style="width: 100%; height: 540px; border: 0; display: block;"
    loading="lazy"
  ></iframe>
</div>
```
