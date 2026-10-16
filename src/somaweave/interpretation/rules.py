"""Rule tables for the four interpretation axes.

Every rule is deterministic and documented here so a reviewer can audit why a
classification was produced. Tags labelled with ClinGen/CGC/VICC codes are
*approximations* derived from curated-source evidence counts; the formal
criteria depend on sample counts and functional data that are not available
to this module.

Analytical reliability (``ANALYTICAL_RULES``)
    The level is taken from ``somaweave.technical``; across tumour
    specimens the worst level wins (``RELIABILITY_ORDER``). No measurement
    gives ``not_assessable``.

Oncogenicity (``ONCOGENICITY_RULES``)
    Evidence pool: *accepted* curated records (CIViC accepted, ClinVar with
    criteria) in the oncogenic, predictive, prognostic or diagnostic
    categories whose direction is not ``does_not_support``, plus accepted
    functional records. ClinVar germline-oriented blocks are excluded.
    Tags:
      OS1  accepted exact-variant record in the oncogenic category whose
           classification states oncogenic/likely oncogenic.
      OS2  accepted functional record at the exact variant supporting an
           oncogenic effect.
      OS3  >= 3 accepted curated records at exact-variant or codon level
           (hotspot treated as well established; approximation).
      OM3  1-2 accepted curated records at exact-variant or codon level
           (hotspot treated as recurrent but not well established).
      SBS2 accepted functional record at the exact variant that does not
           support an oncogenic effect.
      SBx  accepted exact-variant classification stating benign/likely
           benign (ClinVar oncogenicity block or CIViC benign significance).
      Computational predictor criteria (OP1/SBP1) are never applied; the
      module records "computational evidence not assessed".
    Classification (first matching row wins):
      oncogenic            exact-variant accepted supportive records from
                           >= 2 independent sources, or >= 3 such records,
                           and no accepted benign evidence.
      likely_oncogenic     any exact-variant accepted supportive record
                           (single source, < 3 items) or any codon-level
                           accepted supportive record, and no benign record.
      likely_benign/benign only with explicit accepted benign evidence and no
                           supportive record (benign needs >= 2 sources).
      uncertain_significance  otherwise, including when supportive and
                           benign evidence coexist (flagged for review).
      not_assessed         no curated source could be queried at all.
    Upstream caller annotations (``alteration.annotations``) are quoted as
    "reported by upstream" and never counted as evidence.

Actionability (``ACTIONABILITY_RULES`` and ``actionability_tier_for``)
    Evidence pool: accepted predictive, prognostic or diagnostic records with
    direction ``supports``. Each record is tiered by disease match and
    source-native level; the best (lowest) tier is reported.
      Tier I   disease_match SAME and guideline-grade level (CIViC A/B).
      Tier II  SAME with level C, or PARENT with A/B.
      Tier III SAME with level D/E (preclinical/inferential), PARENT with
               C/D/E, RELATED, DIFFERENT, PAN_CANCER or UNKNOWN match
               (cross_cancer_extrapolation=True unless the match is
               UNKNOWN), and any record whose variant match is only at
               gene level.
      Tier IV  curated sources were queried and nothing accepted applies.
      not_assessed  no curated source could be queried.
    AMP level: A/B/C/D from the source-native level (E -> D); not_assessed
    when none.

Case relevance (``RELEVANCE_RULES``)
      high          accepted same- or parent-disease clinical evidence
                    (tier I/II) exists.
      moderate      tier III evidence that concerns an agent the patient
                    received before/at specimen collection, or same-disease
                    evidence at gene level only.
      low           only cross-cancer or unresolved-disease evidence with no
                    link to the recorded treatments.
      none          curated sources queried successfully and no accepted
                    evidence applies.
      not_assessable  curated sources missing.
    Missing dates, purity, or unresolved disease hypotheses produce
    ``unresolved_questions``, never conclusions.
"""

from __future__ import annotations

from somaweave.domain import DiseaseMatch, MatchSpecificity

RELIABILITY_ORDER: dict[str, int] = {"not_assessable": 0, "unreliable": 1, "low": 2, "moderate": 3, "high": 4}

ANALYTICAL_RULES: dict[str, str] = {
    "source": "somaweave.technical.assess_alteration level per tumour specimen",
    "aggregation": "worst level across tumour specimens (order: not_assessable < unreliable < low < moderate < high)",
    "none": "no tumour measurement -> not_assessable",
}

