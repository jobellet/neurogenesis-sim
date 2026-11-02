# AGENTS.md: guide for agents working on neurogenesis-sim

## What this repository is
A general toolbox to grow spiking neural networks from genes and hand-made specifications, simulate them cheaply, and
share working circuits as modules. The target is in `README.md` and the plan in `docs/ROADMAP.md`. **Pick one task from
the roadmap (e.g. "C4 migrate"), and stay within its scope.**

## Before you start
0. Get the overview in one read. `python scripts/build_context.py` writes two Markdown files built from the
   documentation (also published on the documentation site and as the `ai-context` artifact of the docs workflow):
   - `neurogenesis-sim-brief.md` (about 11k tokens): project status, README, core concepts, design principles, these
     rules, the CLI and a map of the package. Read it first.
   - `neurogenesis-sim-context.md` (about 70k tokens): the same status section, then every documentation page (roadmap,
     stage reference, formats, protocols, tutorials) in one file.

   Their first section is generated: commit, registered stages, open pull requests, and everything the docs mark as
   partial, not done, PLACEHOLDER or **Not implemented**. Check there that your task is not already done or in an open
   pull request. Both files are generated: never edit or commit them.
1. Read `README.md`, `docs/ROADMAP.md` (sections 1–3 and your task), `docs/EXTENDING.md`, `docs/NEURON_MODELS.md`.
2. Install and run the tests:
   ```
   pip install -e ".[test]"
   cd viz && npm ci && npm run build:kernel && cd ..   # browser kernel, for the equivalence tests
   JAX_PLATFORMS=cpu pytest -q
   ```
   All tests must pass before and after your change, and none may be skipped (CI fails on skipped kernel tests).
3. Work on a branch `task/<id>-<short-name>` and open a pull request that names the task id. Do not push to `main`.

## Invariants: never break these
- **Determinism.**
  - Same inputs and seed give identical outputs.
  - Development randomness comes only from the random streams given to a stage (`rng` argument, one stream per stage,
    see roadmap §2.1).
  - Rules (`neurogenesis.development.rules`) never draw random numbers.
  - Never use global NumPy random state, `random`, or time.
  - `legacy_stream` mode in `run_schedule()` exists exclusively for backward compatibility with legacy plans (fingerprints).
    New schedules must never use `legacy_stream=True`: it breaks the one-stream-per-stage isolation rule.
- **Backward compatibility.**
  - Existing plans and genomes must grow the same networks: `tests/test_development.py` and the legacy-compiler
    fingerprints of task A5.
  - New options are off by default.
  - If a change must alter existing networks, stop and ask the maintainer.
- **Kernel equivalence.** `lif_int` gives identical spikes in Python (`spiking/reference.py`), JAX
  (`spiking/jax_backend.py`), the browser (`viz/src/sim/kernel.ts`), and the portable C kernel `nglif` (`desktop/common/native/nglif/`). Any change to one must be made to all four,
  with the equivalence tests passing.
- **Desktop apps & shared contracts ownership.**
  - Jules agents never edit `desktop/mac/` (owned by the Mac agent) nor `desktop/avalonia/` (owned by the Avalonia agent).
  - `desktop/common/` and `neurogenesis/bridge/` are shared contracts (protocol, NGB1 binary network format, UI schema, visual spec, C kernel `nglif`, golden fixtures, runtime scripts).
  - Change them only in dedicated tasks with a version bump, an updated spec, and all apps' CI passing.
- **Protocol & schema versioning.** Any change to `desktop/common/PROTOCOL.md`, `UI_SCHEMA.md` or Project schema requires backward compatibility, explicit versioning and migration tests.
- **Generality.** No species, organ, task or environment names inside `neurogenesis/`. Use them only in `examples/`,
  in tests as toy content, or in separate module repositories.
- **Contracts.** The Project schema (A1), `Tissue` (A2), `Param` (A3) and the Stage interface (A4) are shared.
  - Change them only within those tasks, or in a dedicated PR that updates every user and the schema version.
  - A change to a contract must also update the docs, migrations and tests.

## Low-compute rules
- Scale linearly: O(N) cells, O(E) synapses.
  - Local interactions go through the shared cell list (task D1).
  - No dense N × N or Ns × Nd arrays except below a documented threshold (state it in the docstring, e.g. `N <= 2048`).
- Use struct-of-arrays, float32 (int32 for the integer kernel), vectorised NumPy or JAX, and no Python loops over
  cells or synapses in hot paths.
