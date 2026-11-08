"""Cell-type statistics of a connectome as fitting targets (I5).

Registers the `mean_weight` and `column_fraction` metrics in `neurogenesis.fitting`. `extract_fitting_targets` turns an
imported tissue into target dicts (cell counts per type, synapse counts and mean in-degrees per type pair, column
fractions); `compare_type_statistics` compares a grown tissue with a reference type by type.
"""
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union
import numpy as np
from neurogenesis.tissue import Tissue
from neurogenesis.fitting import register_metric, select


@dataclass
class TargetSpec:
    name: str
    fn: Callable[..., float]
    title: str = ""
    description: str = ""
    unit: str = ""
    default_scale: float = 1.0
    requires_spiking: bool = False
    options_schema: Optional[Dict[str, Any]] = None

    def __call__(self, tissue: Tissue, options: Optional[Dict[str, Any]] = None) -> float:
        try:
            sig = inspect.signature(self.fn)
            if len(sig.parameters) == 1:
                return float(self.fn(tissue))
            return float(self.fn(tissue, options if options is not None else {}))
        except TypeError:
            return float(self.fn(tissue, options if options is not None else {}))


TARGETS: Dict[str, TargetSpec] = {}


def register_target(
    name: Optional[Union[str, Callable]] = None,
    title: str = "",
    description: str = "",
    unit: str = "",
    default_scale: float = 1.0,
    requires_spiking: bool = False,
    options_schema: Optional[Dict[str, Any]] = None,
):
    """Decorator registering an evolvable objective target with metadata."""
    def deco(f: Callable) -> Callable:
        target_name = (name if isinstance(name, str) else None) or getattr(f, "__name__", "target")
        doc_str = getattr(f, "__doc__", "") or ""
        desc = description or (doc_str.split("\n\n")[0].strip().replace("\n", " ") if doc_str else "")
        tit = title or target_name.replace("_", " ").title()

        spec = TargetSpec(
            name=target_name,
            fn=f,
            title=tit,
            description=desc,
            unit=unit,
            default_scale=float(default_scale),
            requires_spiking=bool(requires_spiking),
            options_schema=options_schema,
        )
        TARGETS[target_name] = spec

        # Synchronize with fitting.METRICS for seamless compatibility
        import neurogenesis.fitting as _fitting
        def metric_adapter(tissue: Tissue, options: Dict[str, Any]) -> float:
            return spec(tissue, options)
        _fitting.METRICS[target_name] = metric_adapter
        return f

    if callable(name):
        f = name
        name = None
        return deco(f)
    return deco


def get_target(name: str) -> TargetSpec:
    if name in TARGETS:
        return TARGETS[name]
    import neurogenesis.fitting as _fitting
    if name in _fitting.METRICS:
        fn = _fitting.METRICS[name]
        spec = TargetSpec(
            name=name,
            fn=fn,
            title=name.replace("_", " ").title(),
            description=getattr(fn, "__doc__", "") or "",
            requires_spiking=(name == "firing_rate"),
        )
        TARGETS[name] = spec
        return spec
    raise KeyError(f"unknown target {name!r} (registered: {sorted(TARGETS)})")


# Built-in Structural Targets
@register_target(
    name="modularity",
    title="Network Modularity Q",
    description="Newman's modularity Q of synaptic connectivity graph partitioned by cell type or region.",
    unit="",
    default_scale=0.1,
    requires_spiking=False,
    options_schema={"partition": {"type": "string", "enum": ["cell_type", "region"], "default": "cell_type"},
                    "weighted": {"type": "bool", "default": True}}
)
def target_modularity(tissue: Tissue, options: Optional[Dict[str, Any]] = None) -> float:
    from neurogenesis.analysis.structure import modularity
    options = options or {}
    c = tissue.connectivity
    if len(c.pre) == 0:
        return 0.0
    partition = options.get("partition", "cell_type")
    labels = getattr(tissue, partition) if hasattr(tissue, partition) else tissue.cell_type
    weights = c.weight if options.get("weighted", True) else None
    q = modularity(c.pre, c.post, labels, weights=weights)
    return 0.0 if np.isnan(q) else float(q)


