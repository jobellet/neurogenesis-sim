# Test Infrastructure: Interoperability & E2E Verification

This document specifies the opaque-box, requirement-driven testing infrastructure for `neurogenesis-sim`, focusing on Phase J interoperability (Task J3: Neuromorphic Intermediate Representation / NIR output), Milestone K4b delay clipping, format registries, CLI workflows, and export reports.

---

## 1. Test Philosophy & Principles

1. **Opaque-Box Requirement-Driven Verification**:
   - Tests interact strictly through public APIs (`neurogenesis.interop.export_network`, `import_network`, `formats`, `require`, `neurogenesis.data.import_connectome`, and the CLI `neurogenesis export` / `import`).
   - Tests never depend on private variables, internal stage state, or unexported functions.
   - Every test case validates a documented functional requirement from `PROJECT.md`, `docs/ROADMAP.md` §4 Phase J (J1, J2, J3) and K4b.

2. **Progressive Testability & Graceful Dependency Decoupling**:
   - Tests are modular and progressive. If optional dependencies (e.g., `nir`, `h5py`, `pyarrow`) are missing, or if downstream milestones are in-flight, tests gracefully isolate behaviors using standard testing contracts, verifying both installed behavior and missing-dependency error contracts (`require`).
   - When `nir` is installed, full graph round-trips via `nir.read`, node inspection, and serialization checks are executed.

3. **Self-Contained & Isolated State**:
   - Every test constructs its own network topologies or uses independent pytest fixtures (`tmp_path`).
   - Zero side-effects across tests: files created during export are isolated in temporary test directories.
   - Determinism invariant: all tests run deterministically with zero unseeded random state.

4. **Explicit Authoritative Expected Output**:
   - Physical and mathematical properties govern expected dynamics parameters ($V_{th} = E_L + s \cdot v$, $\tau_m = -1 / \ln(1 - 2^{-\text{shift}_v})$, $R = \tau_m / C_m$).
   - Graph structures, matrix dimensions, node naming, edge tuples, and JSON reports are checked against explicit specification contracts.

---

## 2. Feature Inventory & Coverage Matrix

The test infrastructure covers all features defined in `PROJECT.md § Feature Inventory`:

| # | Feature | Scope | Tier 1 (>=5) | Tier 2 (>=5) | Tier 3 (Cross) | Tier 4 (System) |
|---|---------|-------|--------------|--------------|----------------|-----------------|
| **1** | J3 NIR Core Exporter | `export_nir` via `export_network` | 5 | 5 | Yes | Yes |
| **2** | J3 Dynamics Mapping | LIF parameters to `nir.CubaLIF` | 5 | 5 | Yes | Yes |
| **3** | J3 Connectivity Mapping | Dense weights to `nir.Linear` / graph | 5 | 5 | Yes | Yes |
| **4** | J3 Export Report | Exact, approximated, dropped reporting | 5 | 5 | Yes | Yes |
| **5** | J3 Format Registry & Builtin | `formats()`, `_BUILTIN`, dynamic loading | 5 | 5 | Yes | Yes |
| **6** | J3 Packaging Extra | `pyproject.toml` extra, `require()` | 5 | 5 | Yes | Yes |
| **7** | K4b Delay Clip Lifting | Configurable `max_delay` in `import_connectome` | 5 | 5 | Yes | Yes |
| **8** | Roadmap & Docs Sync | Status consistency across documentation | 5 | 5 | Yes | Yes |
| **9** | Interop CLI & Round-Trip | CLI `export` / `import` subcommands | 5 | 5 | Yes | Yes |

---

## 3. Test Architecture & Runner

### 3.1 Directory Layout
```
tests/e2e/
├── __init__.py                       # Package marker
├── conftest.py                       # Fixtures: synthetic networks, columns, connectome data
└── test_e2e_nir_and_interop.py       # Comprehensive Tiers 1-4 test suite
```

### 3.2 Test Runner Command
To execute the E2E test suite alone:
```bash
pytest tests/e2e/ -v
```

To execute the entire project test suite adhering to low-compute CPU execution invariants:
```bash
JAX_PLATFORMS=cpu pytest -q
```

### 3.3 Fixture Architecture (`tests/e2e/conftest.py`)
- `single_neuron_net`: Minimal network with 1 LIF neuron, default dynamics.
- `two_neuron_feedforward_net`: 2 LIF neurons connected by 1 excitatory synapse with delay.
- `recurrent_net`: 2 neurons with reciprocal synapses and 1 self-connection loop.
- `mixed_drivers_net`: Heterogeneous population containing standard LIF neurons, Poisson driver (`mode=1`), and burster (`mode=2`).
- `cortical_column_net`: Morphogenetic column (300 neurons) generated via `MorphogeneticEngine`.
- `layered_net`: Layered cortical sheet network (48+ neurons) generated via `MorphogeneticEngine`.
- `toy_connectome_files`: Isolated temporary directory with CSV tables for `import_connectome`.

