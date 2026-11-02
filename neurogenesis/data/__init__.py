"""Connectome data layer (Phase I): dataset manifests and downloads, streaming import, registration, weight mapping."""
from .catalogue import DataError, data_dir, describe, fetch, load_manifest
from .importer import import_connectome, map_weights, read_batches, transform_positions

__all__ = ["DataError", "data_dir", "describe", "fetch", "load_manifest", "import_connectome", "map_weights",
           "read_batches", "transform_positions"]
