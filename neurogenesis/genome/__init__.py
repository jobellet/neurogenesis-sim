"""Genomes: nested dicts of genes; gene addressing, [0, 1] coding, gene groups and JSON."""
from .genes import INTEGER_ROOTS, from_unit, get_gene, rebound, set_gene, to_unit
from .groups import body_genes, differentiation_genes, field_genes, guidance_genes, identity_genes, typed_guidance_genes
from .io import from_json, to_json

__all__ = ["INTEGER_ROOTS", "from_unit", "get_gene", "rebound", "set_gene", "to_unit", "body_genes", "differentiation_genes",
           "field_genes", "guidance_genes", "identity_genes", "typed_guidance_genes", "from_json", "to_json"]
