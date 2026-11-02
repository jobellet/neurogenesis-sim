import numpy as np
from typing import Tuple, Any

from neurogenesis.spatial import CellList
from neurogenesis.development.rules import RULES, GuidanceContext

def sparse_guidance(
    ctx: GuidanceContext,
    plan: Any,
    rng: np.random.Generator,
    c: float = 5.0,
    exact: bool = False
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes synaptic connections using sparse candidate selection or dense exact match.

    Returns:
        pre (np.ndarray): Source indices of formed synapses.
        post (np.ndarray): Target indices of formed synapses.
        p_formed (np.ndarray): The probabilities used to form these synapses (can be used for debugging).
    """
    gd = ctx.gd
    sigma = float(gd.get("sigma", 0.1))  # defaults as in grow_axons
    p0 = float(gd.get("p0", 0.0))

    if exact:
        # EXACT MODE: Identical to dense grow.py
        d2 = ((ctx.pos_dst[None, :, :] - ctx.target[:, None, :]) ** 2).sum(-1)
        ctx.p = p0 * np.exp(-d2 / (2 * sigma ** 2))
        
        for r in plan.rules.get("probability", ()):
            RULES["probability"][r](ctx)
            
        rnd = rng.random(ctx.p.shape)
        pre, post = np.nonzero(rnd < ctx.p)
        return pre, post, ctx.p[pre, post]
    
    # SPARSE MODE
    radius = c * sigma
    cl = CellList(ctx.pos_dst, cutoff=radius)
    # Query targets within radius of each ctx.target
    pre, post, dists = cl.query_radius(ctx.target, radius, return_distances=True)
    
    if len(pre) == 0:
        return np.zeros(0, dtype=int), np.zeros(0, dtype=int), np.zeros(0, dtype=float)
        
    p_sparse = p0 * np.exp(-(dists ** 2) / (2 * sigma ** 2))
    
    # Apply probability rules sparsely.
    # Since we can't build the dense matrix, we intercept known rules and apply them equivalently.
    for r in plan.rules.get("probability", ()):
        if r == "identity_expression":
            if ctx.identity_src is not None and "type_s" in ctx.gd:
                factor = np.clip(np.asarray(ctx.gd["type_s"], float)[ctx.identity_src], 0.0, 1.0)
                p_sparse = p_sparse * factor[pre]
        elif r == "no_autapse":
            if ctx.src == ctx.dst:
                mask = pre != post
                pre = pre[mask]
                post = post[mask]
                p_sparse = p_sparse[mask]
        elif r == "source_sign":
            if ctx.gd.get("source") in ("exc", "inh"):
                is_inh = (ctx.gd["source"] == "inh")
                mask = (ctx.inhibitory_src[pre] == is_inh)
                p_sparse = p_sparse * mask
        else:
            raise NotImplementedError(f"Probability rule '{r}' is not supported in sparse guidance mode.")

    # Independent pair evaluation
    formed = rng.random(len(p_sparse)) < p_sparse
    pre = pre[formed]
    post = post[formed]
    p_sparse = p_sparse[formed]
    
    return pre, post, p_sparse
