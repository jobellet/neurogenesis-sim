# Desktop apps

Native apps for macOS, Windows and Linux that drive the toolbox: build networks by hand or from genes, step through
development in 3D, and simulate live. They share everything that is not platform UI.

```
desktop/
  common/    shared by every app. Owned jointly: a change needs a PR that keeps all three apps working.
    PROTOCOL.md     the bridge protocol (JSON lines) and the NGB1 network format
    native/nglif/   the live simulation kernel in portable C11 (lif_int + NGB1 I/O), used by every app
    fixtures/       golden networks and spike rasters every native kernel must reproduce
  mac/       Swift, SwiftUI and Metal
  windows/   (built by another agent)
  linux/     (built by another agent)
```

| Shared piece | Where | Status |
|---|---|---|
| Bridge server | `neurogenesis/bridge/` (`python -m neurogenesis.bridge`), spec in `common/PROTOCOL.md`, tests in `tests/test_bridge.py` | done |
| Native live kernel (C11, `nglif`) and golden fixtures | `common/native/nglif/`, `common/fixtures/`; CI builds it on Linux, macOS and Windows | done |
| UI schema (forms generated from the bridge's schemas) and visual spec | `common/UI_SCHEMA.md`, `common/visual_spec.json` | planned |
| Embedded Python runtime | `common/runtime/` | planned |

**Rules for shared files.**
- **Bump on breaking changes.** If you change the protocol, the NGB1 format or the UI schema in a way that breaks
  clients, bump its version, update its spec, and say so in the PR: the other two apps depend on it.
- **Add without bumping.** Adding a method or an optional field is not a breaking change. Clients must ignore what
  they do not know.
