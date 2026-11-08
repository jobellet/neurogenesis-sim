## Description
<!-- Provide a summary of the changes proposed in this Pull Request. -->

## Type of Change
- [ ] New Catalogue Circuit Card (`catalogue/*.json`)
- [ ] Core Engine / Developmental Mechanism
- [ ] Schema / Protocol / Bridges
- [ ] Bug Fix / Platform Support
- [ ] Documentation / Tutorial / Presets

## Invariants Checklist (AGENTS.md)
- [ ] **Determinism**: Same seed and parameters yield identical output across runs.
- [ ] **Backward Compatibility**: Existing plans, genomes, and schemas develop and load identically.
- [ ] **Kernel Equivalence**: Any change affecting spiking behavior matches across Python, JAX, Numba, nglif, and browser kernel.
- [ ] **Low-Compute Scale**: Scales linearly O(N) cells and O(E) synapses. Declared memory and operation counts verified.

## Catalogue Card Contributor Verification (if adding/modifying cards)
- [ ] Card format conforms to `neurogenesis-card/1`.
- [ ] Passed `validate_card()` validation checks.
- [ ] Author ORCID matches `^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$`.
- [ ] Paper DOI matches `^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$` (if provided).
- [ ] Deterministic reproduction on held-out seeds `[1000, 1001, 1002]` passes `pytest tests/test_catalogue_cards.py`.
- [ ] Remix loop verified via `pull()`: circuit accepts pharmacological and genetic perturbations.

## Verification Commands Run Locally
```bash
JAX_PLATFORMS=cpu pytest -q
pytest tests/test_catalogue_cards.py -v
```
