# Embedded Python runtime

This folder builds a relocatable Python that contains neurogenesis-sim and its dependencies, so the desktop apps work
on a computer with no Python, package manager or compiler. All three apps use the same script.

```bash
python desktop/common/runtime/build_runtime.py --target macos-arm64 --out build/runtime-macos-arm64
```

**Targets:** `macos-x86_64`, `macos-arm64`, `linux-x86_64`, `linux-arm64`, `windows-x86_64`. The default is this
machine.

**Output:**
- `<out>/python/`: the interpreter is `bin/python3`, or `python.exe` on Windows.
- `<out>/runtime.json`: the target, the CPython build and its checksum, and the versions of every package.

Apps start the bridge with `<out>/python/bin/python3 -m neurogenesis.bridge`, in an environment without
`PYTHONPATH`, `PYTHONHOME` or user site-packages.

| Step | Detail |
|---|---|
| CPython | python-build-standalone, `install_only_stripped`, release 20261013, Python 3.12. `pins.json` commits each target's archive name and SHA-256. A build trusts only those committed hashes, never a checksum file downloaded at build time. Archives are cached in `~/.cache/neurogenesis/runtime`. |
| Packages | `locks/<target>.txt` lists exact versions with the SHA-256 of each wheel, and is installed with `pip --require-hashes --no-deps`. The toolbox wheel, built from this checkout, is installed after it with `--no-deps`. Every target locks the same 16 packages (jax and jaxlib 0.4.38, numpy 2.5.4, matplotlib, scipy and their dependencies), so the three apps run the same versions. |
| Size | Test suites and caches are removed. On macOS, universal2 binaries are thinned to the target's architecture (`lipo -thin`), large extension modules are stripped of local symbols (jaxlib loses about 110 MB), and changed files are re-signed ad hoc. A macOS x86_64 runtime is about 510 MB, and 240 MB in the disk image. |
| Checks | Native builds precompile the bytecode and smoke-test the bridge. `smoke_test.py <runtime>` runs the bridge with an almost empty environment, checking the handshake, that the toolbox loads from inside the runtime, a network, and JAX. `desktop/mac/tools/check_bundle.sh` checks that nothing in the Mac app links outside macOS or the bundle. |

**Changing the pinned versions.** Edit `RELEASE`, `PYTHON` or `requirements.in` on purpose, in a PR, then run
`python build_runtime.py --lock` (pip 23.1 or later). It rewrites `pins.json` and every lock from the release's
checksums and pip's resolution. Review the diff, then rebuild and smoke-test every target. jax 0.4.38 is the last
version with macOS x86_64 wheels, so every target stays on it while the Intel app exists.

**What CI tests** (`.github/workflows/release.yml`; on version tags and by hand, never on pull requests). Runners come
from the repository variables of `.github/RUNNERS.md`; unset means GitHub-hosted:

| Target | Runner variable (default) | Built | Smoke-tested |
|---|---|---|---|
| macos-x86_64 | `MAC_RUNNER` (`macos-15-intel`) | natively, into the app and the disk image | from the mounted disk image, plus `check_bundle.sh` |
| macos-arm64 | `MAC_ARM64_RUNNER` (`macos-latest`) | natively, as above | as above |
| linux-x86_64 | `LINUX_RUNNER` (`ubuntu-latest`) | natively, or cross-built on another host | with `smoke_test.py`, on a Linux x86_64 runner only |
| windows-x86_64 | `WINDOWS_RUNNER` (`windows-latest`) | natively | with `smoke_test.py` |
| linux-arm64 | `LINUX_RUNNER` (`ubuntu-latest`) | cross-built | no: there is no arm64 Linux runner for this repository |

A macOS job stops at once if its runner has another architecture. Python runs in a per-job virtual environment, and
signing uses a temporary keychain, so a self-hosted machine's own Python and keychains are left as they are.

**Tests.** `tests/test_runtime_script.py` checks, without network access:
- that every target has a committed CPython hash and a hashed lock, and that all locks list the same packages;
- archive selection and pruning;
- on macOS, the thinning of a real universal binary.