- Every stage and model declares its cost (bytes and operations as functions of N, E and its parameters).
  `neurogenesis.cost` uses this before running and refuses what cannot fit. Add a test that the declared cost is within
  a factor 3 of measurement.
- Prefer the CPU path working everywhere: GPUs must be optional, and results must not depend on the device beyond
  floating-point tolerance (integer paths are exact).

## How to add things
| You add... | Where | Must also |
|---|---|---|
| a developmental stage | `neurogenesis/stages/<name>.py`, `@register_stage` | params as `Param`s, cost declaration, neutral parameters = no-op, toy-tissue behaviour test, a docs entry |
| a guidance / placement / weight rule | `neurogenesis/development/rules.py` or a plugin, `@register(phase, name)` | inactive without its genes; listed in the plan's rules; test |
| a neuron model | `neurogenesis/spiking/models/<name>.py`, `register_model` | use `base.drivers` and `base.transmit`; `state_bytes`, `flops`, `substeps`; known-property tests; add to the parametrised tests in `tests/test_models.py` |
| a geometry or field type | `neurogenesis/geometry/`, `neurogenesis/fields/` | JSON round trip through the Project schema; sampling test |
| a GUI panel | `viz/src/ui/` | reads and writes Project files only (no hidden state); `npm run build` passes |
| an example | `examples/<name>.py` | runs on a laptop CPU in under ~5 min; a test in `tests/test_examples.py` |

## Style
- Match the surrounding code: concise docstrings that say what a function does and its units, few comments, and names
  that say what things are.
- Biological mechanisms in docstrings cite their source (first author, year, journal). Do not claim biological fidelity
  beyond what is implemented and tested.
- Units:
  - one tick = 1 ms;
  - local positions in [0, 1]³ inside a region's box;
  - space units in the box (they set conduction delays);
  - currents in toolbox units unless a model states its physical mapping.
- Commit messages: imperative summary line, a body saying what changed and how it was tested.

## CI minute conservation (strictly enforced until Dec 1 or repo is public)
GitHub Actions minutes for the account are exhausted (macOS minutes count 10×, Windows 2×).
Until Dec 1 (or until the repo is public), CI is blocked:
- **Run the test suite locally before pushing**: never push unverified code or rely on CI for feedback.
- **Batch commits**: one push per finished step, not per commit.
- **Use `[skip ci]`** in commit titles/bodies for docs-only, comment, or roadmap changes.
- **Paste local test run into PR**: PR merges require local test runs pasted into the PR description (exact command + summary line, e.g. `JAX_PLATFORMS=cpu pytest -q -ra` and `204 passed in 216s`), instead of green checks.
- **macOS and Windows CI jobs** (`mac-app`, `nglif` macOS/Windows, release macOS builds, Avalonia Windows) run only on:
  - pushes to `main`;
  - `workflow_dispatch`;
  - PRs explicitly labeled `full-ci`.
- **Ubuntu jobs** run on every PR, skipping draft PRs for everything except the Ubuntu Python tests (`if: github.event.pull_request.draft == false`).

## Testing checklist for a pull request
- [ ] `JAX_PLATFORMS=cpu pytest -q` passes locally, with nothing skipped (kernel tests need `npm run build:kernel`).
- [ ] Local test command and summary line pasted into the PR description (replaces CI check until Dec 1).
- [ ] Commits batched (one push per finished step); `[skip ci]` used if docs-only.
- [ ] New code has tests: determinism; neutral parameters = no-op; the documented behaviour; the cost declaration.
- [ ] Existing networks unchanged (development fingerprints).
- [ ] `cd viz && npm run build` passes if `viz/` changed.
- [ ] Golden fixtures and contract tests pass if `desktop/common/`, `neurogenesis/bridge/`, or `nglif` changed.
- [ ] Design and scope review pass against AGENTS.md and task contracts before merging.
- [ ] Docs updated: README status block and table (checked by `tests/test_readme_status.py`), `docs/EXTENDING.md` or the relevant guide, the roadmap status line of your task,
      `docs/STAGES.md` for a stage, and any PLACEHOLDER your work fills. The status section of the AI context files is
      built from these, so a stale status line or placeholder shows up there as work still to do.

## When unsure
Prefer the smallest change that fulfils the task's acceptance tests. Ask (in the PR) rather than changing a contract,
adding a heavy dependency, or altering existing networks. Pure-Python dependencies beyond numpy / jax / matplotlib need
the maintainer's approval.
