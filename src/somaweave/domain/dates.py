"""Partial-precision dates.

Clinical records often carry month- or year-precision dates. Fabricating a day
to satisfy a ``date`` field would be invention, so case fields accept either a
full ISO date or a partial ``YYYY-MM`` / ``YYYY`` string. ``PartialDate``
exposes the precision and the earliest/latest full dates the value can denote,
which is what chronology code needs to compute bounded intervals.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal, Union

from pydantic import AfterValidator

PARTIAL_RE = re.compile(r"^(\d{4})(?:-(0[1-9]|1[0-2]))?$")


def _check_partial(value: str) -> str:
    if not PARTIAL_RE.match(value):
        raise ValueError("partial date must be YYYY or YYYY-MM (full dates are parsed as dates)")
    return value


PartialDateStr = Annotated[str, AfterValidator(_check_partial)]
# Field type for clinical dates: a full ISO date, or a YYYY / YYYY-MM string.
FlexibleDate = Union[date, PartialDateStr]

Precision = Literal["day", "month", "year"]


@dataclass(frozen=True)
class PartialDate:
    year: int
    month: int | None = None
    day: int | None = None

    @property
    def precision(self) -> Precision:
        if self.day is not None:
            return "day"
        if self.month is not None:
            return "month"
        return "year"

    @property
    def earliest(self) -> date:
        return date(self.year, self.month or 1, self.day or 1)

    @property
    def latest(self) -> date:
        if self.day is not None:
            return date(self.year, self.month, self.day)
        if self.month is not None:
            return date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])
        return date(self.year, 12, 31)

    def isoformat(self) -> str:
        if self.day is not None:
            return self.earliest.isoformat()
        if self.month is not None:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"

    @classmethod
    def parse(cls, value: FlexibleDate | None) -> "PartialDate | None":
        if value is None:
            return None
        if isinstance(value, date):
            return cls(value.year, value.month, value.day)
        m = PARTIAL_RE.match(value)
        if not m:
            raise ValueError(f"not a partial date: {value!r}")
        return cls(int(m.group(1)), int(m.group(2)) if m.group(2) else None, None)


def certainly_before(a: FlexibleDate | None, b: FlexibleDate | None) -> bool | None:
    """True if every date ``a`` could denote precedes every date ``b`` could
    denote; False if ``a`` certainly follows ``b``; None when undecidable or
    either is missing. Used to flag ordering errors without inventing days."""
    pa, pb = PartialDate.parse(a), PartialDate.parse(b)
    if pa is None or pb is None:
        return None
    if pa.latest < pb.earliest:
        return True
    if pa.earliest > pb.latest:
        return False
    return None
