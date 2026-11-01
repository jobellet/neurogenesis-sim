"""
Stage registry and auto-discovery.
"""
import pkgutil
import importlib

from neurogenesis.stages.base import Stage, register_stage, run_schedule

# Auto-discover all modules in this package to register their stages
__all__ = ["Stage", "register_stage", "run_schedule"]

for _, module_name, _ in pkgutil.iter_modules(__path__):
    importlib.import_module(f".{module_name}", package=__name__)
