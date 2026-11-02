"""Connectome skeleton import and simplification (N4).

`simplify_arbor_rdp` drops nodes of an `ArborStore` within `tolerance` of the line between kept nodes (Ramer, 1972,
Computer Graphics and Image Processing; Douglas, 1973, Cartographica), keeping roots, branch points,
terminals and compartment boundaries.
`import_connectome_skeletons` reads SWC skeletons (a directory or zip) for given source ids into one store, in the
toolbox frame (`data.importer.transform_positions`); `attach_connectome_skeletons` sets them as a tissue's morphology.
"""
from __future__ import annotations

import zipfile
import io
from pathlib import Path
from typing import Dict, Optional, Sequence, Union, Any

import numpy as np

from ..arbors import ArborStore, read_swc
from ..tissue import Tissue
from .importer import transform_positions

def simplify_arbor_rdp(store: ArborStore, tolerance: float) -> ArborStore:
    """Simplifies unbranched chains between roots, branch points, terminals, and compartment boundaries 
    using 3D Ramer-Douglas-Peucker perpendicular distance threshold `tolerance`.
    `tolerance <= 0` returns `store` unchanged. Preserves cell indices and parent ordering."""
    if tolerance <= 0 or store.n_nodes == 0:
        return store
        
    nc = store.children_count()
    topo = (store.parent < 0) | (nc != 1) | (store.compartment != np.where(store.parent >= 0, store.compartment[np.maximum(store.parent, 0)], store.compartment))
    
    def _rdp_keep(pts: np.ndarray, tol: float) -> np.ndarray:
        if len(pts) <= 2:
            return np.ones(len(pts), dtype=bool)
        
        start, end = pts[0], pts[-1]
        
        if np.allclose(start, end):
            d = np.linalg.norm(pts - start, axis=1)
        else:
            line_vec = end - start
            line_len = np.linalg.norm(line_vec)
            if line_len == 0:
                d = np.linalg.norm(pts - start, axis=1)
            else:
                d = np.linalg.norm(np.cross(line_vec, start - pts), axis=1) / line_len
            
        dmax = np.max(d[1:-1])
        if dmax > tol:
            idx = np.argmax(d[1:-1]) + 1
            keep1 = _rdp_keep(pts[:idx+1], tol)
            keep2 = _rdp_keep(pts[idx:], tol)
            keep = np.zeros(len(pts), dtype=bool)
            keep[:idx+1] = keep1
            keep[idx:] = keep[idx:] | keep2
            return keep
        else:
            keep = np.zeros(len(pts), dtype=bool)
            keep[0] = True
            keep[-1] = True
            return keep

    keep_final = topo.copy()
    parent = store.parent
    
    # Pre-compute children to avoid O(N^2) behavior in traversal
    children_idx = np.argsort(parent, kind='stable')
    sorted_parent = parent[children_idx]
    
    def get_children(node_idx):
        lo = np.searchsorted(sorted_parent, node_idx, side='left')
        hi = np.searchsorted(sorted_parent, node_idx, side='right')
        return children_idx[lo:hi]
    
    chain_starts = np.flatnonzero(~topo & (parent >= 0) & topo[parent])
    
    for start_idx in chain_starts:
        curr = start_idx
        chain = [parent[start_idx]]
        while not topo[curr]:
            chain.append(curr)
            children = get_children(curr)
            if len(children) != 1:
                break
            curr = children[0]
        chain.append(curr)
        
        chain_idx = np.array(chain)
        pts = store.xyz[chain_idx]
        
        keep_chain = _rdp_keep(pts, tolerance)
        keep_final[chain_idx[keep_chain]] = True

    return store.take(keep_final)

def import_connectome_skeletons(source: Union[str, Path], source_ids: Sequence[int], units: Optional[Dict[str, Any]] = None,
                                max_nodes_per_cell: Optional[int] = None, rdp_tolerance: float = 0.0,
                                compartment_map: Optional[Dict[int, int]] = None) -> ArborStore:
    """Loads SWC files for the given `source_ids`, assigns `cell` index matching the tissue's neuron order."""
    source_path = Path(source)
    units = units or {}
    
    stores = []
    
    is_zip = source_path.is_file() and source_path.suffix.lower() == '.zip'
    
    if is_zip:
        with zipfile.ZipFile(source_path, 'r') as zf:
            for cell_idx, sid in enumerate(source_ids):
                filename = f"{sid}.swc"
                try:
                    with zf.open(filename) as f:
                        lines = io.TextIOWrapper(f, encoding='utf-8').readlines()
                        store = read_swc(lines, cell=cell_idx)
                        stores.append(store)
                except KeyError:
                    stores.append(ArborStore())
    else:
        for cell_idx, sid in enumerate(source_ids):
            swc_file = source_path / f"{sid}.swc"
            if swc_file.exists():
                store = read_swc(swc_file, cell=cell_idx)
                stores.append(store)
            else:
                stores.append(ArborStore())
                
    merged = ArborStore.concatenate(stores)
    if merged.n_nodes == 0:
        return merged
        
    merged.xyz = transform_positions(merged.xyz, units).astype(np.float32)
    
    if "voxel_size" in units:
        mean_voxel_size = np.mean(units["voxel_size"])
        merged.radius = (merged.radius * mean_voxel_size).astype(np.float32)
        
    if compartment_map:
        new_comp = merged.compartment.copy()
        for old_c, new_c in compartment_map.items():
            new_comp[merged.compartment == old_c] = new_c
        merged.compartment = new_comp
        
    if rdp_tolerance > 0:
        merged = simplify_arbor_rdp(merged, rdp_tolerance)
        
    if max_nodes_per_cell is not None:
        merged = merged.to_budget(max_nodes_per_cell)
        
    return merged

def attach_connectome_skeletons(tissue: Tissue, info: dict, swc_source: Union[str, Path], 
                                max_nodes_per_cell: Optional[int] = None, rdp_tolerance: float = 0.0) -> Tissue:
    """Uses info['source_ids'] to load and attach skeletons to tissue.morphology."""
    source_ids = info.get("source_ids", [])
    if not len(source_ids):
        return tissue
        
    units = info.get("dataset_units", None)
    
    store = import_connectome_skeletons(
        source=swc_source,
        source_ids=source_ids,
        units=units,
        max_nodes_per_cell=max_nodes_per_cell,
        rdp_tolerance=rdp_tolerance
    )
    
    tissue.morphology = store
    return tissue
