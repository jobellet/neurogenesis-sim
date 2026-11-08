# Tutorial 11 — Desktop apps

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/jobellet/neurogenesis-sim/blob/main/notebooks/tutorials/desktop-apps.ipynb)

Native apps for macOS (SwiftUI + Metal) and for Windows and Linux (Avalonia, one C# code base). They need no Python
installation: each bundles a Python runtime with the toolbox.

| Layer | Shared by every app |
|---|---|
| Python bridge | `python -m neurogenesis.bridge`: development, evolution, modules, projects ({doc}`../reference/bridge-protocol`) |
| C kernel `nglif` | live simulation with spikes identical to Python, JAX and the browser, checked against golden fixtures |
| NGB1 | binary network files, int32 indices, optional extension columns |
| UI schema | panels for stages, Params, models and genes are generated from the toolbox, not hand-written ({doc}`../reference/ui-schema`) |
| Visual spec | one colour and style specification for every app |

Because the apps learn stages, Params and models from the toolbox at run time, a stage merged in Python appears in
every app without changing the apps.

## macOS
```bash
cd desktop/mac && ./build.sh        # developer build; a signed .dmg is produced by the release workflow
```

## Windows and Linux
See `desktop/avalonia/README.md` (in progress, roadmap task H5).

```{admonition} PLACEHOLDER
:class: placeholder
Screenshots of each app (network view, inspector, live development preview, schedule editor generated from the UI
schema, evolution progress), a GIF of growing and simulating a project end to end, and installation instructions
for the released packages.
```
