"""Partial-date handling.

Clinical records frequently carry dates with reduced precision (``2024-03``,
``2024``). A ``PartialDate`` stores only the components that were given and
labels the precision; day or month are never invented. Intervals between
partial dates are reported as a range of possible day counts.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

DatePrecision = Literal["day", "month", "year"]

_ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_ISO_YEAR = re.compile(r"^(\d{4})$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PartialDate(_Model):
    original: str = Field(description="Input exactly as supplied (ISO text for date objects).")
    year: int = Field(ge=1, le=9999)
    month: Optional[int] = Field(default=None, ge=1, le=12)
    day: Optional[int] = Field(default=None, ge=1, le=31)
    precision: DatePrecision

    def earliest(self) -> date:
        """Earliest calendar day consistent with the stated components."""
        return date(self.year, self.month or 1, self.day or 1)

    def latest(self) -> date:
        """Latest calendar day consistent with the stated components."""
        month = self.month or 12
        day = self.day or calendar.monthrange(self.year, month)[1]
        return date(self.year, month, day)

    def iso(self) -> str:
        if self.precision == "day":
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        if self.precision == "month":
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"


class DayInterval(_Model):
    """Number of days from ``start`` to ``end`` as a range.

    ``days_min``/``days_max`` bound the true value given the precision of the
    inputs; ``days_exact`` is set only when both inputs have day precision.
    Negative values mean ``end`` may precede ``start``.
    """

    days_min: int
    days_max: int
    days_exact: Optional[int] = None
    precision: DatePrecision = Field(description="Coarsest precision among the two inputs.")


def parse_partial_date(value: Union[str, date, None]) -> tuple[Optional[PartialDate], Optional[str]]:
    """Parse ISO ``YYYY-MM-DD``, ``YYYY-MM`` or ``YYYY`` text, or a ``date``.

    Returns ``(None, reason)`` for missing or unrecognised input. Other
    formats (``03/12/2024``, ``12 Mar 2024``) are rejected rather than
    guessed because day/month order is ambiguous.
    """
    if value is None:
        return None, "no date supplied"
    if isinstance(value, date):
        return PartialDate(original=value.isoformat(), year=value.year, month=value.month, day=value.day, precision="day"), None
    s = value.strip()
    if not s:
        return None, "empty string"
    m = _ISO_DAY.match(s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            date(y, mo, d)
        except ValueError as exc:
            return None, f"invalid calendar date: {exc}"
        return PartialDate(original=s, year=y, month=mo, day=d, precision="day"), None
    m = _ISO_MONTH.match(s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if not 1 <= mo <= 12:
            return None, "month out of range"
        return PartialDate(original=s, year=y, month=mo, precision="month"), None
    m = _ISO_YEAR.match(s)
    if m:
        return PartialDate(original=s, year=int(m.group(1)), precision="year"), None
    return None, "unrecognised date format (expected YYYY-MM-DD, YYYY-MM or YYYY)"


_ORDER = {"day": 0, "month": 1, "year": 2}


def days_between(start: PartialDate, end: PartialDate) -> DayInterval:
    """Days from ``start`` to ``end`` with precision-aware bounds.

    The minimum assumes the latest possible ``start`` and earliest possible
    ``end``; the maximum assumes the reverse.
    """
    days_min = (end.earliest() - start.latest()).days
    days_max = (end.latest() - start.earliest()).days
    exact = days_min if start.precision == "day" and end.precision == "day" else None
    coarsest = max(start.precision, end.precision, key=lambda p: _ORDER[p])
    return DayInterval(days_min=days_min, days_max=days_max, days_exact=exact, precision=coarsest)
