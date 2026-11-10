# Project: neurogenesis-sim Roadmap Next Task (J3 NIR Output Format & Docs Sync)

## Architecture
- **Package**: `neurogenesis.interop`
  - `core.py`: Registry and `ExportReport` dataclass, lazy format loader, `require` helper. Registered `"nir"`.
  - `dynamics.py`: Canonical translation of integer LIF dynamics into continuous parameters (`lif_params`).
  - `nir.py`: Implementation of J3 NIR exporter (`export_nir`) and importer (`import_nir`), mapping LIF parameters to `nir.CubaLIF`, genuine driver input separation, building `nir.NIRGraph` with input/output and linear weight edges, saving to `.nir` files.
- **CLI & Configuration**:
  - `neurogenesis/cli.py`: CLI export subcommand supporting `--format nir`.
  - `pyproject.toml`: Optional dependency extra `nir = ["nir>=1.0.0"]`.
- **Documentation**:
  - `README.md`, `docs/ROADMAP.md`, `docs/changelog.md`.

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|--------|
| 1 | J3 NIR Core Exporter | `export_nir(net, path, dt=1e-3, **opts)` in `neurogenesis/interop/nir.py` | M1 | `docs/ROADMAP.md` §4 J3 | DONE |
| 2 | J3 Dynamics Mapping | Mapping `lif_params` to `nir.CubaLIF` (tau_mem, tau_syn, v_threshold, v_reset, v_leak, r, dt) | M1 | `neurogenesis.interop.dynamics` | DONE |
| 3 | J3 Connectivity Mapping | Assembling dense linear weight matrices into `nir.Linear` and building `nir.NIRGraph` | M1 | `docs/ROADMAP.md` §4 J3 | DONE |
| 4 | J3 Export Report | Honest reporting of exact, approximated (delays, integer dynamics), and dropped (drivers) | M1 | `neurogenesis.interop.core` | DONE |
| 5 | J3 Registry & Builtin | Registering `"nir"` format and adding `"nir"` to `_BUILTIN` in `core.py` | M1 | `neurogenesis.interop.core` | DONE |
| 6 | J3 Packaging Extra | Adding `nir = ["nir>=1.0.0"]` under `[project.optional-dependencies]` in `pyproject.toml` | M1 | `pyproject.toml` | DONE |
| 7 | K4b Delay Clip Lifting | Configurable `max_delay: int = 255` in `importer.py` | M2 | Scoped out per AGENTS.md invariant | SCOPED OUT |
| 8 | Roadmap & README Sync | Sync `docs/ROADMAP.md`, `README.md`, and `docs/changelog.md` (J3 done, C18 done) | M2 | `tests/test_readme_status.py` | IN_PROGRESS |
| 9 | Comprehensive E2E Test Suite | Requirement-driven test suite validating CLI, round-trips, report fidelity, and error cases | M3 | Dual Track E2E | IN_PROGRESS |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: J3 NIR Exporter | `neurogenesis/interop/nir.py`, `core.py`, `pyproject.toml` | none | DONE |
| 2 | M2: Roadmap & Docs Sync | `docs/ROADMAP.md`, `README.md`, `docs/changelog.md` | M1 | IN_PROGRESS |
| 3 | M3: Full Verification & Push | Run full repo tests, final audit, git commit & push directly to origin/main | M1, M2 | PLANNED |

## Interface Contracts
### `neurogenesis.interop.nir` ↔ `neurogenesis.interop.core`
- `export_nir(net: SNNNetwork, path: Union[str, Path], dt: float = 1e-3, population: str = "ngs", drivers: str = "keep", **opts) -> ExportReport`
- Input: `net` (SNNNetwork instance or path), destination `path` (.nir file), optional `dt` (seconds), `drivers` ("keep", "input", "drop"), `mV_per_unit`, `E_L`, `C_m`.
- Output: `ExportReport` with format `"nir"`, `exact`, `approximated`, `dropped`, and `counts`.
- Errors: Raises `ImportError` via `require("nir", "nir")` if `nir` package is not installed; raises `ValueError` if network has 0 LIF neurons or $N > 2048$.

### `neurogenesis.interop.nir` ↔ `nir` library
- Node types used: `nir.CubaLIF`, `nir.Linear`, `nir.Input`, `nir.Output`, `nir.NIRGraph`.
- Graph construction:
  - When `drivers == "keep"`: `Input -> Linear (feedforward) -> CubaLIF -> Output` (with recurrent loop if recurrent synapses exist).
  - When `drivers == "input"`: `Input (K driver channels) -> Linear (input_linear, shape N_lif x K) -> CubaLIF -> Output` (driver somas excluded from CubaLIF).
- Serialization: `nir.write(path, nir_graph)`.
