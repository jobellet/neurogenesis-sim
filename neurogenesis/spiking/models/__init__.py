"""Neuron models over one shared transmission layer (synapses, delays, drivers): choose the level of biophysical detail
per simulation; estimate its cost first with neurogenesis.cost."""
from . import hh, lif_int, two_compartment

MODELS = {m.name: m for m in (lif_int, two_compartment, hh)}


def get_model(name):
    if name not in MODELS:
        raise KeyError(f"unknown neuron model {name!r}; available: {sorted(MODELS)}")
    return MODELS[name]


def register_model(module):
    """Add a neuron model (a module or object with name, description, substeps, state_bytes, flops, init_state, tick)."""
    for attr in ("name", "description", "substeps", "state_bytes", "flops", "init_state", "tick"):
        assert hasattr(module, attr), f"a neuron model needs {attr}"
    MODELS[module.name] = module
