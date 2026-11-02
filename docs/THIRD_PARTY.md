# Third-party software and prior work

Licences were read from the installed packages. This repository is under the MIT licence (`LICENSE`). Update this file
when a dependency, a copied snippet or a key reference is added.

## Code copied or adapted from elsewhere
None identified. The integer kernel, the viewer and the development engine were written for this project; the browser
sandbox has no attribution or licence header from another project.

## Software used at run time
| Package | Licence | Use |
|---|---|---|
| numpy | BSD-3-Clause | arrays, development |
| jax, jaxlib | Apache-2.0 | kernel on CPU / GPU, batching |
| matplotlib | Matplotlib licence (PSF-based) | rasters in the reference simulator |
| three (viewer) | MIT | 3D rendering (WebGL) |
| vite, typescript, esbuild, rollup and their small dependencies (build only) | MIT / Apache-2.0 / ISC / BSD-3-Clause | building the viewer |
| pytest, jsonschema (tests) | MIT | tests |
| sphinx, sphinx-rtd-theme, myst-parser, sphinx-copybutton (documentation build only) | BSD-2-Clause / MIT | the documentation site |
| GitHub Actions: actions/* (checkout, setup-python, setup-node, upload/download-artifact, upload-pages-artifact, deploy-pages), dorny/paths-filter, dawidd6/action-download-artifact | MIT | CI only, not distributed |

**Desktop app releases.** The embedded runtime (`desktop/common/runtime`, task H4) bundles a CPython build from
python-build-standalone (CPython: PSF License; its bundled libraries such as OpenSSL, SQLite, libffi and zlib keep
their own licences) and the Python packages above. Release bundles must ship those licence files (checked in H7).
The Windows / Linux app (Avalonia, CommunityToolkit.Mvvm, Silk.NET; MIT) lists its NuGet dependencies in
`desktop/avalonia/`.

The viewer loads the Inter and JetBrains Mono fonts from Google Fonts (SIL Open Font License 1.1); opening it sends a
request to Google's servers.

## Methods implemented from the literature
| Mechanism | Source |
|---|---|
| Leaky integrate-and-fire neurons | Lapicque L (1907); Gerstner W, Kistler WM, Naud R, Paninski L (2014). *Neuronal Dynamics* |
| Positional chemoaffinity (axons find targets from graded molecular labels) | Sperry RW (1963). *PNAS*; Eph / ephrin gradients reviewed in McLaughlin T, O'Leary DDM (2005). *Annu Rev Neurosci* |
| Lateral-inhibition differentiation (Notch–Delta) | Collier JR, Monk NAM, Maini PK, Lewis JH (1996). *J Theor Biol* |
| Laminar targeting of axons | Xiao T, Staub W, Robles E, Gosse NJ, Cole GJ, Baier H (2011). *Cell*; Robles E, Filosa A, Baier H (2013). *J Neurosci* |
| Island-model evolution | Whitley D, Rana S, Heckendorn RB (1999). *J Comput Inf Technol* |
