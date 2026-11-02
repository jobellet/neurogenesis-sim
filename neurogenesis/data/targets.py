import numpy as np
from typing import Any, Dict, List, Optional
from neurogenesis.tissue import Tissue
from neurogenesis.fitting import register_metric, select

@register_metric("mean_weight")
def _mean_weight(t: Tissue, o: Dict[str, Any]) -> float:
    pre = select(t, o, "pre_")
    post = select(t, o, "post_")
    c = t.connectivity
    
    if len(pre) == 0 or len(post) == 0 or len(c.pre) == 0:
        return 0.0
        
    pre_ok = np.zeros(len(t.alive), bool)
    pre_ok[pre] = True
    post_ok = np.zeros(len(t.alive), bool)
    post_ok[post] = True
    
    mask = pre_ok[c.pre] & post_ok[c.post]
    if not np.any(mask):
        return 0.0
        
    w = c.weight[mask]
    if o.get("abs", False):
        w = np.abs(w)
    return float(np.mean(w))

@register_metric("column_fraction")
def _column_fraction(t: Tissue, o: Dict[str, Any]) -> float:
    pre = select(t, o, "pre_")
    post = select(t, o, "post_")
    c = t.connectivity
    
    if len(pre) == 0 or len(post) == 0 or len(c.pre) == 0:
        return 0.0
        
    pre_ok = np.zeros(len(t.alive), bool)
    pre_ok[pre] = True
    post_ok = np.zeros(len(t.alive), bool)
    post_ok[post] = True
    
    mask = pre_ok[c.pre] & post_ok[c.post]
    if not np.any(mask):
        return 0.0
        
    syn_pre = c.pre[mask]
    syn_post = c.post[mask]
    
    cols = None
    if "column_field" in o:
        cf = o["column_field"]
        if hasattr(cf, "values"):
            cols = cf.values(t.positions)
        elif callable(cf):
            cols = cf(t.positions)
        else:
            cols = np.asarray(cf)
    elif "columns" in o:
        centres = np.asarray(o["columns"])
        pos = t.positions[:, :centres.shape[1]]
        diff = pos[:, None, :] - centres[None, :, :]
        dists = np.sum(diff**2, axis=-1)
        cols = np.argmin(dists, axis=-1)
    else:
        return 0.0
        
    offset = o.get("offset", None)
    if offset is not None:
        offset = np.asarray(offset)
        if "columns" in o:
            centres = np.asarray(o["columns"])
            pre_pos = centres[cols[syn_pre]]
            post_pos = centres[cols[syn_post]]
            diff = post_pos - pre_pos
            same = np.linalg.norm(diff - offset, axis=-1) < 1e-5
        else:
            diff = cols[syn_post] - cols[syn_pre]
            same = np.linalg.norm(diff - offset, axis=-1) < 1e-5
    else:
        same = (cols[syn_pre] == cols[syn_post])
        if len(same.shape) > 1:
            same = np.all(same, axis=-1)
            
    return float(np.mean(same))


