"""Cues released by cells (C27): `secrete_cue` turns cells (or their arbor terminals) into sources of a diffusible cue,
stored as a `CueField` that later stages read like any field (guidance and arborisation in `grow_arbors`, migration,
weights, a neuromodulator's spatial reach).

Shared by `grow_arbors`: `cell_gain`, a per-cell value that is either a `Param` or {"expression": channel, "scale": s}
(s times the cell's expression level of that channel), so that a receptor's expression sets a growth cone's response.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np

from neurogenesis.arbors import NODE_BYTES, compartment_id
from neurogenesis.fields.maps import CueField
from neurogenesis.params import resolve, worst_case
from neurogenesis.stages.base import register_stage
from neurogenesis.tissue import Tissue


def cell_gain(spec: Any, tissue: Tissue, cells: np.ndarray, genome: Dict[str, Any], fields: Dict[str, Any],
              default: float = 0.0) -> np.ndarray:
    """Per-cell value for `cells`: a `Param` (a `Field` is read at the soma) or {"expression": k, "scale": s} = s x the
    expression level of channel k (0 where the tissue has no expression)."""
    if spec is None:
        return np.full(len(cells), float(default))
    if isinstance(spec, dict) and "expression" in spec:
        k = int(spec["expression"])
        s = float(resolve(spec.get("scale", 1.0), genome, fields))
        ex = tissue.expression
        if ex is None or ex.ndim != 2 or k >= ex.shape[1]:
            return np.zeros(len(cells))
        return s * np.asarray(ex[cells, k], dtype=float)
    v = np.asarray(resolve(spec, genome, fields, positions=tissue.positions[cells]), dtype=float)
    return np.broadcast_to(v, (len(cells),)).copy() if v.ndim == 0 else v.reshape(len(cells))


def select_cells(tissue: Tissue, sel: Any) -> np.ndarray:
    """Alive cells matching {"region": [...], "cell_type": [...], "expressing": k, "threshold": t} (all keys optional)."""
    mask = tissue.alive.copy()
    if isinstance(sel, dict):
        for key in ("region", "cell_type"):
            if key in sel:
                mask &= np.isin(getattr(tissue, key), np.asarray(sel[key]).ravel())
        if "expressing" in sel:
            ex = tissue.expression
            k = int(sel["expressing"])
            if ex is None or ex.ndim != 2 or k >= ex.shape[1]:
                return np.zeros(0, np.int64)
            mask &= np.asarray(ex[:, k], dtype=float) > float(sel.get("threshold", 0.0))
    return np.flatnonzero(mask)


@register_stage("secrete_cue")
class SecreteCue:
    """Selected cells release a cue; the stage stores its concentration as the `CueField` `name` in the fields.

    Long-range guidance cues are secreted by intermediate and final targets and form gradients along the path of
    growth cones (netrin, Slit, class-3 semaphorins; Tessier-Lavigne & Goodman 1996, Science 274:1123-1133); target
    cells also release factors that make arriving axons branch (BDNF at the optic tectum: Cohen-Cory & Fraser 1995,
    Nature 378:192-196), and the striatum's secretion is what makes it permissive for dopaminergic axons (Nolz1:
    Soleilhavoup et al. 2020, Nat Commun 11:3111). Arriving axons in turn shape the dendrites of their targets through
    activity and neurotrophins (McAllister, Lo & Katz 1995, Neuron 15:791-803; Cline 2001, Curr Opin Neurobiol
    11:118-126). Two kinds of source:
    - `source: "soma"` (default): each selected cell is one source of strength `amount`;
    - `source: "terminals"` (or "nodes"): the terminal nodes (or all nodes) of the selected cells' arbors of
      compartment `compartment` (default "axon") are sources, each of strength `amount` of its cell: release from
      boutons or varicosities, e.g. an afferent-derived signal, or a neuromodulator released along an axonal arbor
      (most dopaminergic terminals are non-synaptic: Ducrot et al. 2021, PubMed 34320240; release from sparse
      active-zone-like sites in about 30 % of varicosities: Liu et al. 2018, Cell 172:706-718).
    `cells` selects by region, cell_type and/or expression (`expressing` channel above `threshold`), e.g. the cells
    expressing a ligand gene; `amount` is a `Param` per cell or {"expression": k, "scale": s}; `length` (> 0) the decay
    length sqrt(D / k) in space units; `cutoff` (default 5) lengths. `mode: "add"` adds to an existing `CueField` of
    the same name with the same length (several cell types releasing one molecule); default "set" replaces it.
    No randomness. Neutral default: no `name` = no-op. O(sources).
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        per = 1 if params.get("source", "soma") == "soma" else int(worst_case(params.get("expected_sources_per_cell"), 50))
        s = N * per
        return int(s * 32 + N * 16), int(s * 10 + N * 4)

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        name = params.get("name")
        if name is None:
            return tissue
        name = str(resolve(name, genome, fields))
        length = float(resolve(params.get("length", 1.0), genome, fields))
        cutoff = float(resolve(params.get("cutoff", 5.0), genome, fields))
        cells = select_cells(tissue, params.get("cells"))
        amount = cell_gain(params.get("amount", 1.0), tissue, cells, genome, fields, default=1.0)
        source = str(resolve(params.get("source", "soma"), genome, fields))
        if source == "soma":
            pts, amt = tissue.positions[cells], amount
        elif source in ("terminals", "nodes"):
            m = tissue.morphology
            if m is None or m.n_nodes == 0 or len(cells) == 0:
                pts, amt = np.zeros((0, 3)), np.zeros(0)
            else:
                local = np.full(len(tissue.alive), -1, np.int64)
                local[cells] = np.arange(len(cells))
                comp = compartment_id(resolve(params.get("compartment", "axon"), genome, fields))
                sel = (local[m.cell] >= 0) & (m.compartment == comp)
                if source == "terminals":
                    sel &= m.children_count() == 0
                idx = np.flatnonzero(sel)
                pts, amt = m.xyz[idx].astype(float), amount[local[m.cell[idx]]]
        else:
            raise ValueError(f"secrete_cue: unknown source {source!r} (soma, terminals or nodes)")
        keep = amt != 0
        pts, amt = pts[keep], amt[keep]
        mode = str(resolve(params.get("mode", "set"), genome, fields))
        old = fields.get(name)
        if mode == "add" and isinstance(old, CueField):
            if abs(old.length - length) > 1e-12:
                raise ValueError(f"secrete_cue: cannot add to '{name}' with another length ({old.length} vs {length})")
            pts, amt = np.concatenate([old.points, pts]), np.concatenate([old.amounts, amt])
        elif mode not in ("set", "add"):
            raise ValueError(f"secrete_cue: unknown mode {mode!r}")
        fields[name] = CueField(pts, amt, length=length, cutoff=cutoff)
        return tissue
