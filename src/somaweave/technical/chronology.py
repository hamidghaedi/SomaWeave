"""Treatment and clinical-event exposure relative to specimen collection.

Dates are taken as recorded and may be partial (``YYYY-MM`` or ``YYYY``). A
relation is asserted only when it holds for every full date the recorded
values could denote; otherwise it is ``overlapping_or_undetermined`` (dates
present but the precision does not decide the order) or ``unknown_dates``
(a needed date is absent). Day differences are reported as exact integers when
both dates have day precision and as ``[min, max]`` ranges otherwise; nothing
is imputed.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import Case, TreatmentEvent
from somaweave.domain.dates import FlexibleDate, PartialDate

ExposureRelation = Literal["before_specimen", "ongoing_at_collection", "after_specimen", "overlapping_or_undetermined", "unknown_dates"]
EventRelation = Literal["before_specimen", "after_specimen", "same_period_or_undetermined", "unknown_dates"]


class TreatmentExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    treatment_id: str
    name: str
    agents: list[str] = Field(default_factory=list)
    relation: ExposureRelation
    days_start_to_collection: Optional[int] = Field(default=None, description="collection - start in days when both have day precision.")
    days_end_to_collection: Optional[int] = Field(default=None, description="collection - end in days when both have day precision.")
    days_start_to_collection_range: Optional[tuple[int, int]] = Field(default=None, description="[min, max] days at the recorded precision.")
    days_end_to_collection_range: Optional[tuple[int, int]] = Field(default=None)
    precision: Optional[str] = Field(default=None, description="Coarsest precision among the dates used (day/month/year).")
    note: Optional[str] = None


class EventTiming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    event_date: Optional[str] = None
    relation: EventRelation
    days_to_collection_range: Optional[tuple[int, int]] = None
    note: Optional[str] = None


def _days_range(later: PartialDate, earlier: PartialDate) -> tuple[Optional[int], tuple[int, int]]:
    """Days from ``earlier`` to ``later`` as (exact or None, [min, max])."""
    lo = (later.earliest - earlier.latest).days
    hi = (later.latest - earlier.earliest).days
    exact = lo if lo == hi else None
    return exact, (lo, hi)


def _coarsest(*parts: Optional[PartialDate]) -> Optional[str]:
    order = {"day": 0, "month": 1, "year": 2}
    present = [p.precision for p in parts if p is not None]
    return max(present, key=order.__getitem__) if present else None


def treatment_exposure(treatment: TreatmentEvent, collection_date: Optional[FlexibleDate]) -> TreatmentExposure:
    """Classify one treatment relative to a collection date without guessing missing dates or days."""
    coll = PartialDate.parse(collection_date)
    start = PartialDate.parse(treatment.start_date)
    end = PartialDate.parse(treatment.end_date)
    base: dict = {"treatment_id": treatment.treatment_id, "name": treatment.name, "agents": list(treatment.agents),
                  "precision": _coarsest(coll, start, end)}
    if coll is None:
        return TreatmentExposure(**base, relation="unknown_dates", note="specimen collection_date missing")
    if start is not None:
        base["days_start_to_collection"], base["days_start_to_collection_range"] = _days_range(coll, start)
    if end is not None:
        base["days_end_to_collection"], base["days_end_to_collection_range"] = _days_range(coll, end)
    if start is None and end is None:
        return TreatmentExposure(**base, relation="unknown_dates", note="treatment start_date and end_date missing")
    if start is not None and start.earliest > coll.latest:
        return TreatmentExposure(**base, relation="after_specimen")
    if end is not None and end.latest < coll.earliest:
        note = "start_date missing; relation based on end_date only" if start is None else None
        return TreatmentExposure(**base, relation="before_specimen", note=note)
    if start is None:
        return TreatmentExposure(**base, relation="unknown_dates", note="start_date missing and end_date is not certainly before collection")
    start_certainly_before = start.latest <= coll.earliest
    if end is not None:
        end_certainly_after = end.earliest >= coll.latest
        if start_certainly_before and end_certainly_after:
            return TreatmentExposure(**base, relation="ongoing_at_collection")
        return TreatmentExposure(**base, relation="overlapping_or_undetermined",
                                 note=f"recorded precision ({base['precision']}) does not decide whether exposure preceded, overlapped or followed collection")
    if treatment.ongoing is True:
        if start_certainly_before:
            return TreatmentExposure(**base, relation="ongoing_at_collection", note="end_date missing; treatment recorded as ongoing")
        return TreatmentExposure(**base, relation="overlapping_or_undetermined", note="treatment ongoing; start and collection fall in the same recorded period")
    return TreatmentExposure(**base, relation="unknown_dates", note="end_date missing and ongoing not stated")


def specimen_chronology(case: Case, specimen_id: str) -> list[TreatmentExposure]:
    """Exposure relation of every case treatment to the named specimen's collection date."""
    specimen = case.specimen(specimen_id)
    return [treatment_exposure(t, specimen.collection_date) for t in case.treatments]


def event_timing(case: Case, specimen_id: str) -> list[EventTiming]:
    """Clinical events (progression, metastasis, ...) relative to the specimen collection date."""
    coll = PartialDate.parse(case.specimen(specimen_id).collection_date)
    out: list[EventTiming] = []
    for ev in case.clinical_events:
        evd = PartialDate.parse(ev.event_date)
        base = {"event_type": ev.event_type.value, "event_date": evd.isoformat() if evd else None}
        if coll is None or evd is None:
            out.append(EventTiming(**base, relation="unknown_dates", note="event or collection date missing"))
            continue
        _, rng = _days_range(coll, evd)
        if evd.latest < coll.earliest:
            out.append(EventTiming(**base, relation="before_specimen", days_to_collection_range=rng))
        elif evd.earliest > coll.latest:
            out.append(EventTiming(**base, relation="after_specimen", days_to_collection_range=rng))
        else:
            out.append(EventTiming(**base, relation="same_period_or_undetermined", days_to_collection_range=rng,
                                   note=f"event and collection fall in the same recorded period ({_coarsest(coll, evd)} precision)"))
    return out
