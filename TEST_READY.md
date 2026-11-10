# TEST_READY: End-to-End Interoperability Test Suite

The opaque-box, requirement-driven E2E test suite for `neurogenesis-sim` Phase J Interoperability (Task J3: NIR Exporter) and Milestone K4b (Delay Clip Lifting) is fully established, verified, and ready.

---

## 1. Test Execution Commands

To execute the full E2E test suite:
```bash
pytest tests/e2e/test_e2e_nir_and_interop.py -v
```

To execute quietly under low-compute CPU invariants:
```bash
JAX_PLATFORMS=cpu pytest -q tests/e2e/test_e2e_nir_and_interop.py
```

To run both unit and E2E interop test suites together:
```bash
pytest tests/test_interop.py tests/test_interop_sonata.py tests/e2e/ -q
```

---

## 2. Test Architecture & Coverage Summary

| Tier | Category | Target Threshold | Implemented Tests | Current Active / Passing | Pending Downstream Milestone |
|---|---|---|---|---|---|
| **Tier 1** | Equivalence Classes & Happy Paths | $\ge 5$ per feature (45 total) | 45 | 18 passing | 27 skipped (M1 / M2) |
| **Tier 2** | Boundary, Extreme & Error Conditions | $\ge 5$ per feature (45 total) | 45 | 21 passing | 24 skipped (M1 / M2) |
| **Tier 3** | Cross-Feature Pairwise Combinations | Cross-feature matrix | 6 | 0 passing | 6 skipped (M1) |
| **Tier 4** | Real-World System Workflows & CLI Pipelines | Real-world pipelines | 5 | 2 passing | 3 skipped (M1) |
| **Total** | **All Tiers** | **Comprehensive** | **101 tests** | **41 passed** | **60 skipped (0 failed)** |

*Note on Progressive Testability*: In compliance with repository guidelines, tests for features pending implementation in Milestone M1 (`export_nir`, `"nir"` in `_BUILTIN`) and Milestone M2 (`max_delay` parameter in `import_connectome`) are cleanly skipped with explicit milestone reasons. As soon as Workers M1 and M2 merge their changes, the remaining 60 tests activate automatically with zero test modifications required.

---

## 3. Feature Checklist Across Tiers 1–4