@register_target(
    name="nearest_neighbour_regularity",
    title="Nearest Neighbour Regularity",
    description="Regularity index (mean/s.d. of nearest-neighbour distance) of cell positions.",
    unit="",
    default_scale=0.2,
    requires_spiking=False,
    options_schema={"cell_type": {"type": "int"}, "region": {"type": "int"}}
)
def target_nearest_neighbour_regularity(tissue: Tissue, options: Optional[Dict[str, Any]] = None) -> float:
    from neurogenesis.analysis.structure import nearest_neighbour_regularity
    options = options or {}
    idx = select(tissue, options) if options else np.flatnonzero(tissue.alive)
    if len(idx) < 3:
        return 0.0
    pos = tissue.positions[idx]
    r = nearest_neighbour_regularity(pos[:, :2] if pos.shape[1] >= 2 else pos)
    return 0.0 if np.isnan(r) else float(r)


@register_target(
    name="within_group_fraction",
    title="Within Group Fraction",
    description="Fraction of synapses whose pre and post cells share the same group label.",
    unit="",
    default_scale=0.1,
    requires_spiking=False,
    options_schema={"partition": {"type": "string", "enum": ["cell_type", "region"], "default": "cell_type"}}
)
def target_within_group_fraction(tissue: Tissue, options: Optional[Dict[str, Any]] = None) -> float:
    from neurogenesis.analysis.structure import within_group_fraction
    options = options or {}
    c = tissue.connectivity
    if len(c.pre) == 0:
        return 0.0
    partition = options.get("partition", "cell_type")
    labels = getattr(tissue, partition) if hasattr(tissue, partition) else tissue.cell_type
    frac = within_group_fraction(c.pre, c.post, labels)
    return 0.0 if np.isnan(frac) else float(frac)


@register_target(
    name="connection_lengths",
    title="Mean Connection Length",
    description="Mean Euclidean length of all synapses in space units.",
    unit="space units",
    default_scale=0.1,
    requires_spiking=False
)
def target_connection_lengths(tissue: Tissue, options: Optional[Dict[str, Any]] = None) -> float:
    from neurogenesis.analysis.structure import connection_lengths
    c = tissue.connectivity
    if len(c.pre) == 0:
        return 0.0
    lengths = connection_lengths(tissue.positions, c.pre, c.post)
    return float(np.mean(lengths)) if len(lengths) else 0.0


# Built-in Spatial Map Targets
@register_target(
    name="pinwheel_density",
    title="Pinwheel Density",
    description="Density of orientation pinwheels per unit area.",
    unit="pinwheels/area",
    default_scale=1.0,
    requires_spiking=False,
    options_schema={"field": {"type": "string"}, "bounds": {"type": "array"}, "spacing": {"type": "float"}}
)
def target_pinwheel_density(tissue: Tissue, options: Optional[Dict[str, Any]] = None) -> float:
    from neurogenesis.fields.maps import find_pinwheels, PinwheelField
    from neurogenesis.fields.core import Field, field_from_dict
    options = options or {}
    field = options.get("field")
    if isinstance(field, dict):
        field = field_from_dict(field)

    bounds = options.get("bounds", ([0.0, 0.0], [1.0, 1.0]))
    b_min, b_max = np.asarray(bounds[0], float)[:2], np.asarray(bounds[1], float)[:2]
    area = max(float(np.prod(b_max - b_min)), 1e-6)

    if isinstance(field, PinwheelField):
        return float(len(field.singularities) / area)

    if hasattr(field, "values"):
        spacing = float(options.get("spacing", 0.05))
        from neurogenesis.fields.maps import regular_points, _regular_axes
        axes = _regular_axes((b_min, b_max), spacing)
        grid_shape = [len(a) for a in axes]
        pts = regular_points((b_min, b_max), spacing)
        angles = field.values(pts).reshape(*grid_shape)
        pos, _ = find_pinwheels(angles, b_min, spacing)
        return float(len(pos) / area)

    if len(tissue.alive) > 0 and hasattr(tissue, "directions"):
        pos2d = tissue.positions[tissue.alive, :2]
        lo, hi = pos2d.min(0), pos2d.max(0)
        box_area = max(float(np.prod(hi - lo)), 1e-6)
        return float(len(tissue.alive) / box_area)
    return 0.0


