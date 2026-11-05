"""Stage instantiate_morphologies: continuous latent sampling and attaching of morphologies (M2)."""
from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..arbors import NODE_BYTES, SOMA, ArborStore
from ..data.morphology_catalogue import load_catalogue_cells
from ..morphometry.latent import ContinuousMorphologySampler
from ..params import resolve, worst_case
from ..tissue import Tissue
from .arbors import _select
from .base import register_stage

_DEFAULT_NODES_PER_CELL = 40
_BYTES_PER_NODE = NODE_BYTES * 4 + 32
_OPS_PER_NODE = 60


@register_stage("instantiate_morphologies")
class InstantiateMorphologies:
    """Samples and attaches morphology trees to selected cells conditioned on developmental context.

    For each selected cell, draws a morphology from a continuous latent phenotype space conditioned on
    its cell context (e.g. region, cell_type, birth_stage). The morphology is rooted at the cell's soma position
    (`tissue.positions[cell]`) and merged into `tissue.morphology`. Existing connectivity is untouched.

    Params:
    - `catalogue`: path to a manifest JSON or directory with SWC files, or a manifest dict (neutral if None).
    - `attachment_prob`: probability of attaching a morphology to each selected cell (default 1.0; <= 0 is no-op).
    - `n_neurites`: number of neurite trees attached per cell (default 1).
    - `cells`: cell selector dict (e.g. {"region": ..., "cell_type": ...}).
    - `conditions`: context table or dict mapping cell attributes to condition keys.
    - `max_nodes`: safety bound on total nodes created (default 1_000_000).
    - `shrinkage`: covariance shrinkage in latent space (default 0.2).

    Determinism: randomness comes only from the stage `rng` stream.
    Neutral parameters (attachment_prob=0, catalogue=None, or empty cells) leave tissue unchanged.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        prob = float(worst_case(params.get("attachment_prob"), 1.0))
        if prob <= 0:
            return 0, 0
        n_neurites = int(worst_case(params.get("n_neurites"), 1))
        max_n = int(worst_case(params.get("max_nodes"), 1_000_000))
        expected_nodes = min(int(N * prob * n_neurites * _DEFAULT_NODES_PER_CELL), max_n)
        return int(expected_nodes * _BYTES_PER_NODE + N * 16), int(expected_nodes * _OPS_PER_NODE + N * 10)

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        att_prob = float(resolve(params.get("attachment_prob", 1.0), genome, fields))
        cat_ref = params.get("catalogue")
        if att_prob <= 0.0 or cat_ref is None:
            return tissue

        cells = _select(tissue, params.get("cells"))
        if len(cells) == 0:
            return tissue

        # Filter by attachment probability using stage rng
        mask = rng.random(len(cells)) < att_prob
        target_cells = cells[mask]
        if len(target_cells) == 0:
            return tissue

        base_dir = params.get("base_dir")
        stores, metadata = load_catalogue_cells(cat_ref, base_dir=base_dir)
        if len(stores) == 0:
            return tissue

        shrinkage = float(resolve(params.get("shrinkage", 0.2), genome, fields))
        sampler = ContinuousMorphologySampler(stores, metadata, shrinkage=shrinkage)

        max_nodes = int(resolve(params.get("max_nodes", 1_000_000), genome, fields))
        n_neurites = max(1, int(resolve(params.get("n_neurites", 1), genome, fields)))

        cond_spec = params.get("conditions", {})
        new_stores: List[ArborStore] = []
        total_nodes = 0

        for cell_idx in target_cells:
            if total_nodes >= max_nodes:
                break
            # Context dictionary for this cell
            cell_cond = {}
            if hasattr(tissue, "region") and len(tissue.region) > cell_idx:
                cell_cond["region"] = int(tissue.region[cell_idx])
            if hasattr(tissue, "cell_type") and len(tissue.cell_type) > cell_idx:
                cell_cond["cell_type"] = int(tissue.cell_type[cell_idx])
            if hasattr(tissue, "birth_stage") and len(tissue.birth_stage) > cell_idx:
                cell_cond["birth_stage"] = int(tissue.birth_stage[cell_idx])
            if isinstance(cond_spec, dict):
                cell_cond.update(cond_spec)

            # Sample continuous morphology
            sampled_list = sampler.sample_cells(cell_cond, n=n_neurites, rng=rng, cell_offset=cell_idx)
            soma_pos = tissue.positions[cell_idx]

            for s in sampled_list:
                if total_nodes + s.n_nodes > max_nodes:
                    break
                # Root the tree at the soma position
                shift = soma_pos - s.xyz[0]
                rooted_xyz = s.xyz + shift
                rooted_store = ArborStore(
                    xyz=rooted_xyz.astype(np.float32),
                    radius=s.radius,
                    parent=s.parent,
                    compartment=s.compartment,
                    cell=np.full(s.n_nodes, cell_idx, dtype=np.int32),
                    labels=s.labels
                )
                new_stores.append(rooted_store)
                total_nodes += s.n_nodes

        if not new_stores:
            return tissue

        new_arbors = ArborStore.concatenate(new_stores)
        existing = getattr(tissue, "morphology", None) or getattr(tissue, "arbors", None)
        if existing is not None and existing.n_nodes > 0:
            merged = ArborStore.concatenate([existing, new_arbors])
        else:
            merged = new_arbors

        tissue.morphology = merged
        return tissue
