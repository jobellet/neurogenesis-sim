# Glossary

Audit
: Re-evaluating a chosen genome on development seeds never used during the search, including knockouts.

Body plan
: Regions (boxes with placement rules, roles and signs) and the projections allowed between them.

Bridge
: The JSON-lines server (`python -m neurogenesis.bridge`) through which apps and other programs use the toolbox.

Capacity test
: Checking with a hand-set genome that an architecture can do a task at all, before any genetic search.

Development seed
: The random seed of growth. Same plan + genome + seed → the same network.

Driver neuron
: A neuron that fires on its own: Poisson (`mode` 1) or burster (`mode` 2).

Field
: Values defined on space (gradients, layers, maps), sampled at cell positions.

Fingerprint
: A hash of a grown network, frozen in tests to detect any change in development.

Gene
: A path into the genome plus bounds; coded in [0, 1] for evolution.

Island
: One independent evolving population; islands use disjoint development seeds.

Module
: Plan + genome + interface + validation + provenance + neuron model, saved as JSON and reusable.

NGB1
: The binary network format shared by the bridge, the C kernel and the apps.

nglif
: The portable C implementation of the integer LIF kernel, used by the desktop apps.

Param
: The source of a stage parameter: `Const`, `Gene`, `Field`, `Fit` or `Expr`.

Rule
: A small function modifying one phase of the fixed growth procedure; inactive without its genes.

Schedule
: Ordered list of stages (each with Params, `repeat`, `when`) that transforms a Tissue.

Stage
: A registered operator `Tissue × Params × rng → Tissue`.

Tick
: One simulation step, 1 ms.

Tissue
: The struct of arrays (cells and connectivity) that stages transform.
