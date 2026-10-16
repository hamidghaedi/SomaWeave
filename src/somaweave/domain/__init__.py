"""Canonical SomaWeave data types.

This package holds pure data models only: no network calls, no file IO beyond
what pydantic needs to validate. Everything downstream (normalization,
technical assessment, providers, interpretation, reporting) consumes and
produces these types.
"""

from somaweave.domain.enums import (
    AlterationType,
    Assembly,
    ClinicalEventType,
    DiseaseMatch,
    EvidenceCategory,
    EvidenceDirection,
    MatchSpecificity,
    Preservation,
    SourceStatus,
    SpecimenRole,
    TreatmentResponse,
)
from somaweave.domain.alteration import (
    Alteration,
    AlterationMeasurement,
    CopyNumberState,
    FusionPartner,
    GenomicPosition,
    ReadSupport,
)
from somaweave.domain.case import (
    Case,
    ClinicalEvent,
    Diagnosis,
    DiseaseHypothesis,
    PurityEstimate,
    Specimen,
    TreatmentEvent,
)
from somaweave.domain.evidence import (
    Citation,
    DiseaseReference,
    EvidenceRecord,
    SourceQuery,
    SourceQueryResult,
)
from somaweave.domain.assessment import (
    ActionabilityAssessment,
    AnalyticalReliability,
    CaseRelevance,
    FindingAssessment,
    OncogenicityAssessment,
)

__all__ = [name for name in dir() if not name.startswith("_")]
