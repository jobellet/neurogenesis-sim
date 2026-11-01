# Neurogenesis for Mac

A native macOS app (Swift, SwiftUI and Metal) that drives the whole toolbox: it lets you build networks by hand or
from genes, step through development in 3D, and watch simulated activity live. It runs on Intel Macs with macOS 14 or
later and needs only the Command Line Tools, not Xcode.

```bash
./build.sh                 # compile, install in ~/Applications, add to the Dock
./build.sh --no-install    # build/Neurogenesis.app only
```

`NG_PYTHON` sets the Python to use. It needs numpy, jax and matplotlib, and by default the build picks the first such
Python it finds (conda first). `NG_REPO` sets the toolbox checkout the app imports: the app runs
`python -m neurogenesis.bridge` with that folder first on `PYTHONPATH`. It defaults to the repository's main worktree,
so work that other agents merge appears in the app. You can change both later in **Roadmap status → Python**. Shared
pieces (the protocol, and later the C kernel and UI schemas) are in `../common/` (see `../README.md`).

## How it works
| Part | File | What it does |
|---|---|---|
| Live kernel | `Sources/LIFKernel.swift` | The `lif_int` integer kernel. It gives identical spikes to `reference.py` and `jax_backend.py`, and `tests/test_desktop_kernel.py` checks this. It runs on its own thread (`SimEngine.swift`) at any speed, from 0.1× real time to maximum. |
| 3D view | `Sources/Renderer.swift`, `MetalView.swift` | Metal, instanced. Neurons flash when they spike, synapses light up when a presynaptic spike leaves, and region boxes and geometry sample clouds are drawn too. |
| Toolbox | `Sources/Bridge.swift` → `python -m neurogenesis.bridge` | A Python child process speaking JSON lines (`../common/PROTOCOL.md`). Networks travel as binary NGB1 files (float64 and int32), not JSON. |
| Panels | `Sources/Panels.swift` | Project (A1), Geometry (B1, B2), Fields (B3–B5), Body plan, Genome, Schedule (A3, A4, C1–C13), Development, Network, Simulation, Plasticity (E1), Evolution (E2, E3), Modules (G1), Cost (D3), Analysis (E4), and Roadmap status. |

**Placeholders.** The bridge checks which roadmap tasks are present in the checkout (`capabilities`). A task that has
not been merged yet appears as a dashed orange card that explains what it will do, and the sidebar shows its task ids.
Once the code is merged, **Roadmap status → Refresh** restarts Python, and the controls switch on without rebuilding
the app. For example, the schedule editor writes A4 entries (`{name, operator, params, repeat}`) with A3 Params
(`{"type": "Gene", "path": "a.b", "lo", "hi"}`), and **Run schedule** works as soon as the stages it uses are
registered.

**Resources.** Heavy actions are checked against this Mac before they run: growing a plan, generating a preset,
sampling cells, opening projects or networks, loading modules, evolution, other neuron models and plasticity. Each is
refused with an alert if it would need more than 60 % of the memory free right now (or half the RAM). The Python side
estimates from the inputs: legacy `grow()` builds dense Ns × Nd arrays, and every cell and synapse is a Python object.
The app side reads the network's size from the NGB1 header before loading it. *Body plan → Resources → Check* shows
the estimate, and *Roadmap status → This Mac* shows the machine.

## Using it
- **Navigate:** drag to orbit; shift-drag, right-drag or ⌘-drag to pan; scroll or pinch to zoom (on a trackpad,
  two-finger scrolling orbits). Double-click centres the view on a neuron. W A S D Q E move the camera, F frames
  everything.
- **Build by hand:** the toolbar tools are select (⌘1), add a neuron (⌘2), connect the selection to a target (⌘3) and
  stimulate (⌘4). The inspector edits every neuron field and every synapse. ⌫ deletes the selection, ⌘Z undoes.
- **Grow:** edit regions, projections and their main genes in **Body plan**, then press ⌘G. ⇧⌘G develops step by step,
  and you can scrub through the checkpoints in **Development**.
- **Simulate:** space or ⌘R runs and pauses; ⌘I drives the input neurons; ⌥-click a neuron to inject a current pulse.
  Other neuron models (`two_compartment`, `hh`) run in Python from **Simulation**.
- **Files:** open or drop a Project, body plan, module or network JSON. Networks you save also open in `viz/`.

## Tests
```bash
JAX_PLATFORMS=cpu pytest -q desktop/mac/tests tests/test_bridge.py
```
