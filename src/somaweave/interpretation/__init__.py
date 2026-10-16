"""Rule-based interpretation of one alteration along four independent axes.

No composite score is produced. See ``somaweave.interpretation.rules`` for the
rule tables and ``interpret`` for the entry point.
"""

from somaweave.interpretation.interpret import interpret
from somaweave.interpretation.rules import (
    ACTIONABILITY_RULES,
    ANALYTICAL_RULES,
    GUIDELINE_GRADE_LEVELS,
    ONCOGENICITY_RULES,
    RELEVANCE_RULES,
    RELIABILITY_ORDER,
    actionability_tier_for,
)

__all__ = [
    "ACTIONABILITY_RULES", "ANALYTICAL_RULES", "GUIDELINE_GRADE_LEVELS", "ONCOGENICITY_RULES", "RELEVANCE_RULES",
    "RELIABILITY_ORDER", "actionability_tier_for", "interpret",
]
