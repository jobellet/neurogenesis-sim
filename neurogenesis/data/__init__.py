"""Connectome data layer (Phase I): dataset manifests and downloads, streaming import, registration, weight mapping."""
from .catalogue import DataError, data_dir, describe, fetch, load_manifest
from .importer import import_connectome, map_weights, read_batches, transform_positions
from .registration import roi_mask_geometry, column_coordinates_field
from .skeletons import attach_connectome_skeletons, import_connectome_skeletons, simplify_arbor_rdp
from .targets import compare_type_statistics, extract_fitting_targets

__all__ = ["DataError", "data_dir", "describe", "fetch", "load_manifest", "import_connectome", "map_weights",
           "read_batches", "transform_positions", "roi_mask_geometry", "column_coordinates_field", "attach_connectome_skeletons", "import_connectome_skeletons",
           "simplify_arbor_rdp", "compare_type_statistics", "extract_fitting_targets"]
