"""The run bundle handed to the renderers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import FindingAssessment
from somaweave.evidence import EvidenceSet
from somaweave.normalization import NormalizedCase


class RunBundle(BaseModel):
    """Everything a report needs for one case run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    generated_at: datetime
    somaweave_version: str
    offline: bool = False
    case: NormalizedCase
    technical_summary: dict[str, Any] = Field(default_factory=dict, description="Output of somaweave.technical.technical_summary.")
    evidence_sets: list[EvidenceSet] = Field(default_factory=list)
    findings: list[FindingAssessment] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict, description="Manifest-level provenance (versions, hashes, config path).")

    def evidence_set(self, alteration_id: str) -> EvidenceSet:
        for es in self.evidence_sets:
            if es.alteration_id == alteration_id:
                return es
        raise KeyError(alteration_id)