---

## 4. Test Tiers & Specifications

### Tier 1: Equivalence Classes & Happy Path (>= 5 tests per feature)
- **Feature 1 (Core Exporter)**:
  1. `test_tier1_export_single_lif_neuron`: Exports 1-neuron network to `.nir` file.
  2. `test_tier1_export_two_neuron_feedforward`: Exports 2-neuron feedforward circuit.
  3. `test_tier1_export_recurrent_circuit`: Exports recurrent circuit with feedback loop.
  4. `test_tier1_export_cortical_column`: Exports 300-neuron column with dense connectivity.
  5. `test_tier1_export_layered_network`: Exports multi-layered network topology.
- **Feature 2 (Dynamics Mapping)**:
  1. `test_tier1_dynamics_standard_lif_parameters`: Verifies `tau_mem`, `tau_syn`, `v_leak`, `v_threshold`, `v_reset`, `r`.
  2. `test_tier1_dynamics_varying_membrane_time_constant`: Verifies `shift_v` mapping across 1 to 8.
  3. `test_tier1_dynamics_varying_synaptic_time_constant`: Verifies `shift_s` mapping across 1 to 8.
  4. `test_tier1_dynamics_custom_voltage_scaling`: Verifies custom `mV_per_unit`, `E_L`, and `C_m`.
  5. `test_tier1_dynamics_custom_dt`: Verifies explicit `dt` passed to CubaLIF.
- **Feature 3 (Connectivity Mapping)**:
  1. `test_tier1_connectivity_input_node_created`: Verifies NIR `Input` node with shape `(N,)`.
  2. `test_tier1_connectivity_output_node_created`: Verifies NIR `Output` node with shape `(N,)`.
  3. `test_tier1_connectivity_feedforward_linear_matrix`: Verifies linear weight dimension and PSC current scale.
  4. `test_tier1_connectivity_recurrent_linear_loop`: Verifies recurrent edge `(lif -> w_rec -> lif)`.
  5. `test_tier1_connectivity_inhibitory_synapse_negative_weights`: Verifies sign fidelity for inhibitory synapses.
- **Feature 4 (Export Report)**:
  1. `test_tier1_report_format_identifier`: Verifies `report.format == "nir"`.
  2. `test_tier1_report_node_and_edge_counts`: Verifies `report.counts` matches neurons and synapses.
  3. `test_tier1_report_lossless_is_false`: Verifies `report.lossless is False`.
  4. `test_tier1_report_documents_approximated_dynamics`: Verifies explanation in `report.approximated`.
  5. `test_tier1_report_documents_dropped_delays`: Verifies delay omission is documented.
- **Feature 5 (Format Registry)**:
  1. `test_tier1_registry_nir_in_formats`: Verifies `"nir"` in `formats()`.
  2. `test_tier1_registry_builtin_resolution`: Verifies dynamic loading of `neurogenesis.interop.nir`.
  3. `test_tier1_registry_export_network_delegation`: Verifies `export_network(net, "nir", path)` delegates cleanly.
  4. `test_tier1_registry_case_sensitivity`: Verifies lowercase canonical naming.
  5. `test_tier1_registry_custom_format_coexistence`: Verifies custom format registration alongside NIR.
- **Feature 6 (Packaging Extra)**:
  1. `test_tier1_packaging_require_nir_succeeds`: Verifies `require("nir", "nir")` returns module.
  2. `test_tier1_packaging_require_missing_error_message`: Verifies clear error message for missing module.
  3. `test_tier1_packaging_pyproject_toml_extra`: Verifies `nir>=1.0.0` in `pyproject.toml`.
  4. `test_tier1_packaging_lazy_import_efficiency`: Verifies importing `neurogenesis` does not eager-import `nir`.
  5. `test_tier1_packaging_nir_version_check`: Verifies `nir.__version__` is at least 1.0.0.
- **Feature 7 (K4b Delay Clipping)**:
  1. `test_tier1_k4b_delays_preserved_below_max`: Delays below bound are preserved.
  2. `test_tier1_k4b_custom_max_delay_parameter`: `import_connectome` accepts `max_delay` option.
  3. `test_tier1_k4b_delays_clipped_to_custom_max`: Delays above bound are clamped to `max_delay`.
  4. `test_tier1_k4b_counted_warning_emitted_when_clipped`: Warnings emitted only when clipping occurs.
  5. `test_tier1_k4b_delays_at_least_one_tick`: Minimum delay is strictly $\ge 1$.
