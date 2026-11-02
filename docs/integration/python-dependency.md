# Using the toolbox as a Python dependency

## Pin a version
```toml
# pyproject.toml of your project
dependencies = ["neurogenesis-sim @ git+https://github.com/jobellet/neurogenesis-sim.git@<commit-or-tag>"]
```
Pin a commit or a tag: development results depend on the exact code that grew the networks.

## Freeze network fingerprints
Your results come from specific networks. Freeze a fingerprint of each (plan + genome + seed → network) and test it,
so that an upgrade of the toolbox that changes your networks fails your tests instead of silently changing results.

```python
import hashlib, json

def fingerprint(net):
    d = net.to_dict()
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()

# tests/test_fingerprints.py
def test_networks_unchanged():
    expected = json.load(open("tests/fixtures/network_fingerprints.json"))
    for name, (plan, genome, seed) in my_networks().items():
        assert fingerprint(grow(plan, genome, seed)) == expected[name]
```

## Keep your project's content out of the toolbox
Region names, stimuli, tasks and environments belong to your project. If you need a new mechanism, write it as a
plugin in your package; if it is general, propose it upstream (see {doc}`../development/contributing`).

## Determinism checklist
- Pass explicit seeds everywhere (`grow(..., seed=)`, `simulate_counts` kernel seed, evolution `island`).
- Never use global NumPy random state in code that feeds the toolbox.
- Record the toolbox commit, the JAX version and the device in your result files.
