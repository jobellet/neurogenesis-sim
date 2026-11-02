# Driving the toolbox from other programs (the bridge)

`python -m neurogenesis.bridge` is a server that reads one JSON request per line on stdin and writes one JSON message
per line on stdout. The desktop apps use it; any program that can start a process can too.

## Python client (minimal)
```python
import json, subprocess

p = subprocess.Popen(["python", "-m", "neurogenesis.bridge"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     text=True, bufsize=1)
ready = json.loads(p.stdout.readline())                 # {"event": "ready", "data": {"protocol": "1.0", ...}}

def call(i, method, **params):
    p.stdin.write(json.dumps({"id": i, "method": method, "params": params}) + "\n")
    while True:
        msg = json.loads(p.stdout.readline())
        if msg.get("id") == i:
            return msg

print(call(1, "ping"))
print(call(2, "models")["result"])
net = call(3, "generate", morphology="column", neurons=300, seed=1)["result"]   # {path, neurons, synapses, ...}
spikes = call(4, "simulate", ngb=net["path"], model="lif_int", ticks=200, seed=0)["result"]
```

## Other languages
- **C# / .NET:** the Windows and Linux app (`desktop/avalonia/`).
- **Swift:** the macOS app (`desktop/mac/Sources/Bridge.swift`).
- **JavaScript / Node, Julia, MATLAB, R:** start the process, write lines, read lines.

Methods cover projects, plans, development (with step-by-step checkpoints), simulation, cost estimates, f–I curves,
plasticity, evolution (long jobs with progress events) and modules. Full list and message formats:
{doc}`../reference/bridge-protocol`.

```{admonition} PLACEHOLDER
:class: placeholder
Small client libraries (`neurogenesis-bridge` for Node and Julia), and an example notebook driving the bridge from
MATLAB.
```
