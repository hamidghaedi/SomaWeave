"""Analytical-reliability assessment combining the technical modules.

Level rules (applied in order, first match wins), documented in ``LEVEL_RULES``:

1. ``not_assessable`` - no tumour ALT count or no usable denominator.
2. ``unreliable`` - matched normal shows ALT support above both limits
   (``normal_alt_support``) or tumour ALT count < ``UNRELIABLE_MIN_ALT`` (3).
3. ``low`` - any major flag: low_tumor_depth, low_alt_reads,
   low_unique_templates, low_mapq, low_alt_baseq, strand_imbalance,
   ffpe_c_to_t_context.
4. ``moderate`` - any minor flag: low_normal_depth, no_matched_normal,
   caller_filter_not_pass, upstream_qc_flag, or a key metric not reported
   (``*_not_reported``).
5. ``high`` - otherwise.

The level is about analytical reliability only. It says nothing about
oncogenicity, actionability or clonality.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave import __version__
from somaweave.domain import (
    Alteration,
    AlterationMeasurement,
    AnalyticalReliability,
    Case,
    Specimen,
    SpecimenRole,
)
from somaweave.technical.allele_fractions import NormalSupportSummary, ObservedVaf, normal_alt_summary, observed_vaf
from somaweave.technical.chronology import TreatmentExposure, specimen_chronology
from somaweave.technical.depth_quality import DepthQualityResult, QualityThresholds, depth_quality_flags
from somaweave.technical.expected_vaf import SCENARIO_DISCLAIMER, ScenarioAnalysis, evaluate_scenarios
from somaweave.technical.ffpe import FfpeAssessment, FfpeThresholds, ffpe_assessment

UNRELIABLE_MIN_ALT = 3
MAJOR_FLAGS = frozenset({
    "low_tumor_depth", "low_alt_reads", "low_unique_templates", "low_mapq", "low_alt_baseq",
    "strand_imbalance", "ffpe_c_to_t_context",
})
MINOR_FLAGS = frozenset({"low_normal_depth", "no_matched_normal", "caller_filter_not_pass", "upstream_qc_flag"})
PASS_FILTERS = frozenset({"PASS", "."})

LEVEL_RULES: dict[str, str] = {
    "not_assessable": "no tumour ALT count or no usable depth denominator",
    "unreliable": f"normal_alt_support flag, or tumour ALT count < {UNRELIABLE_MIN_ALT}",
    "low": "any major flag: " + ", ".join(sorted(MAJOR_FLAGS)),
    "moderate": "any minor flag: " + ", ".join(sorted(MINOR_FLAGS)) + ", or any *_not_reported flag",
    "high": "no flags",
}


class MeasurementAssessment(BaseModel):
    """Everything computed for one alteration in one tumour specimen."""

    model_config = ConfigDict(extra="forbid")

    alteration_id: str
    specimen_id: str
    observed: ObservedVaf
    normal: NormalSupportSummary
    depth_quality: DepthQualityResult
    ffpe: FfpeAssessment
    scenarios: ScenarioAnalysis
    reliability: AnalyticalReliability
    caller: Optional[str] = None
    caller_filters: list[str] = Field(default_factory=list)
    upstream_qc_flags: list[str] = Field(default_factory=list)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _level(flags: list[str], observed: ObservedVaf) -> tuple[str, str]:
    if observed.vaf is None or observed.alt_count is None:
        return "not_assessable", LEVEL_RULES["not_assessable"]
    if "normal_alt_support" in flags or observed.alt_count < UNRELIABLE_MIN_ALT:
        return "unreliable", LEVEL_RULES["unreliable"]
    if any(f in MAJOR_FLAGS for f in flags):
        return "low", LEVEL_RULES["low"]
    if any(f in MINOR_FLAGS or f.endswith("_not_reported") for f in flags):
        return "moderate", LEVEL_RULES["moderate"]
    return "high", LEVEL_RULES["high"]


def assess_measurement(case: Case, alteration: Alteration, measurement: AlterationMeasurement,
                       quality: QualityThresholds = QualityThresholds(),
                       ffpe: FfpeThresholds = FfpeThresholds()) -> MeasurementAssessment:
    """Assess one measurement of one alteration; pure and deterministic."""
    specimen: Specimen = case.specimen(measurement.specimen_id)
    obs = observed_vaf(measurement.tumor)
    norm = normal_alt_summary(measurement.normal)
    dq = depth_quality_flags(measurement.tumor, measurement.normal, specimen.sequencing_assay, quality)
    fa = ffpe_assessment(alteration, measurement.tumor, specimen.preservation, ffpe, quality)
    scen = evaluate_scenarios(specimen, measurement, obs)

    flags = list(dq.flags) + list(fa.flags)
    flags += [f"{m}_not_reported" for m in dq.not_evaluated + fa.not_evaluated]
    if any(f not in PASS_FILTERS for f in measurement.caller_filters):
        flags.append("caller_filter_not_pass")
    if measurement.qc_flags:
        flags.append("upstream_qc_flag")
    flags = _dedupe(flags)

    level, rule = _level(flags, obs)
    rationale: list[str] = [f"level rule: {rule}"]
    if obs.vaf is not None:
        rationale.append(f"observed VAF {obs.vaf:.4f} ({obs.alt_count}/{obs.denominator}, {obs.denominator_source}); "
                         f"95% {obs.ci_method} CI [{obs.ci_lower:.4f}, {obs.ci_upper:.4f}]")
    else:
        rationale.append("observed VAF not computable from counts; caller-reported VAF, if any, was not substituted")
    if norm.available and norm.alt_count is not None:
        rationale.append(f"matched normal ALT {norm.alt_count}/{norm.denominator}")
    rationale.extend(fa.rationale)
    if dq.not_evaluated or fa.not_evaluated:
        rationale.append("metrics not reported: " + ", ".join(dq.not_evaluated + fa.not_evaluated))
    if measurement.qc_flags:
        rationale.append("upstream QC flags: " + ", ".join(measurement.qc_flags))
    rationale.append(SCENARIO_DISCLAIMER)

    reliability = AnalyticalReliability(level=level, flags=flags, rationale=rationale, specimen_id=measurement.specimen_id)
    return MeasurementAssessment(
        alteration_id=alteration.alteration_id, specimen_id=measurement.specimen_id, observed=obs, normal=norm,
        depth_quality=dq, ffpe=fa, scenarios=scen, reliability=reliability, caller=measurement.caller,
        caller_filters=list(measurement.caller_filters), upstream_qc_flags=list(measurement.qc_flags),
    )


def _tumor_measurements(case: Case, alteration: Alteration) -> list[AlterationMeasurement]:
    return [m for m in alteration.measurements if case.specimen(m.specimen_id).role == SpecimenRole.TUMOR]


def assess_alteration(case: Case, alteration: Alteration,
                      quality: QualityThresholds = QualityThresholds(),
                      ffpe: FfpeThresholds = FfpeThresholds()) -> list[AnalyticalReliability]:
    """One ``AnalyticalReliability`` per tumour-specimen measurement of the alteration."""
    return [assess_measurement(case, alteration, m, quality, ffpe).reliability for m in _tumor_measurements(case, alteration)]


def technical_summary(case: Case, quality: QualityThresholds = QualityThresholds(),
                      ffpe: FfpeThresholds = FfpeThresholds()) -> dict[str, Any]:
    """JSON-ready technical report for a case: VAFs, intervals, scenarios, flags, chronology."""
    alterations = []
    for alt in case.alterations:
        assessments = [assess_measurement(case, alt, m, quality, ffpe) for m in _tumor_measurements(case, alt)]
        alterations.append({
            "alteration_id": alt.alteration_id,
            "gene_symbol": alt.gene_symbol,
            "hgvs_p": alt.hgvs_p,
            "alteration_type": alt.alteration_type.value,
            "measurements": [a.model_dump(mode="json") for a in assessments],
        })
    chronology: dict[str, list[dict[str, Any]]] = {}
    for spec in case.tumor_specimens():
        exposures: list[TreatmentExposure] = specimen_chronology(case, spec.specimen_id)
        chronology[spec.specimen_id] = [e.model_dump(mode="json") for e in exposures]
    return {
        "report": "technical_summary",
        "somaweave_version": __version__,
        "case_id": case.case_id,
        "level_rules": dict(LEVEL_RULES),
        "quality_thresholds": quality.as_dict(),
        "ffpe_thresholds": ffpe.as_dict(),
        "scenario_disclaimer": SCENARIO_DISCLAIMER,
        "alterations": alterations,
        "treatment_chronology": chronology,
    }
