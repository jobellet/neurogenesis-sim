"""Declared safe ranges of stage parameters.

`PARAM_BOUNDS[stage][param] = (lo, hi)` says that the stage accepts every value of that scalar parameter in [lo, hi]
(ends included) without error, whatever the other parameters are within their own ranges. They are ranges of validity of
the code, not of biology: a virtual gene may take any value inside them, including values found in no species. A profile
default (`examples/profiles`) must lie inside them, and `tests/test_stage_bounds.py` runs each listed stage on random
values and on the corners of the box. Add a stage here when it gets a numeric parameter that users will draw from a gene
or a `Fit`; the test then asks for a harness for it.
"""
from typing import Dict, Optional, Tuple

PARAM_BOUNDS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "proliferate": {"prob": (0.0, 1.0), "jitter": (0.0, 5.0)},
    "cell_cycle_clock": {"k": (0.0, 1.0), "a": (0.0, 6.0)},
    "transporter_switch": {
        "e_immature": (-120.0, 20.0), "e_mature": (-120.0, 20.0), "midpoint": (-50.0, 200.0),
        "width": (1e-3, 100.0), "activity_gain": (0.0, 20.0), "v_rest": (-120.0, 20.0),
    },
}


def param_bounds(stage: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """The declared ranges of a stage's scalar parameters, or None."""
    return PARAM_BOUNDS.get(stage)
