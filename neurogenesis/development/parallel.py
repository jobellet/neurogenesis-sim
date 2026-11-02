"""Parallel development in CPU processes (spawned; JAX restricted to the CPU there). Results equal the serial ones."""
from __future__ import annotations

import concurrent.futures
import multiprocessing

_POOL = None


def _init_worker():
    import os
    os.environ["JAX_PLATFORMS"] = "cpu"


def set_workers(n):
    """Use n worker processes for map_calls (n <= 1: serial, the default)."""
    global _POOL
    if _POOL is not None:
        _POOL.shutdown()
        _POOL = None
    if n and n > 1:
        _POOL = concurrent.futures.ProcessPoolExecutor(n, mp_context=multiprocessing.get_context("spawn"), initializer=_init_worker)


def _call(args):
    fn, kw = args
    return fn(**kw)


def map_calls(fn, calls):
    """``[fn(**kw) for kw in calls]``, in parallel if set_workers was called. fn must be a module-level function.

    Scripts that use workers must guard their entry point with `if __name__ == "__main__":` (spawned workers re-import
    the main module) and should keep JAX imports out of module level, or set JAX_PLATFORMS=cpu when
    __name__ != "__main__", so that workers do not claim the GPU."""
    if _POOL is None:
        return [fn(**kw) for kw in calls]
    return list(_POOL.map(_call, [(fn, kw) for kw in calls], chunksize=max(1, len(calls) // 64)))


def grow_many(calls):
    """``neurogenesis.development.grow(**kw)`` for every kw in calls (keys: plan, genome, seed, regions, projections, name)."""
    from .grow import grow
    return map_calls(grow, calls)
