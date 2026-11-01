import numpy as np
import pytest
from neurogenesis.development.rules import GuidanceContext
from neurogenesis.development.sparse_guidance import sparse_guidance

class MockPlan:
    def __init__(self, rules=None):
        self.rules = rules or {}

def test_exact_equivalence():
    Ns, Nd = 100, 150
    rng_init = np.random.default_rng(42)
    
    pos_src = rng_init.random((Ns, 3))
    pos_dst = rng_init.random((Nd, 3))
    target = pos_src.copy()
    
    rng1 = np.random.default_rng(99)
    rng2 = np.random.default_rng(99)
    
    gd = {"sigma": 0.2, "p0": 0.5, "source": "exc"}
    inhibitory_src = np.zeros(Ns, bool)
    inhibitory_src[:50] = True
    
    ctx1 = GuidanceContext(
        src="A", dst="B",
        pos_src=pos_src, pos_dst=pos_dst,
        inhibitory_src=inhibitory_src,
        identity_src=None,
        gd=gd,
        target=target
    )
    
    ctx2 = GuidanceContext(
        src="A", dst="B",
        pos_src=pos_src.copy(), pos_dst=pos_dst.copy(),
        inhibitory_src=inhibitory_src.copy(),
        identity_src=None,
        gd=gd,
        target=target.copy()
    )
    
    plan = MockPlan({"probability": ["source_sign"]})
    
    pre1, post1, p1 = sparse_guidance(ctx1, plan, rng1, exact=True)
    
    d2 = ((pos_dst[None, :, :] - target[:, None, :]) ** 2).sum(-1)
    p_dense = gd["p0"] * np.exp(-d2 / (2 * gd["sigma"] ** 2))
    ctx2.p = p_dense
    from neurogenesis.development.rules import RULES
    RULES["probability"]["source_sign"](ctx2)
    
    rnd = rng2.random(ctx2.p.shape)
    pre2, post2 = np.nonzero(rnd < ctx2.p)
    
    np.testing.assert_array_equal(pre1, pre2)
    np.testing.assert_array_equal(post1, post2)
    np.testing.assert_allclose(p1, ctx2.p[pre2, post2])

def test_sparse_guidance_memory_and_function():
    Ns, Nd = 50000, 50000
    rng = np.random.default_rng(42)
    
    pos_src = rng.random((Ns, 3))
    pos_dst = rng.random((Nd, 3))
    target = pos_src.copy()
    
    # sigma = 0.01 -> radius = 0.05 -> ~30 neighbors per cell.
    # Total dense matrix would be 50k x 50k = 2.5 billion elements (10GB float32), which would OOM.
    # This sparse approach shouldn't OOM.
    gd = {"sigma": 0.01, "p0": 0.5, "source": "exc"}
    inhibitory_src = np.zeros(Ns, bool)
    inhibitory_src[25000:] = True
    
    ctx = GuidanceContext(
        src="A", dst="B",
        pos_src=pos_src, pos_dst=pos_dst,
        inhibitory_src=inhibitory_src,
        identity_src=None,
        gd=gd,
        target=target
    )
    
    plan = MockPlan({"probability": ["source_sign"]})
    
    pre, post, p = sparse_guidance(ctx, plan, rng, c=5.0, exact=False)
    
    assert len(pre) > 0
    assert len(pre) == len(post)
    # Check that inhibitory neurons didn't form synapses (due to source_sign="exc")
    assert not np.any(ctx.inhibitory_src[pre])

