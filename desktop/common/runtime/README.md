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
| CPython | python-build-standalone, `install_only_stripped`. The release (`RELEASE` in the script) and the minor version (3.12) are pinned. The archive is checked against the release's `SHA256SUMS` and cached in `~/.cache/neurogenesis/runtime`. |
| Packages | The toolbox wheel, built from this checkout, plus `jaxlib`. The wheel brings numpy, jax and matplotlib. For the build machine's own target, the runtime's own pip installs them. For another target, the host pip installs binary wheels for that platform. |
| Size | Test suites and caches are removed. On macOS, large extension modules are stripped of local symbols and re-signed ad hoc (jaxlib loses about 110 MB). A macOS x86_64 runtime is about 510 MB, and 240 MB in the disk image. |
| Checks | Native builds precompile the bytecode and smoke-test the bridge. `desktop/mac/tools/check_bundle.sh` verifies that nothing links outside macOS or the bundle. |

**Changing the pinned versions.** Bump `RELEASE` or `PYTHON` on purpose, in a PR. Rebuild every target that has an
app, and check that jaxlib publishes wheels for that Python on every target. jax 0.4.38 is the last version with
macOS x86_64 wheels, so Intel Macs stay on it.

**Tests.** `tests/test_runtime_script.py` checks the script without network access. The Release workflow
(`.github/workflows/release.yml`) builds real runtimes and smoke-tests them.
