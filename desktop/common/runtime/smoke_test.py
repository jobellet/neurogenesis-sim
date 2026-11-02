"""Smoke test of a built runtime: its bridge, started with an (almost) empty environment, answers the handshake, imports
the toolbox from inside the runtime, grows a network and runs JAX.

    python desktop/common/runtime/smoke_test.py <runtime dir>          (the --out of build_runtime.py; any OS)

Only the variables the operating system itself needs are passed (Windows: SYSTEMROOT, TEMP; elsewhere: HOME, TMPDIR):
no PATH, PYTHONPATH or PYTHONHOME, so nothing installed on the machine can be used by accident.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REQUESTS = [
    {"id": 1, "method": "ping"},
    {"id": 2, "method": "capabilities"},
    {"id": 3, "method": "generate", "params": {"neurons": 60, "seed": 1}},
    {"id": 4, "method": "fi_curve", "params": {"hi": 20, "step": 10, "ticks": 200}},
]


def main(runtime: Path) -> int:
    runtime = Path(os.path.abspath(runtime))           # absolute, but symlinks kept (a runtime may link into an app)
    manifest = json.loads((runtime / "runtime.json").read_text())
    exe = runtime / "python" / manifest["interpreter"]
    env = {"JAX_PLATFORMS": "cpu", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    for k in ("SYSTEMROOT", "TEMP", "TMP", "HOME", "TMPDIR", "USERPROFILE", "LOCALAPPDATA"):
        if k in os.environ:
            env[k] = os.environ[k]
    r = subprocess.run([str(exe), "-m", "neurogenesis.bridge"], input="".join(json.dumps(q) + "\n" for q in REQUESTS),
                       capture_output=True, text=True, env=env, timeout=900, cwd=str(runtime))
    msgs = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
    replies = {m["id"]: m for m in msgs if "id" in m}
    problems = []
    ready = next((m for m in msgs if m.get("event") == "ready"), None)
    if not ready or ready["data"].get("protocol", "").split(".")[0] != "1":
        problems.append(f"no ready event with protocol 1.x: {ready}")
    for q in REQUESTS:
        if "result" not in replies.get(q["id"], {}):
            problems.append(f"{q['method']}: {replies.get(q['id'], 'no reply')}")
    if not problems:
        where = Path(replies[2]["result"]["repo"]).resolve()
        if (runtime / "python").resolve() not in where.parents:
            problems.append(f"toolbox imported from outside the runtime: {where}")
        if replies[3]["result"]["neurons"] != 60 or replies[4]["result"]["rate_hz"][-1] <= 0:
            problems.append(f"unexpected results: {replies[3]['result']}, {replies[4]['result']}")
    if problems:
        print("SMOKE TEST FAILED\n" + "\n".join(problems) + "\n--- stderr ---\n" + r.stderr[-4000:])
        return 1
    print(f"smoke test ok: {manifest['target']}, Python {manifest['python']}, protocol {ready['data']['protocol']}, "
          f"F-I {replies[4]['result']['rate_hz']} Hz, toolbox in {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