- **Feature 8 (Roadmap & Docs Sync)**:
  1. `test_tier1_docs_readme_status_check`: Verifies `tests/test_readme_status.py` passes.
  2. `test_tier1_docs_roadmap_phase_j_structure`: Validates Phase J entry in `docs/ROADMAP.md`.
  3. `test_tier1_docs_roadmap_k4b_status`: Validates K4b entry in `docs/ROADMAP.md`.
  4. `test_tier1_docs_changelog_entries`: Validates changelog notes.
  5. `test_tier1_docs_format_docstring_accuracy`: Validates docstrings in `neurogenesis.interop`.
- **Feature 9 (CLI Interop)**:
  1. `test_tier1_cli_export_nir_command`: Invocable via `neurogenesis export net.json --format nir --out net.nir`.
  2. `test_tier1_cli_export_prints_report_json`: Validates JSON stdout output from CLI export.
  3. `test_tier1_cli_export_with_ngb_input`: CLI accepts `.ngb` input files.
  4. `test_tier1_cli_export_help_includes_nir`: `--help` lists `nir` as format choice.
  5. `test_tier1_cli_import_command_interface`: Invocable via `neurogenesis import --format <fmt>`.

---

### Tier 2: Boundary, Extreme, and Error Conditions (>= 5 tests per feature)
- **Feature 1**: 0 neurons raises ValueError; isolated neurons (0 synapses); deep output directory auto-creation; string vs Path inputs; overwrite existing file.
- **Feature 2**: Extreme threshold (0, 4096); extreme shift_v (1, 15); extreme shift_s (1, 15); zero refractory; large refractory (50 ticks).
- **Feature 3**: All-to-all dense connectivity; self-synapse loops; extreme weights (maximum integer range $\pm 2047$); multi-synapses between pre/post; sparse single-synapse network.
- **Feature 4**: Zero-driver report (omits driver explanation); 100% Poisson driver report; 100% burster report; zero delay report (1 ms latency); massive delays report.
- **Feature 5**: Unknown format raises `ValueError` with suggestions; empty format string; import on write-only format; duplicate format registration; invalid network type.
- **Feature 6**: Mocked missing `nir` package raises `ImportError` on export; corrupted NIR file raises DataError; non-existent extra names; missing module traceback; mock partial package failure.
- **Feature 7**: Delay exactly equal to `max_delay` triggers NO warning; delay equal to `max_delay + 1` triggers warning; zero-distance soma delay clamp; negative `max_delay` rejection; extreme velocity clamp.
- **Feature 8**: Premature "done" markers rejection; broken internal links; changelog date formatting; stage reference table alignment; cost declaration documentation.
- **Feature 9**: Non-existent network file exit code; invalid format exit code; missing required CLI arguments; corrupted JSON file; read-only destination directory handling.

---

### Tier 3: Cross-Feature Pairwise Combinations
1. **Recurrent Network + Custom Dynamics**: Export recurrent network with non-default `mV_per_unit`, `E_L`, and `dt`.
2. **Heterogeneous Drivers + NIR Report**: Export network containing LIF, Poisson, and burster cells; verify CubaLIF node parameters and report dropped notes.
3. **Extreme Conduction Delays + NIR Dropped Accounting**: Export network with multi-word delays (K4/K4b); verify graph and report consistency.
4. **Multi-Stage Morphogenetic Tissue + NIR Export**: Export network grown via multi-stage developmental plan (axons, pruning, myelination) to NIR.
5. **Dual-Format Consistency**: Export the identical network to both SONATA and NIR; verify weight polarity, neuron counts, and dynamics parameters match between exports.
6. **CLI End-to-End Pipeline**: CLI generate -> CLI export -> NIR graph read-back and topological verification.

---

### Tier 4: Real-World System Scenarios
1. **Cortical Column (300 neurons) End-to-End**:
   - Generate cortical column via `MorphogeneticEngine`.
   - Export to `.nir`.
   - Read via `nir.read` and verify nodes (`Input`, `CubaLIF`, `Linear`, `Output`), edges, and weight matrix dimensions $(300 \times 300)$.
2. **Layered Microcircuit End-to-End**:
   - Generate layered microcircuit.
   - Export to `.nir` and verify feedforward and feedback connections.
3. **Connectome-to-NIR Pipeline**:
   - Import connectome data via `import_connectome`.
   - Convert to `SNNNetwork`.
   - Export to `.nir` and verify topology preservation.
4. **Telemetry & Report Serialization**:
   - Validate full JSON schema of `ExportReport.to_dict()` across production pipelines.
5. **Full CLI Pipeline**:
   - Subprocess invocation of `python -m neurogenesis generate` followed by `python -m neurogenesis export`.

---

## 5. Verification & Acceptance Criteria
- 100% of tests in `tests/e2e/test_e2e_nir_and_interop.py` compile and execute cleanly.
- Tests respect progressive testability: tests verify contract fulfillment and gracefully isolate pending milestone implementations.
- No flaky tests, no unseeded randomness, zero disk leaks outside `tmp_path`.
