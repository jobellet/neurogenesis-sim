# Installation

## Desktop apps (no Python needed)
The native apps bundle their own Python runtime and the toolbox:

| Platform | Package | Status |
|---|---|---|
| macOS (Apple silicon and Intel) | `.dmg` | in progress (roadmap task H4) |
| Windows 10 / 11 | setup `.exe` and portable `.zip` | in progress (task H5) |
| Linux | AppImage | in progress (task H5) |

```{admonition} PLACEHOLDER
:class: placeholder
Download links to the release page, checksums, and screenshots of the installer on each platform, once the first
release is tagged.
```

## Python package
Requirements: Python ≥ 3.10, numpy, jax, matplotlib (installed automatically).

```bash
git clone https://github.com/jobellet/neurogenesis-sim.git
cd neurogenesis-sim
pip install -e ".[test]"
```

For GPU simulation, install the CUDA build of JAX instead of the CPU one:

```bash
pip install -U "jax[cuda12]"
```

```{admonition} PLACEHOLDER
:class: placeholder
`pip install neurogenesis-sim` from PyPI and a conda-forge package, once the package is published.
```

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
