# Installation

## Desktop apps (no Python needed)
The native apps bundle their own pinned Python runtime (`desktop/common/runtime/build_runtime.py`) with the toolbox:

| Platform | Package | Build script / workflow |
|---|---|---|
| macOS (Apple silicon and Intel) | `.dmg` | `desktop/mac/release.sh` (`.github/workflows/release.yml`) |
| Windows 10 / 11 | setup `.exe` and portable `.zip` | `desktop/avalonia/packaging/build-windows.ps1` (`.github/workflows/avalonia-app.yml`) |
| Linux | `.AppImage` and `.tar.gz` | `desktop/avalonia/packaging/build-appimage.sh` (`.github/workflows/avalonia-app.yml`) |

Tagged releases (`v*`) attach installers and `.sha256` checksum files to the
[GitHub Releases](https://github.com/jobellet/neurogenesis-sim/releases) page. After downloading an archive, verify its
checksum before launching:

```bash
# macOS / Linux
shasum -a 256 -c Neurogenesis-*.sha256
```
```powershell
# Windows (PowerShell)
Get-FileHash .\Neurogenesis-Setup.exe -Algorithm SHA256
```

To build the embedded Python runtime or desktop packages locally from source, see {doc}`../tutorials/desktop-apps` and
`desktop/common/runtime/README.md`.

## Python package
Requirements: Python ≥ 3.10, `numpy`, `jax`, `matplotlib` (installed automatically).

Install directly from GitHub without cloning:

```bash
pip install "git+https://github.com/jobellet/neurogenesis-sim.git"
```

Or clone for development and testing:

```bash
git clone https://github.com/jobellet/neurogenesis-sim.git
cd neurogenesis-sim
pip install -e ".[test]"
```

For GPU simulation, install the CUDA build of JAX instead of the CPU one:

```bash
pip install -U "jax[cuda12]"
```

Optional dependency extras declared in `pyproject.toml`:

| Extra | Packages | Enables |
|---|---|---|
| `fast` | `numba>=0.59` | event-driven CPU kernel (`neurogenesis.spiking.numba_backend`) |
| `sonata` | `h5py` | SONATA circuit export / import (`neurogenesis.interop.sonata`) |
| `nir` | `nir>=1.0.0` | NIR graph export / import (`neurogenesis.interop.nir`) |
| `data` | `pyarrow` | Parquet and Feather connectome table streaming (`neurogenesis.data`) |
| `test` | `pytest`, `jsonschema`, `h5py`, `libsonata` (non-Windows), `numba`, `nir` | full test suite |

## Browser viewer
The viewer is a static web app (TypeScript + three.js) in `viz/`:

```bash
cd viz
npm ci
npm run build:kernel   # the browser spiking kernel, also needed by the Python equivalence tests
npm run dev            # http://localhost:5173
```

## Checking the installation
```bash
JAX_PLATFORMS=cpu pytest -q
python -m neurogenesis estimate --neurons 1e4 --synapses-per-neuron 100 --seconds 1
```

All tests should pass. The equivalence tests between the Python, JAX and browser kernels need
`npm run build:kernel`; the C kernel tests need a C compiler and CMake (see `desktop/common/native/nglif/README.md`).

## Building this documentation
```bash
pip install -r docs/requirements.txt
sphinx-build -b html docs docs/_build/html
```
The figures and animations are produced by `docs/_scripts/make_media.py` from real runs of the toolbox.
