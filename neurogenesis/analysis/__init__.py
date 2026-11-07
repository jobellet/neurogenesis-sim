"""Analysis: measurements on grown networks and their activity. Nothing here grows, changes or simulates a network
for its own sake; functions take a tissue, a network, positions, connectivity arrays or recorded activity and return
numbers.

Layout (one module per kind of measure; add new measures to the matching module or a new one here):
- `cells`: single-cell responses (frequency-current curves);
- `structure`: anatomy and wiring (mosaic regularity, connection lengths, modules);
- `criticality`: statistics of population activity (branching parameter, avalanches, scaling relations).

Development lives in `neurogenesis.stages` / `neurogenesis.development`, simulation in `neurogenesis.spiking`
(see docs/reference/layout.md).
"""
from . import cells, criticality, structure
from .cells import fi_curve
from .structure import connection_lengths, modularity, nearest_neighbour_regularity, within_group_fraction

__all__ = ["cells", "criticality", "structure", "fi_curve", "nearest_neighbour_regularity", "connection_lengths",
           "within_group_fraction", "modularity"]
