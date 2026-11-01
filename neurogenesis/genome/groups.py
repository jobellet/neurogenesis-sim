"""Gene groups: the genes of one developmental mechanism for one region or projection."""
from __future__ import annotations


def guidance_genes(src, dst, w_lo=20.0, w_hi=512.0):
    """Positional guidance of a projection: B (3 x 3), c (3), sigma, p0, w."""
    k = (src, dst)
    g = [(("guidance", k, "B", i, j), -2.0, 2.0) for i in range(3) for j in range(3)]
    g += [(("guidance", k, "c", i), -3.0, 3.0) for i in range(3)]
    return g + [(("guidance", k, "sigma"), 0.03, 0.5), (("guidance", k, "p0"), 0.05, 1.0), (("guidance", k, "w"), w_lo, w_hi)]


def field_genes(src, dst, w_lo=0.0, w_hi=512.0):
    """Field width, probability and weight of a projection (no change of its topography)."""
    k = (src, dst)
    return [(("guidance", k, "sigma"), 0.03, 0.5), (("guidance", k, "p0"), 0.0, 1.0), (("guidance", k, "w"), w_lo, w_hi)]


def body_genes(region, count=(16, 256)):
    """Count, excitability, migration and inhibitory fraction of a grown region."""
    c = region
    g = [(("count", c), *count), (("excitability", c, "shift_v"), 2, 6), (("excitability", c, "shift_s"), 1, 5)]
    g += [(("migration", c, "mean", i), 0.0, 1.0) for i in range(3)] + [(("migration", c, "spread"), 0.05, 0.5)]
    return g + [(("inhibitory", c, "a0"), -4.0, 2.0)] + [(("inhibitory", c, "a", i), -4.0, 4.0) for i in range(3)]


def differentiation_genes(region):
    """Lateral-inhibition differentiation of a region (neurogenesis.development.differentiation)."""
    d = ("differentiation", region)
    g = [(d + ("exc", "b0"), -6.0, 6.0)] + [(d + ("exc", "b", i), -6.0, 6.0) for i in range(3)]
    g += [(d + ("exc", "c"), 0.0, 4.0), (d + ("exc", "r"), 0.03, 0.5), (d + ("pace", "b0"), -8.0, 4.0), (d + ("pace", "c"), 0.0, 4.0),
          (d + ("pace", "r"), 0.03, 0.5)]
    return g + [(d + ("theta0",), -1.0, 1.0), (d + ("theta1",), -2.0, 2.0), (d + ("s1v",), -4.0, 4.0), (d + ("s1s",), -4.0, 4.0),
                (d + ("period",), 20.0, 200.0), (d + ("duty",), 4.0, 40.0)]


def identity_genes(region, k=6, root="identity"):
    """Molecular identity code of a region: K x (a_k0, a_k) logits."""
    return [((root, region, "logits", t, j), -4.0, 4.0) for t in range(k) for j in range(4)]


def typed_guidance_genes(src, dst, k=6):
    """Identity-dependent guidance of a projection: per source identity, a target offset (3) and an expression level (1)."""
    key = (src, dst)
    return ([(("guidance", key, "type_c", t, i), -3.0, 3.0) for t in range(k) for i in range(3)]
            + [(("guidance", key, "type_s", t), 0.0, 1.0) for t in range(k)])