ONCOGENICITY_RULES: dict[str, str] = {
    "pool": "accepted curated records; categories oncogenic/predictive/prognostic/diagnostic with direction != does_not_support, plus accepted functional records; ClinVar germline blocks excluded",
    "OS1": "accepted exact-variant oncogenic-category record stating oncogenic or likely oncogenic",
    "OS2": "accepted exact-variant functional record supporting an oncogenic effect",
    "OS3": ">= 3 accepted curated records at exact-variant or codon level (approximation of a well-established hotspot)",
    "OM3": "1-2 accepted curated records at exact-variant or codon level (recurrent, not well established)",
    "SBS2": "accepted exact-variant functional record not supporting an oncogenic effect",
    "SBx": "accepted exact-variant classification stating benign or likely benign",
    "OP1/SBP1": "computational predictor evidence not assessed (no predictor data)",
    "oncogenic": "exact-variant accepted supportive records from >= 2 independent sources or >= 3 records; no accepted benign evidence",
    "likely_oncogenic": "exact-variant accepted supportive record (single source, < 3 records) or codon-level accepted supportive record; no accepted benign evidence",
    "likely_benign": "exactly one source with accepted exact-variant benign classification and no supportive record",
    "benign": ">= 2 sources with accepted exact-variant benign classification and no supportive record",
    "uncertain_significance": "otherwise, including coexisting supportive and benign evidence",
    "not_assessed": "no curated source queried successfully",
}

GUIDELINE_GRADE_LEVELS: frozenset[str] = frozenset({"A", "B"})
CASE_STUDY_LEVELS: frozenset[str] = frozenset({"C"})
PRECLINICAL_LEVELS: frozenset[str] = frozenset({"D", "E"})
SPECIFIC_MATCHES: frozenset[MatchSpecificity] = frozenset({
    MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON, MatchSpecificity.FUNCTIONAL_EQUIVALENT,
    MatchSpecificity.GENE_ALTERATION_CLASS,
})

ACTIONABILITY_RULES: dict[str, str] = {
    "pool": "accepted predictive/prognostic/diagnostic records with direction supports",
    "I": "disease_match same_disease and source level A or B",
    "II": "same_disease with level C, or parent_disease with level A or B",
    "III": "same_disease with level D/E, parent_disease with C/D/E, related/different/pan-cancer/unknown disease match, or gene-level variant match only",
    "IV": "curated sources queried; no accepted applicable record",
    "not_assessed": "no curated source queried successfully",
    "cross_cancer_extrapolation": "True when the best record is parent (lower level), related, different or pan-cancer",
}

RELEVANCE_RULES: dict[str, str] = {
    "high": "tier I or II evidence present",
    "moderate": "tier III evidence concerning an agent received before/at specimen collection, or same-disease gene-level evidence",
    "low": "only cross-cancer or unresolved-disease evidence without a link to recorded treatments",
    "none": "curated sources queried, no accepted evidence applies",
    "not_assessable": "curated sources missing",
}


def amp_level_for(native_level: str | None) -> str:
    """Map a source-native level letter to an AMP level string; ``not_assessed`` if unknown."""
    if not native_level:
        return "not_assessed"
    lv = native_level.strip().upper()
    if lv in ("A", "B", "C", "D"):
        return lv
    if lv == "E":
        return "D"
    return "not_assessed"


def actionability_tier_for(disease_match: DiseaseMatch, native_level: str | None,
                           variant_match: MatchSpecificity) -> tuple[str, bool, str]:
    """Return ``(tier, cross_cancer_extrapolation, reason)`` for one accepted clinical record."""
    lv = (native_level or "").strip().upper()
    if variant_match not in SPECIFIC_MATCHES:
        return "III", disease_match in (DiseaseMatch.RELATED, DiseaseMatch.DIFFERENT, DiseaseMatch.PAN_CANCER), \
            f"variant match is {variant_match.value}; gene-level evidence capped at tier III"
    if disease_match == DiseaseMatch.SAME:
        if lv in GUIDELINE_GRADE_LEVELS:
            return "I", False, f"same disease, level {lv}"
        if lv in CASE_STUDY_LEVELS:
            return "II", False, f"same disease, level {lv} (case studies)"
        return "III", False, f"same disease, level {lv or 'unspecified'} (preclinical/inferential or unspecified)"
    if disease_match == DiseaseMatch.PARENT:
        if lv in GUIDELINE_GRADE_LEVELS:
            return "II", False, f"parent disease, level {lv}"
        return "III", True, f"parent disease, level {lv or 'unspecified'}"
    if disease_match == DiseaseMatch.UNKNOWN:
        return "III", False, "disease match unresolved (label not in OncoTree table); treated as not same-disease"
    return "III", True, f"{disease_match.value}, level {lv or 'unspecified'}; cross-cancer extrapolation"
