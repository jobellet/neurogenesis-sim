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
The cross-platform desktop app (`desktop/avalonia/`, .NET 8 + Avalonia + Silk.NET) shares the C kernel `nglif`, NGB1
binary transport, `UI_SCHEMA.md`, and `visual_spec.json` with the macOS app.

```bash
# Build nglif native library
cmake -S desktop/common/native/nglif -B build/nglif -DCMAKE_BUILD_TYPE=Release
cmake --build build/nglif --config Release
ctest --test-dir build/nglif -C Release --output-on-failure

# Build and test the .NET solution
dotnet build desktop/avalonia/Neurogenesis.Desktop.sln --configuration Release
dotnet test desktop/avalonia/Neurogenesis.Desktop.sln --configuration Release --no-build
```

Packaging scripts produce standalone distributions with the embedded Python runtime:
- **Windows:** `powershell -ExecutionPolicy Bypass -File desktop/avalonia/packaging/build-windows.ps1 -OutputDir dist`
  (setup `.exe` via Inno Setup `setup.iss` and portable `.zip`).
- **Linux:** `./desktop/avalonia/packaging/build-appimage.sh dist` (AppImage and `.tar.gz`).

## Embedded Python runtime
To package a standalone relocatable Python runtime (`python-build-standalone` + hashed wheel lockfiles in
`desktop/common/runtime/locks/`) and smoke-test the bridge handshake in an isolated environment:

```bash
python desktop/common/runtime/build_runtime.py --target macos-arm64 --out build/runtime-macos-arm64
python desktop/common/runtime/smoke_test.py build/runtime-macos-arm64
```

Supported targets: `macos-x86_64`, `macos-arm64`, `linux-x86_64`, `linux-arm64`, `windows-x86_64`. See
`desktop/common/runtime/README.md` for details.

## Workspace overview
- **Viewport & inspector:** drag to orbit, scroll/pinch to zoom, select neurons to inspect membrane parameters (`mode`,
  `shift_v`, `shift_s`, `threshold`, `refractory`) and outgoing synapses, or inject current pulses during live `nglif`
  simulation.
- **Schema-driven editors:** Project, Geometry, Fields, Body plan, Genome, Schedule, Development checkpoints (scrubbing
  through every stage), Plasticity, Evolution, Modules, Cost (`estimate_development`), and Analysis panels are generated
  directly from `python -m neurogenesis ui-schema` ({doc}`../reference/ui-schema`).
- **Unsigned macOS first launch:** builds without a Developer ID signature open via right-click **Open → Open** (or
  **System Settings → Privacy & Security → Open Anyway**); see `desktop/mac/README.md`.
