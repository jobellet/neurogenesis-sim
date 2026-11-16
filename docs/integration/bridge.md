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

### Node.js client

```javascript
import { spawn } from "node:child_process";
import readline from "node:readline";

const proc = spawn("python", ["-m", "neurogenesis.bridge"], { stdio: ["pipe", "pipe", "inherit"] });
const rl = readline.createInterface({ input: proc.stdout });
const pending = new Map();
let nextId = 1;

rl.on("line", (line) => {
  const msg = JSON.parse(line);
  if (msg.id !== undefined && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  }
});

const call = (method, params = {}) =>
  new Promise((resolve) => {
    const id = nextId++;
    pending.set(id, resolve);
    proc.stdin.write(JSON.stringify({ id, method, params }) + "\n");
  });

console.log(await call("ping"));
const net = (await call("generate", { morphology: "column", neurons: 300, seed: 1 })).result;
const sim = (await call("simulate", { ngb: net.path, model: "lif_int", ticks: 200, seed: 0 })).result;
console.log("spikes:", sim.total_spikes);
proc.stdin.end();
```

### Julia client

```julia
using JSON

proc = open(`python -m neurogenesis.bridge`, "r+")
ready = JSON.parse(readline(proc))

function bridge_call(io, id, method; kwargs...)
    req = Dict("id" => id, "method" => method, "params" => Dict(string(k) => v for (k, v) in kwargs))
    println(io, JSON.json(req)); flush(io)
    while true
        msg = JSON.parse(readline(io))
        get(msg, "id", nothing) == id && return msg
    end
end

println(bridge_call(proc, 1, "ping"))
net = bridge_call(proc, 2, "generate"; morphology="column", neurons=300, seed=1)["result"]
sim = bridge_call(proc, 3, "simulate"; ngb=net["path"], model="lif_int", ticks=200, seed=0)["result"]
close(proc)
```

### MATLAB client

```matlab
pb = java.lang.ProcessBuilder({'python', '-m', 'neurogenesis.bridge'});
proc = pb.start();
stdin = java.io.PrintWriter(java.io.OutputStreamWriter(proc.getOutputStream(), 'UTF-8'), true);
stdout = java.io.BufferedReader(java.io.InputStreamReader(proc.getInputStream(), 'UTF-8'));

ready = jsondecode(char(stdout.readLine()));

stdin.println(jsonencode(struct('id', 1, 'method', 'ping', 'params', struct())));
disp(jsondecode(char(stdout.readLine())));

req = struct('id', 2, 'method', 'generate', 'params', struct('morphology', 'column', 'neurons', 300, 'seed', 1));
stdin.println(jsonencode(req));
net = jsondecode(char(stdout.readLine())).result;

simReq = struct('id', 3, 'method', 'simulate', 'params', struct('ngb', net.path, 'model', 'lif_int', 'ticks', 200, 'seed', 0));
stdin.println(jsonencode(simReq));
sim = jsondecode(char(stdout.readLine())).result;
proc.destroy();
```
