"""Evidence reconciliation: disease matching, grouping, conflicts, coverage.

Pure functions over canonical domain objects. No network access.
"""

from somaweave.evidence.reconcile import (
    ACCEPTED_CLINVAR_REVIEW_TERMS,
    MISSING_STATUSES,
    QUERIED_OK_STATUSES,
    Conflict,
    CoverageState,
    EvidenceGroup,
    EvidenceSet,
    Provenance,
    SourceCoverage,
    civic_significance,
    coverage_from_results,
    is_accepted,
    reconcile,
)

__all__ = [
    "ACCEPTED_CLINVAR_REVIEW_TERMS", "MISSING_STATUSES", "QUERIED_OK_STATUSES", "Conflict", "CoverageState",
    "EvidenceGroup", "EvidenceSet", "Provenance", "SourceCoverage", "civic_significance", "coverage_from_results",
    "is_accepted", "reconcile",
]
from somaweave.evidence.applicability import Applicability, applicability_for, classify_profile, one_letter_protein  # noqa: E402,F401
