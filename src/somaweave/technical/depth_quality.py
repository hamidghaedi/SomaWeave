"""Depth, support and base/mapping quality thresholds.

Thresholds are a frozen dataclass so a run can override them explicitly and
record the values used. A metric that is not reported is listed under
``not_evaluated``; it is never treated as a pass.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import ReadSupport
from somaweave.technical.allele_fractions import normal_alt_summary, observed_vaf


@dataclass(frozen=True)
class QualityThresholds:
    """Minimum acceptable values; defaults are conservative research settings."""

    min_tumor_depth_wgs: int = 30
    min_tumor_depth_other: int = 30
    min_alt_reads: int = 5
    min_unique_templates: int = 3
    min_mapq: float = 40.0
    min_alt_baseq: float = 25.0
    min_normal_depth: int = 20
    max_normal_alt: int = 1
    max_normal_vaf: float = 0.02

    def as_dict(self) -> dict:
        return asdict(self)


class DepthQualityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flags: list[str] = Field(default_factory=list)
    not_evaluated: list[str] = Field(default_factory=list, description="Metrics missing from the input.")
    details: dict[str, Optional[float]] = Field(default_factory=dict)
    thresholds: dict = Field(default_factory=dict)


def _is_wgs(assay: Optional[str]) -> bool:
    return assay is not None and assay.strip().upper() == "WGS"


def depth_quality_flags(tumor: Optional[ReadSupport], normal: Optional[ReadSupport],
                        sequencing_assay: Optional[str] = None,
                        thresholds: QualityThresholds = QualityThresholds()) -> DepthQualityResult:
    """Produce named depth/quality flags for one tumour (and optional normal) measurement.

    Flags: ``low_tumor_depth``, ``low_alt_reads``, ``low_unique_templates``,
    ``low_mapq``, ``low_alt_baseq``, ``low_normal_depth``,
    ``normal_alt_support`` (normal ALT exceeds both the count and VAF limits),
    ``no_matched_normal``, ``no_tumor_counts``.
    """
    flags: list[str] = []
    missing: list[str] = []
    details: dict[str, Optional[float]] = {}
    min_depth = thresholds.min_tumor_depth_wgs if _is_wgs(sequencing_assay) else thresholds.min_tumor_depth_other

    if tumor is None:
        flags.append("no_tumor_counts")
    else:
        obs = observed_vaf(tumor)
        details["tumor_depth"] = obs.denominator
        details["tumor_alt_count"] = tumor.alt_count
        details["tumor_vaf"] = obs.vaf
        if obs.denominator is None:
            missing.append("tumor_depth")
            if tumor.alt_count is None:
                flags.append("no_tumor_counts")
        elif obs.denominator < min_depth:
            flags.append("low_tumor_depth")
        if tumor.alt_count is None:
            missing.append("tumor_alt_count")
        elif tumor.alt_count < thresholds.min_alt_reads:
            flags.append("low_alt_reads")
        details["unique_templates_alt"] = tumor.unique_templates_alt
        if tumor.unique_templates_alt is None:
            missing.append("unique_templates_alt")
        elif tumor.unique_templates_alt < thresholds.min_unique_templates:
            flags.append("low_unique_templates")
        details["mean_mapq"] = tumor.mean_mapq
        if tumor.mean_mapq is None:
            missing.append("mean_mapq")
        elif tumor.mean_mapq < thresholds.min_mapq:
            flags.append("low_mapq")
        details["mean_baseq_alt"] = tumor.mean_baseq_alt
        if tumor.mean_baseq_alt is None:
            missing.append("mean_baseq_alt")
        elif tumor.mean_baseq_alt < thresholds.min_alt_baseq:
            flags.append("low_alt_baseq")

    norm = normal_alt_summary(normal)
    if not norm.available:
        flags.append("no_matched_normal")
    else:
        details["normal_depth"] = norm.denominator
        details["normal_alt_count"] = norm.alt_count
        details["normal_vaf"] = norm.vaf
        if norm.denominator is None:
            missing.append("normal_depth")
        elif norm.denominator < thresholds.min_normal_depth:
            flags.append("low_normal_depth")
        if norm.alt_count is None:
            missing.append("normal_alt_count")
        else:
            count_ok = norm.alt_count <= thresholds.max_normal_alt
            vaf_ok = norm.vaf is not None and norm.vaf <= thresholds.max_normal_vaf
            if not (count_ok or vaf_ok):
                flags.append("normal_alt_support")
    return DepthQualityResult(flags=flags, not_evaluated=missing, details=details, thresholds=thresholds.as_dict())