@register_target(
    name="field_correlation",
    title="Field Correlation",
    description="Pearson correlation between a spatial field and cell property.",
    unit="",
    default_scale=0.1,
    requires_spiking=False,
    options_schema={"field": {"type": "string"}, "property": {"type": "string", "default": "cell_type"}}
)
def target_field_correlation(tissue: Tissue, options: Optional[Dict[str, Any]] = None) -> float:
    from neurogenesis.fields.core import field_from_dict
    options = options or {}
    field = options.get("field")
    if isinstance(field, dict):
        field = field_from_dict(field)

    idx = select(tissue, options) if ("cell_type" in options or "region" in options) else np.flatnonzero(tissue.alive)
    if len(idx) < 2:
        return 0.0

    pts = tissue.positions[idx]
    if hasattr(field, "values"):
        f_vals = np.asarray(field.values(pts), float).ravel()
    elif callable(field):
        f_vals = np.asarray(field(pts), float).ravel()
    else:
        f_vals = pts[:, 0]

    prop_name = options.get("property", "cell_type")
    if hasattr(tissue, prop_name):
        p_vals = np.asarray(getattr(tissue, prop_name)[idx], float).ravel()
    else:
        p_vals = pts[:, 0]

    if len(f_vals) != len(p_vals):
        f_vals = f_vals[:len(p_vals)]

    std_f, std_p = float(np.std(f_vals)), float(np.std(p_vals))
    if std_f < 1e-12 or std_p < 1e-12:
        return 0.0
    corr = float(np.corrcoef(f_vals, p_vals)[0, 1])
    return 0.0 if np.isnan(corr) else corr


@register_target(
    name="mean_weight",
    title="Mean Weight",
    description="Mean synaptic weight between pre and post cells.",
    unit="toolbox units",
    default_scale=1.0,
    requires_spiking=False
)
def _mean_weight(t: Tissue, o: Optional[Dict[str, Any]] = None) -> float:
    o = o or {}
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


@register_target(
    name="column_fraction",
    title="Column Fraction",
    description="Fraction of synapses between cells in the same cortical column.",
    unit="",
    default_scale=0.1,
    requires_spiking=False
)
def _column_fraction(t: Tissue, o: Optional[Dict[str, Any]] = None) -> float:
    o = o or {}
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


def _sync_builtin_metrics():
    import neurogenesis.fitting as _fitting
    _meta = {
        "cell_count": ("Cell Count", "Number of living cells (optionally of a region / cell type).", "cells", 10.0, False, {"cell_type": "int", "region": "int"}),
        "density": ("Density", "Selected cells per unit volume.", "cells/vol", 1.0, False, {"volume": "float"}),
        "layer_thickness": ("Layer Thickness", "Extent of selected cells along axis.", "space units", 0.1, False, {"axis": "int", "lower": "float", "upper": "float"}),
        "synapse_count": ("Synapse Count", "Synapses between selected pre and post cells.", "synapses", 10.0, False, {"pre_cell_type": "int", "post_cell_type": "int"}),
        "mean_in_degree": ("Mean In-Degree", "Synapses per selected post cell.", "synapses/cell", 1.0, False, {"post_cell_type": "int"}),
        "connection_probability": ("Connection Probability", "Fraction of connected pairs at distance [d_min, d_max).", "", 0.1, False, {"d_min": "float", "d_max": "float"}),
        "firing_rate": ("Firing Rate", "Mean rate (Hz) of selected cells in lif_int simulation.", "Hz", 5.0, True, {"ticks": "int", "ext_current": "int"}),
    }
    for m_name, fn in _fitting.METRICS.items():
        if m_name not in TARGETS:
            if m_name in _meta:
                t, d, u, s, spk, opt = _meta[m_name]
                TARGETS[m_name] = TargetSpec(m_name, fn, title=t, description=d, unit=u, default_scale=s, requires_spiking=spk, options_schema=opt)
            else:
                TARGETS[m_name] = TargetSpec(m_name, fn, title=m_name.replace("_", " ").title(), description=getattr(fn, "__doc__", "") or "", requires_spiking=(m_name == "firing_rate"))

_sync_builtin_metrics()


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
