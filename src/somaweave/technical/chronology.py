"""Treatment exposure relative to specimen collection.

Dates are taken as recorded. When a date needed for a relation is absent the
relation is ``unknown_dates`` with an explanatory note; nothing is imputed.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import Case, TreatmentEvent

ExposureRelation = Literal["before_specimen", "ongoing_at_collection", "after_specimen", "unknown_dates"]


class TreatmentExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    treatment_id: str
    name: str
    agents: list[str] = Field(default_factory=list)
    relation: ExposureRelation
    days_start_to_collection: Optional[int] = Field(default=None, description="collection_date - start_date in days (negative if start is after collection).")
    days_end_to_collection: Optional[int] = Field(default=None, description="collection_date - end_date in days (negative if end is after collection).")
    note: Optional[str] = None


def treatment_exposure(treatment: TreatmentEvent, collection_date: Optional[date]) -> TreatmentExposure:
    """Classify one treatment relative to a collection date without guessing missing dates."""
    start, end = treatment.start_date, treatment.end_date
    base = {"treatment_id": treatment.treatment_id, "name": treatment.name, "agents": list(treatment.agents)}
    if collection_date is None:
        return TreatmentExposure(**base, relation="unknown_dates", note="specimen collection_date missing")
    d_start = (collection_date - start).days if start else None
    d_end = (collection_date - end).days if end else None
    base.update({"days_start_to_collection": d_start, "days_end_to_collection": d_end})

    if start is None and end is None:
        return TreatmentExposure(**base, relation="unknown_dates", note="treatment start_date and end_date missing")
    if start is not None and start > collection_date:
        return TreatmentExposure(**base, relation="after_specimen")
    if end is not None and end < collection_date:
        if start is None:
            return TreatmentExposure(**base, relation="before_specimen", note="start_date missing; relation based on end_date only")
        return TreatmentExposure(**base, relation="before_specimen")
    # From here: (start is None or start <= collection) and (end is None or end >= collection)
    if start is None:
        return TreatmentExposure(**base, relation="unknown_dates", note="start_date missing and end_date is on/after collection; cannot tell whether exposure preceded the specimen")
    if end is not None:
        return TreatmentExposure(**base, relation="ongoing_at_collection")
    if treatment.ongoing is True:
        return TreatmentExposure(**base, relation="ongoing_at_collection", note="end_date missing; treatment recorded as ongoing")
    return TreatmentExposure(**base, relation="unknown_dates", note="start_date precedes collection but end_date missing and ongoing not stated")


def specimen_chronology(case: Case, specimen_id: str) -> list[TreatmentExposure]:
    """Exposure relation of every case treatment to the named specimen's collection date."""
    specimen = case.specimen(specimen_id)
    return [treatment_exposure(t, specimen.collection_date) for t in case.treatments]