### Feature 1: J3 NIR Core Exporter (`export_nir(net, path, dt=1e-3, **opts)`)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_export_single_lif_neuron`: Single neuron export to `.nir`.
  - `test_tier1_export_two_neuron_feedforward`: Feedforward circuit export.
  - `test_tier1_export_recurrent_circuit`: Recurrent circuit export.
  - `test_tier1_export_cortical_column`: 300-neuron cortical column export.
  - `test_tier1_export_layered_network`: Layered network export.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_exporter_zero_neurons_raises_value_error`: Zero-neuron network raises `ValueError`.
  - `test_tier2_exporter_isolated_neurons_no_synapses`: Network with zero synapses.
  - `test_tier2_exporter_deep_directory_creation`: Auto-creates parent directories.
  - `test_tier2_exporter_path_types_str_and_path`: Both `str` and `Path` accepted.
  - `test_tier2_exporter_overwrite_existing_file`: Clean overwrite of destination file.
- [x] **Tier 3 (Cross-Feature)**:
  - `test_tier3_morphogenetic_tissue_to_nir_export`: Export tissue grown via developmental plan.
- [x] **Tier 4 (Real-World)**:
  - `test_tier4_cortical_column_300_end_to_end_nir`: Full round-trip validation with `nir.read`.
  - `test_tier4_layered_microcircuit_end_to_end_nir`: Full layered microcircuit validation.

### Feature 2: J3 Dynamics Mapping (LIF Parameters to `nir.CubaLIF`)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_dynamics_standard_lif_parameters`: Verified `tau_mem`, `tau_syn`, `v_leak`, `v_threshold`, `v_reset`, `r`.
  - `test_tier1_dynamics_varying_membrane_time_constant`: Verified `shift_v` mapping across 1–8.
  - `test_tier1_dynamics_varying_synaptic_time_constant`: Verified `shift_s` mapping across 1–8.
  - `test_tier1_dynamics_custom_voltage_scaling`: Verified custom `mV_per_unit`, `E_L`, `C_m`.
  - `test_tier1_dynamics_custom_dt`: Verified explicit `dt` step support.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_dynamics_extreme_thresholds`: Thresholds at 0 and 4096.
  - `test_tier2_dynamics_boundary_shift_v`: Extreme shifts (1 and 15).
  - `test_tier2_dynamics_boundary_shift_s`: Extreme shifts (1 and 15).
  - `test_tier2_dynamics_zero_refractory_period`: Refractory period = 0 ticks.
  - `test_tier2_dynamics_large_refractory_period`: Refractory period = 50 ticks.
- [x] **Tier 3 (Cross-Feature)**:
  - `test_tier3_recurrent_network_custom_dynamics`: Combined custom dynamics and recurrent feedback.

### Feature 3: J3 Connectivity Mapping (Dense Linear Weight Matrix & Graph Assembly)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_connectivity_input_node_created`: Input node with matching dimension.
  - `test_tier1_connectivity_output_node_created`: Output node with matching dimension.
  - `test_tier1_connectivity_feedforward_linear_matrix`: Dense linear weight matrix.
  - `test_tier1_connectivity_recurrent_linear_loop`: Cyclic edges `(lif -> w_rec -> lif)`.
  - `test_tier1_connectivity_inhibitory_synapse_negative_weights`: Preserves negative sign of inhibitory synapses.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_connectivity_all_to_all_dense_matrix`: Full $N \times N$ connectivity.
  - `test_tier2_connectivity_self_synapse_loop`: Autapses / self-loops.
  - `test_tier2_connectivity_extreme_weights_clamp`: Bounds at $\pm 2047$.
  - `test_tier2_connectivity_multi_synapses_same_pair`: Multiple synapses between identical (pre, post).
  - `test_tier2_connectivity_sparse_single_synapse`: Single active edge in large population.

### Feature 4: J3 Export Report (`ExportReport`)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_report_format_identifier`: Format name `"nir"`.
  - `test_tier1_report_node_and_edge_counts`: Node and edge counts match network.
  - `test_tier1_report_lossless_is_false`: Accurate report that NIR is not lossless.
  - `test_tier1_report_documents_approximated_dynamics`: Continuous dynamics documented.
  - `test_tier1_report_documents_dropped_delays`: Synaptic delay drop documented.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_report_zero_drivers_omits_driver_warning`: Clean report when no drivers present.
  - `test_tier2_report_all_poisson_drivers`: 100% Poisson population reported.
  - `test_tier2_report_all_burster_neurons`: 100% burster population reported.
  - `test_tier2_report_zero_delay_latency_note`: 0-tick latency documented.
  - `test_tier2_report_multi_word_delays_note`: Long delays documented.
- [x] **Tier 3 (Cross-Feature)**:
  - `test_tier3_heterogeneous_drivers_nir_report`: Mixed population reporting.
  - `test_tier3_extreme_delays_nir_dropped_accounting`: Delays dropped reporting.

### Feature 5: J3 Format Registry & Builtin (`core.py`)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_registry_formats_returns_list`: `formats()` returns list of available formats.
  - `test_tier1_registry_nir_in_formats`: `"nir"` registered in `_BUILTIN`.
  - `test_tier1_registry_export_network_delegation`: `export_network` delegates without manual import.
  - `test_tier1_registry_case_sensitivity`: Case-sensitive format matching.
  - `test_tier1_registry_custom_format_coexistence`: User format registration.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_registry_unknown_format_raises_value_error`: Unknown format error message.
  - `test_tier2_registry_empty_format_raises_value_error`: Empty string rejected.
  - `test_tier2_registry_import_unsupported_format_raises`: Write-only format import rejection.
  - `test_tier2_registry_duplicate_registration_overwrites`: Safe re-registration.
  - `test_tier2_registry_invalid_network_type_raises`: Non-network object rejected.

### Feature 6: J3 Packaging Extra (`pyproject.toml`)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_packaging_require_nir_succeeds`: `require("nir", "nir")` imports module.
  - `test_tier1_packaging_require_missing_error_message`: Instructional error message.
  - `test_tier1_packaging_pyproject_toml_extra`: Extra configuration present in `pyproject.toml`.
  - `test_tier1_packaging_nir_version_check`: `nir>=1.0.0` check.
  - `test_tier1_packaging_lazy_import_efficiency`: Lazy loading invariant.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_packaging_mock_missing_nir_raises_import_error`: Graceful error when `nir` uninstalled.
  - `test_tier2_packaging_corrupted_file_handling`: Corrupted file raises clean error.
  - `test_tier2_packaging_non_existent_extra_naming`: Helpful message for invalid extras.
  - `test_tier2_packaging_exception_chaining`: Preserves underlying cause.
  - `test_tier2_packaging_partial_module_mock`: Safe handling of partially initialized modules.

### Feature 7: K4b Delay Clip Lifting (`import_connectome`)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_k4b_delays_preserved_below_max`: Delays below threshold kept.
  - `test_tier1_k4b_custom_max_delay_parameter`: Accepts `max_delay` option.
  - `test_tier1_k4b_delays_clipped_to_custom_max`: Clamps to custom `max_delay`.
  - `test_tier1_k4b_counted_warning_emitted_when_clipped`: Emits counted warning.
  - `test_tier1_k4b_delays_at_least_one_tick`: Minimum delay is 1 tick.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_k4b_delay_equal_to_max_delay_no_warning`: No warning when delay == `max_delay`.
  - `test_tier2_k4b_delay_exceeding_max_delay_triggers_warning`: Warning triggered when delay > `max_delay`.
  - `test_tier2_k4b_zero_distance_clamped_to_one`: Clamping distance = 0 to 1 tick.
  - `test_tier2_k4b_negative_max_delay_rejected`: Invalid negative bound rejected.
  - `test_tier2_k4b_extreme_velocity_clamp`: Large velocity clamps to 1 tick.
- [x] **Tier 4 (Real-World)**:
  - `test_tier4_connectome_import_to_nir_pipeline`: Connectome import to NIR export pipeline.

### Feature 8: Documentation & Roadmap Synchronization
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_docs_readme_status_check`: Verifies `tests/test_readme_status.py`.
  - `test_tier1_docs_roadmap_phase_j_structure`: Validates Phase J section in `docs/ROADMAP.md`.
  - `test_tier1_docs_roadmap_k4b_status`: Validates K4b in `docs/ROADMAP.md`.
  - `test_tier1_docs_changelog_entries`: Validates `docs/changelog.md`.
  - `test_tier1_docs_format_docstring_accuracy`: Validates docstrings in `neurogenesis.interop`.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_docs_no_premature_done_status`: Verifies uncompleted tasks are not marked done.
  - `test_tier2_docs_task_ids_valid`: Validates roadmap task ID format.
  - `test_tier2_docs_changelog_header_dates`: Validates changelog format.
  - `test_tier2_docs_consistent_format_tables`: Verifies README layout table.
  - `test_tier2_docs_readme_badges_intact`: Verifies repository documentation badges.

### Feature 9: CLI Interop (`neurogenesis export` / `import`)
- [x] **Tier 1 (Happy Path)**:
  - `test_tier1_cli_export_nir_command`: Subcommand `neurogenesis export --format nir`.
  - `test_tier1_cli_export_prints_report_json`: Outputs report JSON to stdout.
  - `test_tier1_cli_export_with_ngb_input`: Accepts `.ngb` binary network format.
  - `test_tier1_cli_export_help_includes_command`: Help menu includes format options.
  - `test_tier1_cli_import_help_interface`: Help menu includes import options.
- [x] **Tier 2 (Boundaries & Errors)**:
  - `test_tier2_cli_non_existent_network_file_fails`: Exit code $\ne 0$ on missing file.
  - `test_tier2_cli_unknown_format_fails`: Exit code $\ne 0$ on unknown format.
  - `test_tier2_cli_missing_required_args_fails`: Exit code $\ne 0$ on missing arguments.
  - `test_tier2_cli_corrupted_json_fails`: Exit code $\ne 0$ on malformed JSON.
  - `test_tier2_cli_unwritable_destination_fails`: Exit code $\ne 0$ on unwritable path.
- [x] **Tier 3 (Cross-Feature)**:
  - `test_tier3_cli_generate_export_read_pipeline`: CLI generate $\rightarrow$ CLI export $\rightarrow$ NIR read.
- [x] **Tier 4 (Real-World)**:
  - `test_tier4_production_telemetry_report_serialization`: Validates JSON schema of report.
  - `test_tier4_complete_cli_subprocess_pipeline`: Complete CLI generate $\rightarrow$ stats $\rightarrow$ export pipeline.

---

## 4. Verification Method for Downstream Milestones
When Milestone M1 (J3 NIR Exporter) and Milestone M2 (K4b Delay Clip & Docs) are completed:
1. Run `pytest tests/e2e/test_e2e_nir_and_interop.py -v`.
2. Confirm: **101 passed, 0 failed, 0 skipped**.
