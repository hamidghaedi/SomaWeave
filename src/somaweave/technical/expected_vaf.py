"""Expected VAF under explicit purity / copy-number / multiplicity scenarios.

For tumour purity ``p``, total tumour copy number ``CN`` at the locus, variant
multiplicity ``m`` (copies carrying the variant, 1..CN), normal copy number
``CN_n`` (2 for autosomes) and cancer-cell fraction ``ccf``::

    E[VAF] = p * m * ccf / (p * CN + (1 - p) * CN_n)

This module enumerates scenarios and reports which are *compatible* with the
observed VAF confidence interval. It does not call clonality, multiplicity or
LOH: several scenarios are usually compatible at once, and the same VAF can
arise from a clonal single-copy variant or a subclonal multi-copy one.
Pathology and molecular purity estimates are evaluated separately.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import AlterationMeasurement, Specimen
from somaweave.technical.allele_fractions import ObservedVaf

SCENARIO_DISCLAIMER = (
    "Scenarios are listed as compatible or incompatible with the observed VAF interval. "
    "Clonality, multiplicity and LOH are NOT inferred from VAF alone; a compatible scenario is "
    "not a call. Use caller-reported copy-number/LOH and purity fits as independent inputs."
)

DEFAULT_CCF_GRID: tuple[float, ...] = (1.0, 0.75, 0.5, 0.25)
PuritySource = Literal["pathology_min", "pathology_mid", "pathology_max", "molecular_fit", "alternative_fit", "user"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scenario(_Model):
    purity: float
    total_copy_number: int
    multiplicity: int
    cancer_cell_fraction: float
    expected_vaf: float
    compatible: Optional[bool] = Field(default=None, description="None when no observed interval was available.")


class PurityScenarioSet(_Model):
    purity_source: PuritySource
    purity: float
    scenarios: list[Scenario]
    compatible_count: Optional[int] = None
    fit_index: Optional[int] = Field(default=None, description="Zero-based index in the original alternative_fits list; never a rank.")
    fit_disposition: Optional[str] = None
    fit_ploidy: Optional[float] = None
    fit_score: Optional[float] = None
    fit_tool: Optional[str] = None


class ScenarioAnalysis(_Model):
    disclaimer: str = SCENARIO_DISCLAIMER
    observed_vaf: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    total_copy_number_used: Optional[int] = None
    total_copy_number_reported: Optional[float] = Field(default=None, description="Caller value before any integer rounding.")
    alternative_copy_numbers_evaluated: list[int] = Field(default_factory=list, description="Floor/ceil values also evaluated when the caller CN is non-integer.")
    copy_number_source: Literal["caller", "assumed_diploid", "none"] = "none"
    caller_reported_loh: Optional[bool] = Field(default=None, description="Passed through from the CNA caller; never derived here.")
    loh_call: Optional[Literal['loh', 'no_loh', 'not_called']] = None
    loh_source: Optional[str] = None
    purity_evaluations: list[PurityScenarioSet] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def expected_vaf(purity: float, total_copy_number: float, multiplicity: float,
                 normal_copy_number: float = 2.0, cancer_cell_fraction: float = 1.0) -> float:
    """Expected VAF for one explicit scenario.

    Raises ``ValueError`` on arguments outside their physical ranges or when
    the mixture denominator is zero.
    """
    if not 0.0 <= purity <= 1.0:
        raise ValueError("purity must be in [0, 1]")
    if total_copy_number < 0 or normal_copy_number < 0:
        raise ValueError("copy numbers must be non-negative")
    if multiplicity < 0 or multiplicity > total_copy_number:
        raise ValueError("multiplicity must be in [0, total_copy_number]")
    if not 0.0 <= cancer_cell_fraction <= 1.0:
        raise ValueError("cancer_cell_fraction must be in [0, 1]")
    denom = purity * total_copy_number + (1.0 - purity) * normal_copy_number
    if denom <= 0.0:
        raise ValueError("mixture denominator is zero (no DNA at locus)")
    return purity * multiplicity * cancer_cell_fraction / denom


def enumerate_scenarios(purity: float, total_copy_number: int, normal_copy_number: float = 2.0,
                        ccf_grid: tuple[float, ...] = DEFAULT_CCF_GRID) -> list[Scenario]:
    """Scenarios for multiplicity 1..CN crossed with a cancer-cell-fraction grid.

    ``ccf = 1.0`` rows are the clonal scenarios; the remaining grid values are
    subclonal. Deterministic ordering: multiplicity ascending, then ccf
    descending as given in ``ccf_grid``.
    """
    if total_copy_number < 1:
        return []
    out: list[Scenario] = []
    for m in range(1, int(total_copy_number) + 1):
        for ccf in ccf_grid:
            out.append(Scenario(
                purity=purity, total_copy_number=int(total_copy_number), multiplicity=m,
                cancer_cell_fraction=ccf,
                expected_vaf=expected_vaf(purity, total_copy_number, m, normal_copy_number, ccf),
            ))
    return out


def compare_scenarios(scenarios: list[Scenario], ci_lower: Optional[float], ci_upper: Optional[float]) -> list[Scenario]:
    """Mark each scenario compatible when its expected VAF lies inside [ci_lower, ci_upper]."""
    if ci_lower is None or ci_upper is None:
        return [s.model_copy(update={"compatible": None}) for s in scenarios]
    return [s.model_copy(update={"compatible": ci_lower <= s.expected_vaf <= ci_upper}) for s in scenarios]


def _purity_candidates(specimen: Specimen) -> list[tuple[PuritySource, float]]:
    out: list[tuple[PuritySource, float]] = []
    if specimen.purity is None:
        return out
    pe = specimen.purity
    if pe.pathology_min is not None:
        out.append(("pathology_min", pe.pathology_min))
    if pe.pathology_max is not None and pe.pathology_min is not None and pe.pathology_max != pe.pathology_min:
        out.append(("pathology_mid", round((pe.pathology_min + pe.pathology_max) / 2.0, 4)))
    if pe.pathology_max is not None and pe.pathology_max != pe.pathology_min:
        out.append(("pathology_max", pe.pathology_max))
    if pe.molecular_fit is not None:
        out.append(("molecular_fit", pe.molecular_fit))
    return out


def evaluate_scenarios(specimen: Specimen, measurement: AlterationMeasurement, observed: ObservedVaf,
                       normal_copy_number: float = 2.0, ccf_grid: tuple[float, ...] = DEFAULT_CCF_GRID,
                       assume_diploid_when_missing: bool = True) -> ScenarioAnalysis:
    """Evaluate all purity estimates of the specimen against the observed VAF interval.

    Copy number comes from the caller (rounded to the nearest integer for
    multiplicity enumeration). When absent and ``assume_diploid_when_missing``
    is set, CN=2 is used and labelled ``assumed_diploid``.
    """
    analysis = ScenarioAnalysis(observed_vaf=observed.vaf, ci_lower=observed.ci_lower, ci_upper=observed.ci_upper)
    notes: list[str] = []
    cn_state = measurement.copy_number
    if cn_state is not None:
        call = cn_state.loh_call
        if call is None and cn_state.caller_reported_loh is not None:
            call = 'loh' if cn_state.caller_reported_loh else 'no_loh'
        analysis = analysis.model_copy(update={'loh_call': call, 'loh_source': cn_state.loh_source or cn_state.source_tool,
                                                'caller_reported_loh': cn_state.caller_reported_loh})
        if cn_state.loh_call is not None and cn_state.caller_reported_loh is not None:
            notes.append('Explicit loh_call takes precedence; deprecated caller_reported_loh is retained as originally reported.')
    cn: Optional[int] = None
    alt_cns: list[int] = []
    if cn_state is not None and cn_state.total_copy_number is not None:
        reported = cn_state.total_copy_number
        cn = max(0, int(round(reported)))
        analysis = analysis.model_copy(update={"copy_number_source": "caller", "caller_reported_loh": cn_state.caller_reported_loh,
                                               "total_copy_number_reported": reported})
        if abs(reported - cn) > 1e-9:
            import math
            alt_cns = sorted({max(1, math.floor(reported)), max(1, math.ceil(reported))} - {cn})
            notes.append(f"caller total copy number {reported} is non-integer: multiplicity enumerated at CN={cn} (nearest) and also at "
                         f"CN={', '.join(str(a) for a in alt_cns)} (labelled alternative_cn)")
    elif assume_diploid_when_missing:
        cn = 2
        analysis = analysis.model_copy(update={"copy_number_source": "assumed_diploid"})
        notes.append("no caller copy number at locus; scenarios assume total CN=2 (labelled assumption, not a measurement)")
    if cn is None or cn == 0:
        notes.append("no usable copy number; scenarios not enumerated")
        return analysis.model_copy(update={"notes": notes})
    if observed.ci_lower is None:
        notes.append("no observed VAF interval; scenarios enumerated but compatibility not evaluated")
    purities = _purity_candidates(specimen)
    alternatives = specimen.purity.alternative_fits if specimen.purity else []
    if not purities and not alternatives:
        notes.append("no purity estimate on specimen; scenarios not enumerated")
    evaluations: list[PurityScenarioSet] = []
    for source, p in purities:
        scen = compare_scenarios(enumerate_scenarios(p, cn, normal_copy_number, ccf_grid), observed.ci_lower, observed.ci_upper)
        for a in alt_cns:
            scen += compare_scenarios(enumerate_scenarios(p, a, normal_copy_number, ccf_grid), observed.ci_lower, observed.ci_upper)
        count = None if observed.ci_lower is None else sum(1 for s in scen if s.compatible)
        evaluations.append(PurityScenarioSet(purity_source=source, purity=p, scenarios=scen, compatible_count=count))
    for index, fit in enumerate(alternatives):
        scen = []
        for candidate_cn in [cn] + alt_cns:
            scen += compare_scenarios(enumerate_scenarios(fit.purity, candidate_cn, normal_copy_number, ccf_grid), observed.ci_lower, observed.ci_upper)
        count = None if observed.ci_lower is None else sum(bool(s.compatible) for s in scen)
        evaluations.append(PurityScenarioSet(purity_source='alternative_fit', purity=fit.purity, scenarios=scen,
            compatible_count=count, fit_index=index, fit_disposition=fit.disposition, fit_ploidy=fit.ploidy, fit_score=fit.score, fit_tool=fit.tool))
    if alternatives:
        notes.append('Every alternative fit is enumerated in source order without selection or ranking. Locus copy number is the supplied caller value; it is not re-estimated for alternate ploidy fits.')
    if specimen.purity is not None and specimen.purity.fit_ambiguous:
        notes.append("molecular purity fit flagged ambiguous by the tool: molecular_fit scenarios are one of several competing models and "
                     "must not be preferred over the pathology range")
    return analysis.model_copy(update={"total_copy_number_used": cn, "alternative_copy_numbers_evaluated": alt_cns,
                                       "purity_evaluations": evaluations, "notes": notes})
