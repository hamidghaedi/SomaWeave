"""Case, specimen and clinical-history models.

Design rules (see docs/REPOSITORY_CONTRACT.md section 4):
- pathology-confirmed diagnosis is stored separately from classification
  hypotheses;
- treatment start/end dates are independent from specimen dates;
- pathology-estimated and molecularly fitted purity are separate fields.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from somaweave.domain.alteration import Alteration
from somaweave.domain.enums import (
    Assembly,
    ClinicalEventType,
    Preservation,
    SpecimenRole,
    TreatmentResponse,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Diagnosis(_Model):
    """Pathology-confirmed diagnosis as recorded in the source record."""

    name: str
    oncotree_code: Optional[str] = Field(default=None, description="OncoTree code if assigned by the source.")
    icd_o_morphology: Optional[str] = Field(default=None, description="ICD-O-3 morphology, e.g. 8140/3.")
    icd_o_topography: Optional[str] = Field(default=None, description="ICD-O-3 topography, e.g. C18.9.")
    primary_site: Optional[str] = None
    histology: Optional[str] = None
    stage: Optional[str] = None
    grade: Optional[str] = None
    diagnosis_date: Optional[date] = None
    confirmed_by_pathology: bool = Field(default=True)


class DiseaseHypothesis(_Model):
    """A candidate classification that is NOT pathology-confirmed."""

    oncotree_code: Optional[str] = None
    name: str
    rationale: Optional[str] = None
    proposed_by: Optional[str] = Field(default=None, description="Who/what proposed it, e.g. 'molecular review'.")


class ClinicalEvent(_Model):
    event_type: ClinicalEventType
    event_date: Optional[date] = None
    site: Optional[str] = None
    description: Optional[str] = None


class TreatmentEvent(_Model):
    treatment_id: str
    name: str = Field(description="Regimen or agent name as recorded.")
    agents: list[str] = Field(default_factory=list, description="Individual agent names.")
    agent_identifiers: dict[str, str] = Field(default_factory=dict, description="e.g. {'RxNorm': '...', 'ChEMBL': '...'}")
    intent: Optional[str] = Field(default=None, description="curative, adjuvant, neoadjuvant, palliative, ...")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    ongoing: Optional[bool] = None
    best_response: Optional[TreatmentResponse] = None
    response_notes: Optional[str] = None

    @model_validator(mode="after")
    def _dates_ordered(self) -> "TreatmentEvent":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("treatment end_date precedes start_date")
        return self


class PurityEstimate(_Model):
    """Purity values from different methods are kept apart; none is 'the' purity."""

    pathology_min: Optional[float] = Field(default=None, ge=0, le=1, description="Lower bound of pathologist estimate.")
    pathology_max: Optional[float] = Field(default=None, ge=0, le=1)
    molecular_fit: Optional[float] = Field(default=None, ge=0, le=1, description="Purity fitted by a CNA tool.")
    molecular_fit_tool: Optional[str] = None
    molecular_ploidy: Optional[float] = Field(default=None, ge=0)
    fit_ambiguous: Optional[bool] = Field(default=None, description="True if the tool reported an ambiguous fit.")

    @model_validator(mode="after")
    def _range_ordered(self) -> "PurityEstimate":
        if self.pathology_min is not None and self.pathology_max is not None and self.pathology_max < self.pathology_min:
            raise ValueError("pathology_max < pathology_min")
        return self


class Specimen(_Model):
    specimen_id: str
    role: SpecimenRole
    tissue: Optional[str] = None
    anatomical_site: Optional[str] = None
    is_metastatic_site: Optional[bool] = None
    collection_date: Optional[date] = None
    preservation: Preservation = Preservation.UNKNOWN
    purity: Optional[PurityEstimate] = None
    sequencing_assay: Optional[str] = Field(default=None, description="e.g. WGS, WES, targeted panel name.")
    mean_coverage: Optional[float] = Field(default=None, ge=0)
    library_kit: Optional[str] = None
    sequencer: Optional[str] = None
    notes: Optional[str] = None


class Case(_Model):
    schema_version: str = Field(default="case.v1", pattern=r"^case\.v\d+$")
    case_id: str = Field(description="De-identified case identifier.")
    assembly: Assembly
    diagnosis: Diagnosis
    disease_hypotheses: list[DiseaseHypothesis] = Field(default_factory=list)
    clinical_events: list[ClinicalEvent] = Field(default_factory=list)
    treatments: list[TreatmentEvent] = Field(default_factory=list)
    specimens: list[Specimen] = Field(min_length=1)
    alterations: list[Alteration] = Field(default_factory=list)
    sex: Optional[str] = Field(default=None, description="Biological sex if relevant to interpretation.")
    age_at_diagnosis_years: Optional[int] = Field(default=None, ge=0, le=130)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _references_resolve(self) -> "Case":
        ids = [s.specimen_id for s in self.specimens]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate specimen_id")
        alt_ids = [a.alteration_id for a in self.alterations]
        if len(alt_ids) != len(set(alt_ids)):
            raise ValueError("duplicate alteration_id")
        known = set(ids)
        for alt in self.alterations:
            for m in alt.measurements:
                if m.specimen_id not in known:
                    raise ValueError(f"alteration {alt.alteration_id} references unknown specimen {m.specimen_id}")
            if alt.position is not None and alt.position.assembly != self.assembly:
                raise ValueError(f"alteration {alt.alteration_id} assembly {alt.position.assembly} differs from case assembly {self.assembly}")
        return self

    def tumor_specimens(self) -> list[Specimen]:
        return [s for s in self.specimens if s.role == SpecimenRole.TUMOR]

    def specimen(self, specimen_id: str) -> Specimen:
        for s in self.specimens:
            if s.specimen_id == specimen_id:
                return s
        raise KeyError(specimen_id)
