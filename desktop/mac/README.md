# Neurogenesis for Mac

A native macOS app (Swift, SwiftUI and Metal) that drives the whole toolbox: it lets you build networks by hand or
from genes, step through development in 3D, and watch simulated activity live.

## Install (users)
1. Download `Neurogenesis-<version>-macos-arm64.dmg` for Apple Silicon, or `…-macos-x86_64.dmg` for Intel. They are on
   the project's GitHub Releases page, or in the artifacts of the Release workflow. Check your Mac with  → About This
   Mac → Chip / Processor.
2. Open the disk image and drag **Neurogenesis** to **Applications**.
3. Open it. That's all: no Python, Homebrew or Xcode is needed. The app carries its own Python with the toolbox
   (about 500 MB installed).

**First launch of an unsigned build.** Builds made without a Developer ID (see Signing below) are blocked by macOS
the first time. Right-click the app and choose **Open**, then **Open**. Alternatively, open **System Settings → Privacy
& Security** and click **Open Anyway**. This is needed once.

**First start.** The first start takes up to a minute while macOS checks the app's libraries. Later starts take a few
seconds.

## Build (developers)
macOS 14 or later and the Command Line Tools are enough, without Xcode.

```bash
./build.sh                 # compile, install in ~/Applications, add to the Dock (uses a Python on this Mac)
./build.sh --no-install    # build/Neurogenesis.app only
./release.sh               # release build: embedded runtime, signature if configured, build/Neurogenesis-<v>-macos-<arch>.dmg
```

**Development builds** (`build.sh`) use a Python already on this Mac and a toolbox checkout:
- `NG_PYTHON` sets the Python to use. It needs numpy, jax and matplotlib, and by default the build picks the first
  such Python it finds (conda first).
- `NG_REPO` sets the toolbox checkout the app imports: the app runs `python -m neurogenesis.bridge` with that folder
  first on `PYTHONPATH`. It defaults to the repository's main worktree, so work that other agents merge appears in the
  app.
- You can change both later in **Roadmap status → Python**.

**Release builds** (`release.sh`) embed the runtime of `../common/runtime` (locked packages, pinned CPython):
- They never point at a checkout: `release.sh` refuses a build whose `Info.plist` names one.
- They always run their embedded Python. Stored settings do not change it, and nothing falls back to another
  Python: if the runtime is missing, the app says to reinstall it.
- *Roadmap status → Python* shows the runtime read-only.

### Signing and notarisation
Without credentials, `release.sh` signs ad hoc. The app then runs on any Mac, after the right-click → Open step
above. To ship a build that opens with a double-click, you need:

| What | Where | How to get it |
|---|---|---|
| A Developer ID Application certificate | Apple Developer Program (paid), Certificates → "Developer ID Application" | Export it from Keychain Access as a `.p12` with a password. |
| `MACOS_CERT_P12`, `MACOS_CERT_PASSWORD` | GitHub repository secrets | The `.p12` encoded with `base64 -i cert.p12`, and its password. |
| `MACOS_SIGN_IDENTITY` | secret, or environment variable for local builds | `Developer ID Application: Your Name (TEAMID)`, as `security find-identity -v -p codesigning` lists it. |
| `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` | secrets | An Apple ID, its team, and an app-specific password (appleid.apple.com → Sign-In and Security). They enable notarisation and stapling. |

With these set, `release.sh`:
- signs every Mach-O inside with the hardened runtime and `entitlements.plist`;
- signs the app and the disk image;
- notarises and staples the disk image.

The entitlements allow JIT memory, which JAX needs, and libraries signed by other teams, which Python's extension
modules are. Never commit certificates or passwords: they belong only in secrets or in your keychain.

## How it works
| Part | File | What it does |
|---|---|---|
| Live kernel | `../common/native/nglif` (C), `Sources/SimEngine.swift` | The shared C kernel `nglif`, imported into Swift through its module map. It gives identical spikes to `reference.py` and `jax_backend.py` on the golden fixtures (`tests/test_swift_binding.py` checks the Swift side). It runs on its own thread at any speed, from 0.1× real time to maximum. |
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
JAX_PLATFORMS=cpu pytest -q desktop/mac/tests tests/test_bridge.py tests/test_nglif_fixtures.py
```
