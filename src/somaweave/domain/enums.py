"""Controlled vocabularies shared across SomaWeave."""

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class Assembly(StrEnum):
    GRCH37 = "GRCh37"
    GRCH38 = "GRCh38"


class SpecimenRole(StrEnum):
    TUMOR = "tumor"
    NORMAL = "normal"


class Preservation(StrEnum):
    FFPE = "FFPE"
    FRESH_FROZEN = "fresh_frozen"
    BLOOD = "blood"
    SALIVA = "saliva"
    CELL_FREE = "cell_free"
    OTHER = "other"
    UNKNOWN = "unknown"


class AlterationType(StrEnum):
    SNV = "SNV"
    MNV = "MNV"
    INSERTION = "insertion"
    DELETION = "deletion"
    DELINS = "delins"
    CNA = "CNA"
    SV = "SV"
    FUSION = "fusion"
    OTHER = "other"


class ClinicalEventType(StrEnum):
    DIAGNOSIS = "diagnosis"
    PROGRESSION = "progression"
    RECURRENCE = "recurrence"
    METASTASIS = "metastasis"
    SURGERY = "surgery"
    DEATH = "death"
    OTHER = "other"


class TreatmentResponse(StrEnum):
    COMPLETE = "complete_response"
    PARTIAL = "partial_response"
    STABLE = "stable_disease"
    PROGRESSION = "progressive_disease"
    NOT_EVALUATED = "not_evaluated"
    UNKNOWN = "unknown"


class SourceStatus(StrEnum):
    """Outcome of a query against one source.

    These states are deliberately distinct. ``NO_RECORDS`` is a successful
    query that returned nothing; it is the only state that can be read as
    absence of curated evidence in that source. All other non-``OK`` states
    are *missing* evidence and must never be treated as negative evidence.
    """

    OK = "ok"
    NO_RECORDS = "no_records"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    NOT_QUERIED = "not_queried"
    NO_CREDENTIALS = "no_credentials"
    NOT_SUPPORTED = "not_supported"


class MatchSpecificity(StrEnum):
    """How closely retrieved evidence matches the case alteration.

    Ordered from most to least specific; the retrieval planner walks these
    tiers progressively.
    """

    EXACT_VARIANT = "exact_variant"
    CODON = "codon"
    FUNCTIONAL_EQUIVALENT = "functional_equivalent"
    GENE_ALTERATION_CLASS = "gene_alteration_class"
    GENE = "gene"
    PATHWAY = "pathway"
    DISEASE_ONLY = "disease_only"


class DiseaseMatch(StrEnum):
    SAME = "same_disease"
    PARENT = "parent_disease"
    RELATED = "related_disease"
    DIFFERENT = "different_disease"
    PAN_CANCER = "pan_cancer"
    UNKNOWN = "unknown"


class EvidenceCategory(StrEnum):
    DIAGNOSTIC = "diagnostic"
    PROGNOSTIC = "prognostic"
    PREDICTIVE = "predictive"
    ONCOGENIC = "oncogenic"
    FUNCTIONAL = "functional"
    MECHANISTIC = "mechanistic"
    EPIDEMIOLOGIC = "epidemiologic"
    TRIAL = "trial"  # clinical-trial registry entry: context only, never accepted evidence
    OTHER = "other"


class EvidenceDirection(StrEnum):
    SUPPORTS = "supports"
    DOES_NOT_SUPPORT = "does_not_support"
    CONFLICTING = "conflicting"
    NOT_APPLICABLE = "not_applicable"
