# nglif: the shared native kernel

`nglif` is the `lif_int` integer kernel of neurogenesis-sim in portable C11, with NGB1 network I/O. It has no
dependencies and a plain C ABI, and all three desktop apps use it for live simulation.

It gives the same spikes, bit for bit, as `neurogenesis/spiking/reference.py`, `jax_backend.py` and
`viz/src/sim/kernel.ts`. The golden fixtures in `../../fixtures` check this.

```bash
cmake -S desktop/common/native/nglif -B build/nglif && cmake --build build/nglif --config Release
ctest --test-dir build/nglif -C Release --output-on-failure      # golden fixtures
```

The build produces a static library `nglif` and a shared one (`libnglif.dylib`, `libnglif.so`, `nglif.dll`).
To build without CMake: `cc -std=c11 -O2 -c nglif.c`.

| Call | Does |
|---|---|
| `nglif_network_new(n, e)`, `nglif_network_free` | a zero-filled network (structure of arrays: the NGB1 fields) |
| `nglif_network_read(path, err, len)`, `nglif_network_write` | NGB1 files (`../../PROTOCOL.md`, section 6) |
| `nglif_create(net, seed)`, `nglif_free` | a simulation (copies the network; seed 12345 is the toolbox default) |
| `nglif_set_external(sim, ext)` | current per neuron, added every tick (`jax_backend.tick` `ext_current`) |
| `nglif_inject(sim, i, current)` | current added on the next tick only |
| `nglif_step(sim, spikes, cap)` | one 1 ms tick; returns how many fired and writes their indices |
| `nglif_run(sim, ticks, t, i, cap)` | several ticks, collecting (tick, neuron) pairs |
| `nglif_potential`, `nglif_current`, `nglif_last_spike` | live state for drawing (last spike tick per neuron) |

**Bindings.**
- **Swift:** `module.modulemap` lets Swift `import nglif`. See `desktop/mac/build.sh` and `Sources/SimEngine.swift`.
- **Windows and Linux:** link the same library, or compile `nglif.c` into the app.

**Thread safety.** A simulation is not thread-safe. Guard it with a lock, or use one simulation per thread.

**Changing the kernel.** Any change must keep the fixtures passing. If the reference kernel changes on purpose,
regenerate the fixtures with `python desktop/common/fixtures/make_fixtures.py`, and change all four kernels in the same
PR, as AGENTS.md requires.
