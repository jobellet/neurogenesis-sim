# Integrating neurogenesis-sim into other projects

| You want to... | Use | Page |
|---|---|---|
| use the toolbox from your own Python project | a pinned dependency + network fingerprints | {doc}`python-dependency` |
| add biology without forking | plugins: rules, stages, models, geometries | {doc}`../tutorials/rules-plugins` |
| reuse a circuit someone else made | modules | {doc}`../tutorials/modules` |
| drive it from another language or app | the bridge (JSON lines on stdin / stdout) | {doc}`bridge` |
| exchange networks with other tools | JSON, NGB1, CSR arrays | {doc}`file-formats` |
| run grown networks in other simulators | export (planned) | {doc}`other-simulators` |
| run large batches on a cluster | batched JAX simulation, parallel growth | {doc}`cluster` |

```{toctree}
:hidden:

python-dependency
bridge
file-formats
other-simulators
cluster
```
