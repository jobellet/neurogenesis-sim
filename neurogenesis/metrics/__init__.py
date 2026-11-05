"""Functional connectomics metrics and in-silico stimuli (M3)."""
from .function import (
    multiplicity_regression,
    pair_correlations,
    residual_correlations,
    student_t_pvalue,
    tuning_metrics,
)
from .stimuli import generate_natural_movie, movie_input_currents

__all__ = [
    "pair_correlations",
    "residual_correlations",
    "student_t_pvalue",
    "multiplicity_regression",
    "tuning_metrics",
    "generate_natural_movie",
    "movie_input_currents",
]
