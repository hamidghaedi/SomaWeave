"""Progressive evidence retrieval: plan tiers, run them, deduplicate."""

from somaweave.retrieval.plan import (
    DEFAULT_TIER_PROVIDERS,
    GENE_PATHWAYS,
    PlanItem,
    build_query_plan,
    protein_change_terms,
    to_one_letter,
    to_three_letter,
)
from somaweave.retrieval.run import (
    RetrievalResult,
    dedupe_evidence,
    run_plan,
    stop_after_tier,
    stop_when_curated_evidence,
)

__all__ = [
    "DEFAULT_TIER_PROVIDERS", "GENE_PATHWAYS", "PlanItem", "RetrievalResult", "build_query_plan", "dedupe_evidence",
    "protein_change_terms", "run_plan", "stop_after_tier", "stop_when_curated_evidence", "to_one_letter", "to_three_letter",
]
