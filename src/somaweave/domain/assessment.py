"""Interpretation outputs.

Four axes are assessed and reported separately. There is intentionally no
composite score field; do not add one.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain.enums import DiseaseMatch


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ReliabilityLevel = Literal["high", "moderate", "low", "unreliable", "not_assessable"]
OncogenicityClass = Literal["oncogenic", "likely_oncogenic", "uncertain_significance", "likely_benign", "benign", "not_assessed"]
AmpTier = Literal["I", "II", "III", "IV", "not_assessed"]
AmpLevel = Literal["A", "B", "C", "D", "not_assessed"]
RelevanceLevel = Literal["high", "moderate", "low", "none", "not_assessable"]


class AnalyticalReliability(_Model):
    level: ReliabilityLevel
    flags: list[str] = Field(default_factory=list, description="Technical concerns, e.g. 'low_depth', 'ffpe_c_to_t_context'.")
    rationale: list[str] = Field(default_factory=list)
    specimen_id: Optional[str] = None


class OncogenicityAssessment(_Model):
    classification: OncogenicityClass
    criteria_met: list[str] = Field(default_factory=list, description="ClinGen/CGC/VICC criteria codes, e.g. 'OS3', 'OM1'.")
    rationale: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ActionabilityAssessment(_Model):
    tier: AmpTier
    level: AmpLevel
    disease_match: DiseaseMatch = DiseaseMatch.UNKNOWN
    therapies: list[str] = Field(default_factory=list)
    resistance_to: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    cross_cancer_extrapolation: bool = Field(default=False, description="True if the supporting evidence is from a different cancer type.")


class CaseRelevance(_Model):
    level: RelevanceLevel
    rationale: list[str] = Field(default_factory=list)
    treatment_context: list[str] = Field(default_factory=list, description="e.g. 'variant detected after 3 months of agent X'.")
    unresolved_questions: list[str] = Field(default_factory=list)


class FindingAssessment(_Model):
    alteration_id: str
    analytical: AnalyticalReliability
    oncogenicity: OncogenicityAssessment
    actionability: ActionabilityAssessment
    relevance: CaseRelevance
    established_claims: list[str] = Field(default_factory=list, description="Claims backed by cited evidence_ids.")
    hypotheses: list[str] = Field(default_factory=list, description="Mechanistic or extrapolated statements, labelled as such.")
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list, description="Items requiring expert review.")
    evidence_ids: list[str] = Field(default_factory=list)
