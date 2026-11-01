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
