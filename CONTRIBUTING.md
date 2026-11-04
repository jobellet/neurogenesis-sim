# Contributing

## Code
- New developmental mechanisms are guidance rules (`neurogenesis.development.rules.register`) or new genome keys read by
  `grow`. They must be optional: a genome or plan that does not use them must grow exactly the same network as before.
- Development must stay deterministic: rules do not draw random numbers; any new random draw in `grow` changes every
  network and needs a new major version.
- Every change comes with a test; `pytest` must pass, including the kernel equivalence tests (`cd viz && npm run build:kernel`).

## Modules
A shared module is one `neurogenesis-module/1` JSON file (`Module.save`). It must contain:
- `inputs` and `outputs`: the regions driven by external currents and the regions read out, with a description of the
  input coding (which neuron receives what, at which current) in `description`;
- `validation`: the stimuli or task, the metric, the gate (the per-individual criterion of success), and the pass
  fraction and worst score on development seeds **never used** while the module was designed or evolved (at least 20,
  ideally 100);
- `provenance`: authors, source repository and commit, date, toolbox version.

A module is accepted when its validation can be rerun from these records with the toolbox alone.

## Profiles
A parameter profile (`examples/profiles/*.json`, see `docs/reference/profiles.md`) gives defaults for a species, a region
or an age; the toolbox never depends on one, and any value can be replaced by a `Gene`, a `Field` or a `Fit`. Every
parameter of a profile declares a status (`measured`, `derived`, `assumed` or `free`), what the number is (`quantity`),
and, when it comes from papers, the DOI and what was actually read (`full_text`, `abstract`, `title_only`,
`not_checked`). `python -m neurogenesis profile check --all` must pass; a test runs it on the shipped profiles. A value
applied to a species or region other than the one it was measured in is written as such in `note`.
A numeric stage parameter that users may draw from a gene or a `Fit` gets a range of validity in
`neurogenesis/stages/bounds.py`; `tests/test_stage_bounds.py` then runs the stage on random values and on the corners of
that range, and needs a harness for the new stage.
