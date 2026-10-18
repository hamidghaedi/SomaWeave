"""Normalization layer: structured, provenance-preserving views over a Case.

Pure functions over domain models. No network access, no file IO except the
explicit loaders for optional external tables (HGNC TSV, OncoTree JSON).
"""

from somaweave.normalization.dates import DayInterval, PartialDate, days_between, parse_partial_date
from somaweave.normalization.disease import (
    BUILTIN_ONCOTREE,
    DiseaseContext,
    DiseaseFlag,
    OncoTreeTable,
    build_disease_context, condition_hierarchy,
    disease_match,
    load_oncotree_json,
)
from somaweave.normalization.genes import NormalizedGeneSymbol, load_hgnc_previous_symbols, normalize_gene_symbol
from somaweave.normalization.hgvs import ParsedCodingChange, ParsedProteinChange, parse_coding_hgvs, parse_protein_hgvs
from somaweave.normalization.normalize import (
    NormalizationFlag,
    NormalizedAlteration,
    NormalizedCase,
    NormalizedTreatment,
    normalize_case,
)

__all__ = [name for name in dir() if not name.startswith("_")]
