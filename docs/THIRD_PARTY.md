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
| h5py (optional extra `sonata`) | BSD-3-Clause | SONATA export / import (`neurogenesis.interop`) |
| libsonata (tests only) | LGPL-3.0 | reference SONATA reader in the tests; never vendored |
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
| Topological Morphology Descriptor (TMD) | Kanari L et al. (2018). *Neuroinformatics*; BlueBrain/TMD (LGPL-3.0, https://github.com/BlueBrain/TMD); population statistics in morphOMICs (siegert-lab/morphOMICs, GPL-3.0, https://github.com/siegert-lab/morphOMICs) |
| Morphometric feature extraction | MorphoPy (berenslab/MorphoPy, MIT, https://github.com/berenslab/MorphoPy; JOSS 2020) |
| Continuous morphological phenotype space | Weis M, Hansel C, Ecker AS (2021). *arXiv:2112.12482*; ssl_neuron (MIT, https://github.com/marissaweis/ssl_neuron); functional continuum in DECEMber (PMC12155019) |
| Implicit morphology occupancy model (MorphOcc) | Continuous somatodendritic representation in $\mathbb{R}^{64}$ with PointNet encoder and MLP occupancy decoder (https://openreview.net/pdf/9efa243eba5e55a2d17681f38d6212cfa1690b3b.pdf) |
| Functional connectomics like-to-like wiring rule | MICrONS Consortium. Functional connectomics reveals general wiring rule in mouse visual cortex. *Nature* 640:8058 (2025) / *PMC11981947* / *Cell* 2025; curated tool inventory in awesome-connectomics (https://github.com/ceesem/awesome-connectomics) |
| Developmental sequence of cortical microcircuits | Ko H, Ho FER, Mrsic-Flogel TD et al. (2013). The emergence of functional microcircuits in visual cortex. *Nature* 496:96-100 (PubMed 23552948) |
| 2D Kolmogorov–Smirnov test | Fasano G, Franceschini A (1987). A multidimensional version of the Kolmogorov–Smirnov test. *Mon Not R Astron Soc* 225:155-170 |

## Data sources and licences
| Resource | Licence & Citation | Use |
|---|---|---|
| NeuroMorpho.Org | CC-BY-NC-SA (archive-specific terms); Ascoli GA et al. (2007). *J Neurosci* 27:9245-9251; http://neuromorpho.org | Public neuronal reconstruction repository; manifests under `datasets/morphology/` |
| MICrONS Multi-Area Connectome | CC-BY-4.0; MICrONS Consortium (2021, 2025); https://bossdb.org/project/microns-minnie | Functional connectomics and reconstruction data |
