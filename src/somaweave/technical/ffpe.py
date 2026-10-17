"""FFPE-context and orientation-bias flags.

- Deamination context (``ffpe_c_to_t_context``): C>T or G>A substitution with
  low VAF and/or low independent template support, flagged only when the
  specimen preservation is FFPE.
- Strand imbalance (``strand_imbalance``): exact two-sided binomial test of
  alt_forward vs alt_reverse against 0.5, flagged when p < 0.05 and the ALT
  count is at least 6. Applies regardless of preservation.
- Low ALT base quality / low MAPQ are reported here as part of the FFPE
  context using the same thresholds as ``depth_quality`` (same flag names, so
  the assessment layer can deduplicate).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import Alteration, AlterationType, GenomicPosition, Preservation, ReadSupport
from somaweave.technical.allele_fractions import observed_vaf
from somaweave.technical.depth_quality import QualityThresholds

DEAMINATION_CLASSES = frozenset({"C>T", "G>A"})


@dataclass(frozen=True)
class FfpeThresholds:
    low_vaf: float = 0.10
    min_unique_templates: int = 3
    strand_p_value: float = 0.05
    strand_min_alt: int = 6

    def as_dict(self) -> dict:
        return asdict(self)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrandImbalance(_Model):
    alt_forward: Optional[int] = None
    alt_reverse: Optional[int] = None
    alt_total: Optional[int] = None
    p_value: Optional[float] = Field(default=None, description="Exact two-sided binomial p against 0.5.")
    evaluated: bool = False
    flagged: bool = False
    method: str = "exact_binomial_two_sided"
    source: str = Field(default="reads", description="'reads' (raw ALT read strands) or 'templates' (template-level strands; may be non-exclusive).")


class FfpeAssessment(_Model):
    preservation: Preservation
    substitution_class: Optional[str] = None
    is_deamination_class: bool = False
    deamination_context_flagged: bool = False
    strand: StrandImbalance
    low_alt_baseq: Optional[bool] = None
    low_mapq: Optional[bool] = None
    flags: list[str] = Field(default_factory=list)
    not_evaluated: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    thresholds: dict = Field(default_factory=dict)


def _log_pmf(k: int, n: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + n * math.log(0.5)


def binomial_two_sided_p(k: int, n: int) -> float:
    """Exact two-sided binomial test against p=0.5 (sum of outcomes at most as likely as ``k``)."""
    if n < 0 or k < 0 or k > n:
        raise ValueError("require 0 <= k <= n")
    if n == 0:
        return 1.0
    obs = _log_pmf(k, n)
    total = 0.0
    for i in range(n + 1):
        lp = _log_pmf(i, n)
        if lp <= obs + 1e-12:
            total += math.exp(lp)
    return min(1.0, total)


def strand_imbalance(support: Optional[ReadSupport], thresholds: FfpeThresholds = FfpeThresholds()) -> StrandImbalance:
    """Strand-orientation test on ALT reads; ``evaluated`` is False when counts are missing."""
    if support is None:
        return StrandImbalance()
    fwd, rev, source = support.alt_forward, support.alt_reverse, "reads"
    if fwd is None or rev is None:
        if support.alt_templates_forward is not None and support.alt_templates_reverse is not None:
            fwd, rev, source = support.alt_templates_forward, support.alt_templates_reverse, "templates"
        else:
            return StrandImbalance(alt_forward=support.alt_forward, alt_reverse=support.alt_reverse)
    total = fwd + rev
    if total == 0:
        return StrandImbalance(alt_forward=fwd, alt_reverse=rev, alt_total=0, evaluated=False, source=source)
    p = binomial_two_sided_p(fwd, total)
    flagged = total >= thresholds.strand_min_alt and p < thresholds.strand_p_value
    return StrandImbalance(alt_forward=fwd, alt_reverse=rev, alt_total=total, p_value=p, evaluated=True, flagged=flagged, source=source)


def substitution_class(position: Optional[GenomicPosition]) -> Optional[str]:
    """``REF>ALT`` for single-base substitutions, else None."""
    if position is None:
        return None
    ref, alt = position.reference.upper(), position.alternate.upper()
    if len(ref) == 1 and len(alt) == 1 and ref in "ACGT" and alt in "ACGT" and ref != alt:
        return f"{ref}>{alt}"
    return None


def ffpe_assessment(alteration: Alteration, tumor: Optional[ReadSupport], preservation: Preservation,
                    thresholds: FfpeThresholds = FfpeThresholds(),
                    quality: QualityThresholds = QualityThresholds()) -> FfpeAssessment:
    """Combine deamination-context, strand-imbalance and quality flags for one tumour measurement."""
    strand = strand_imbalance(tumor, thresholds)
    sub = substitution_class(alteration.position) if alteration.alteration_type == AlterationType.SNV else None
    is_deam = sub in DEAMINATION_CLASSES
    flags: list[str] = []
    missing: list[str] = []
    rationale: list[str] = []

    if not strand.evaluated:
        missing.append("strand_counts")
    elif strand.flagged:
        flags.append("strand_imbalance")
        unit = "ALT reads" if strand.source == "reads" else "ALT templates (template-level strand counts; may be non-exclusive)"
        rationale.append(f"{unit} {strand.alt_forward} forward vs {strand.alt_reverse} reverse (exact binomial p={strand.p_value:.4g})")
    elif strand.source == "templates":
        rationale.append("strand test used template-level strand counts (raw read strand counts not reported)")

    deam_flag = False
    if is_deam and preservation == Preservation.FFPE:
        obs = observed_vaf(tumor)
        low_vaf = obs.vaf is not None and obs.vaf < thresholds.low_vaf
        ut = None if tumor is None else tumor.unique_templates_alt
        low_templates = ut is not None and ut < thresholds.min_unique_templates
        if obs.vaf is None and ut is None:
            missing.append("deamination_context_inputs")
        if low_vaf or low_templates:
            deam_flag = True
            flags.append("ffpe_c_to_t_context")
            why = []
            if low_vaf:
                why.append(f"VAF {obs.vaf:.3f} < {thresholds.low_vaf}")
            if low_templates:
                why.append(f"{ut} independent ALT templates < {thresholds.min_unique_templates}")
            rationale.append(f"{sub} substitution in FFPE material with " + " and ".join(why) + "; compatible with cytosine deamination artefact")
        else:
            rationale.append(f"{sub} substitution in FFPE material; VAF and template support above deamination-context thresholds")
    elif is_deam:
        rationale.append(f"{sub} substitution; deamination context not flagged because preservation is {preservation.value}")

    low_bq = low_mq = None
    bq = None if tumor is None else (tumor.mean_baseq_alt if tumor.mean_baseq_alt is not None else tumor.median_baseq_alt)
    mq = None if tumor is None else (tumor.mean_mapq if tumor.mean_mapq is not None else tumor.median_mapq)
    if bq is not None:
        low_bq = bq < quality.min_alt_baseq
        if low_bq:
            flags.append("low_alt_baseq")
    if mq is not None:
        low_mq = mq < quality.min_mapq
        if low_mq:
            flags.append("low_mapq")

    return FfpeAssessment(
        preservation=preservation, substitution_class=sub, is_deamination_class=is_deam,
        deamination_context_flagged=deam_flag, strand=strand, low_alt_baseq=low_bq, low_mapq=low_mq,
        flags=flags, not_evaluated=missing, rationale=rationale, thresholds=thresholds.as_dict(),
    )
