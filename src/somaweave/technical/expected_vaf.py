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
PuritySource = Literal["pathology_min", "pathology_max", "molecular_fit", "user"]


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


class ScenarioAnalysis(_Model):
    disclaimer: str = SCENARIO_DISCLAIMER
    observed_vaf: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    total_copy_number_used: Optional[int] = None
    copy_number_source: Literal["caller", "assumed_diploid", "none"] = "none"
    caller_reported_loh: Optional[bool] = Field(default=None, description="Passed through from the CNA caller; never derived here.")
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
    cn: Optional[int] = None
    if cn_state is not None and cn_state.total_copy_number is not None:
        cn = max(0, int(round(cn_state.total_copy_number)))
        analysis = analysis.model_copy(update={"copy_number_source": "caller", "caller_reported_loh": cn_state.caller_reported_loh})
        if abs(cn_state.total_copy_number - cn) > 1e-9:
            notes.append(f"caller total copy number {cn_state.total_copy_number} rounded to {cn} for multiplicity enumeration")
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
    if not purities:
        notes.append("no purity estimate on specimen; scenarios not enumerated")
    evaluations: list[PurityScenarioSet] = []
    for source, p in purities:
        scen = compare_scenarios(enumerate_scenarios(p, cn, normal_copy_number, ccf_grid), observed.ci_lower, observed.ci_upper)
        count = None if observed.ci_lower is None else sum(1 for s in scen if s.compatible)
        evaluations.append(PurityScenarioSet(purity_source=source, purity=p, scenarios=scen, compatible_count=count))
    if specimen.purity is not None and specimen.purity.fit_ambiguous:
        notes.append("molecular purity fit flagged ambiguous by the tool")
    return analysis.model_copy(update={"total_copy_number_used": cn, "purity_evaluations": evaluations, "notes": notes})
