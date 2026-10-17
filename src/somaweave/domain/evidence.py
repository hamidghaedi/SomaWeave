"""Canonical evidence representation, independent of any provider.

Every provider adapter must translate its native response into
``EvidenceRecord`` objects and a ``SourceQueryResult`` describing the query
outcome. Provider-specific structures must not leak past the adapter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain.enums import (
    DiseaseMatch,
    EvidenceCategory,
    EvidenceDirection,
    MatchSpecificity,
    SourceStatus,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Citation(_Model):
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=1800, le=2200)
    source_label: Optional[str] = Field(default=None, description="e.g. 'FDA label', 'NCCN guideline', 'abstract'.")


class DiseaseReference(_Model):
    name: str
    oncotree_code: Optional[str] = None
    doid: Optional[str] = None
    other_identifiers: dict[str, str] = Field(default_factory=dict)


class SourceQuery(_Model):
    """What was asked of a source."""

    source_name: str
    tier: MatchSpecificity
    query_terms: dict[str, Any] = Field(default_factory=dict, description="Provider-neutral description of the query.")
    native_request: Optional[str] = Field(default=None, description="Native request (URL/GraphQL) for audit; no secrets.")


class SourceQueryResult(_Model):
    """Outcome of one query. ``status`` must be set honestly: a failed or
    skipped query is missing evidence, not negative evidence."""

    query: SourceQuery
    status: SourceStatus
    retrieved_at: datetime
    source_version: Optional[str] = Field(default=None, description="Database release/version or API build if exposed.")
    record_count: int = Field(default=0, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    message: Optional[str] = Field(default=None, description="Error text or notes; no secrets.")
    duration_ms: Optional[int] = Field(default=None, ge=0)


class EvidenceRecord(_Model):
    evidence_id: str = Field(description="Stable SomaWeave id, e.g. 'civic:eid:1234'.")
    source_name: str
    source_native_id: str
    source_url: Optional[str] = None
    source_version: Optional[str] = None
    retrieval_status: SourceStatus = SourceStatus.OK
    retrieved_at: datetime
    query_tier: MatchSpecificity = Field(description="Tier of the query that returned this record.")
    variant_match: MatchSpecificity = Field(description="How specifically this record matches the case alteration.")
    disease_match: DiseaseMatch = DiseaseMatch.UNKNOWN
    gene_symbol: Optional[str] = None
    variant_description: Optional[str] = Field(default=None, description="Variant as described by the source.")
    disease: Optional[DiseaseReference] = Field(default=None, description="Primary disease named by the source (first condition for multi-condition records).")
    conditions: list[DiseaseReference] = Field(default_factory=list, description="All conditions/diseases named by the source when more than one; matching should consider each.")
    evidence_category: EvidenceCategory
    assertion: str = Field(description="The claim, in the source's own terms.")
    direction: EvidenceDirection = EvidenceDirection.NOT_APPLICABLE
    drugs: list[str] = Field(default_factory=list)
    source_native_level: Optional[str] = Field(default=None, description="e.g. CIViC level 'B', OncoKB '1', ClinVar review status.")
    source_native_rating: Optional[str] = None
    source_native_status: Optional[str] = Field(default=None, description="e.g. accepted/submitted, or ClinVar significance.")
    study_design: Optional[str] = None
    sample_size: Optional[int] = Field(default=None, ge=0)
    citations: list[Citation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    is_hypothesis: bool = Field(default=False, description="True for mechanistic/exploratory associations, not validated biomarkers.")
    raw_reference: Optional[str] = Field(default=None, description="Pointer to the cached raw provider payload (path or key).")