def extract_fitting_targets(tissue: Tissue, info: Optional[Dict[str, Any]] = None, columns: Optional[np.ndarray] = None, min_synapses: int = 1) -> List[Dict[str, Any]]:
    targets = []
    
    types = np.unique(tissue.cell_type[tissue.alive])
    
    for t in types:
        count = int(np.sum((tissue.cell_type == t) & tissue.alive))
        targets.append({
            "metric": "cell_count",
            "cell_type": int(t),
            "value": count,
            "scale": max(1.0, 0.2 * count)
        })
        
    for pre_t in types:
        for post_t in types:
            pre_mask = (tissue.cell_type == pre_t) & tissue.alive
            post_mask = (tissue.cell_type == post_t) & tissue.alive
            
            c = tissue.connectivity
            syn_mask = pre_mask[c.pre] & post_mask[c.post]
            syn_count = int(np.sum(syn_mask))
            
            if syn_count < min_synapses:
                continue
                
            num_post = int(np.sum(post_mask))
            mean_in = syn_count / num_post if num_post > 0 else 0.0
            
            targets.append({
                "metric": "synapse_count",
                "pre_cell_type": int(pre_t),
                "post_cell_type": int(post_t),
                "value": syn_count,
                "scale": max(1.0, 0.2 * syn_count)
            })
            
            targets.append({
                "metric": "mean_in_degree",
                "pre_cell_type": int(pre_t),
                "post_cell_type": int(post_t),
                "value": mean_in,
                "scale": max(0.1, 0.2 * mean_in)
            })
            
            if columns is not None:
                pos = tissue.positions[:, :columns.shape[1]]
                diff = pos[:, None, :] - columns[None, :, :]
                dists = np.sum(diff**2, axis=-1)
                cols = np.argmin(dists, axis=-1)
                
                syn_pre = c.pre[syn_mask]
                syn_post = c.post[syn_mask]
                same_col = cols[syn_pre] == cols[syn_post]
                frac = float(np.mean(same_col)) if len(same_col) > 0 else 0.0
                
                targets.append({
                    "metric": "column_fraction",
                    "pre_cell_type": int(pre_t),
                    "post_cell_type": int(post_t),
                    "columns": columns.tolist(),
                    "value": frac,
                    "scale": max(0.05, 0.2 * frac)
                })
                
    return targets

def compare_type_statistics(grown: Tissue, reference: Tissue) -> Dict[str, Any]:
    types = np.unique(np.concatenate([grown.cell_type[grown.alive], reference.cell_type[reference.alive]]))
    N_types = int(np.max(types)) + 1 if len(types) > 0 else 0
    
    def get_counts(t: Tissue):
        counts = np.zeros(N_types, dtype=int)
        if len(t.alive) == 0:
            return counts
        unique, c = np.unique(t.cell_type[t.alive], return_counts=True)
        counts[unique] = c
        return counts
        
    def get_syn_matrix(t: Tissue):
        mat = np.zeros((N_types, N_types), dtype=int)
        c = t.connectivity
        if len(c.pre) > 0:
            pre_types = t.cell_type[c.pre]
            post_types = t.cell_type[c.post]
            alive_mask = t.alive[c.pre] & t.alive[c.post]
            pre_types = pre_types[alive_mask]
            post_types = post_types[alive_mask]
            np.add.at(mat, (pre_types, post_types), 1)
        return mat

    def get_degree_matrix(t: Tissue, syn_mat, counts):
        deg = np.zeros((N_types, N_types), dtype=float)
        for i in range(N_types):
            for j in range(N_types):
                if counts[j] > 0:
                    deg[i, j] = syn_mat[i, j] / counts[j]
        return deg

    c_g = get_counts(grown)
    c_r = get_counts(reference)
    
    s_g = get_syn_matrix(grown)
    s_r = get_syn_matrix(reference)
    
    d_g = get_degree_matrix(grown, s_g, c_g)
    d_r = get_degree_matrix(reference, s_r, c_r)
    
    sum_r = np.sum(c_r)
    count_l1_rel_error = float(np.sum(np.abs(c_g - c_r)) / sum_r) if sum_r > 0 else 0.0
    
    flat_g = s_g.flatten()
    flat_r = s_r.flatten()
    norm_g = np.linalg.norm(flat_g)
    norm_r = np.linalg.norm(flat_r)
    if norm_g > 0 and norm_r > 0:
        matrix_cosine_similarity = float(np.dot(flat_g, flat_r) / (norm_g * norm_r))
    else:
        matrix_cosine_similarity = 1.0 if norm_g == 0 and norm_r == 0 else 0.0
        
    mask = d_r > 0
    if np.any(mask):
        degree_mean_rel_error = float(np.mean(np.abs(d_g[mask] - d_r[mask]) / d_r[mask]))
    else:
        degree_mean_rel_error = 0.0
        
    return {
        "grown_counts": c_g.tolist(),
        "reference_counts": c_r.tolist(),
        "grown_synapses": s_g.tolist(),
        "reference_synapses": s_r.tolist(),
        "count_l1_rel_error": count_l1_rel_error,
        "matrix_cosine_similarity": matrix_cosine_similarity,
        "degree_mean_rel_error": degree_mean_rel_error
    }
