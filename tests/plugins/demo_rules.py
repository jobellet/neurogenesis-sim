"""A third-party rule shipped with a module (tests): halves every weight of projections with gd["halve"]."""
from neurogenesis.development import register


@register("weight", "halve")
def halve(ctx):
    if ctx.gd.get("halve"):
        ctx.w = ctx.w / 2
