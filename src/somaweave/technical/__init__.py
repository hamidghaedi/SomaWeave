"""Deterministic technical assessment of detected alterations.

Pure functions, no network, no LLM input. Every value derived here (observed
VAF, confidence intervals, expected VAF under explicit scenarios, QC flags,
treatment chronology) is reported alongside the raw measurement it came from.

Scientific ground rules enforced by this package:

- VAF is computed from raw counts only; a caller-reported VAF is exposed
  separately and never substituted for counts.
- Clonality and LOH are never inferred from VAF alone. Expected-VAF analysis
  returns the set of *compatible* purity/copy-number/multiplicity scenarios,
  not a call.
- Missing metrics are reported as "not evaluated", never as a pass.
"""

from somaweave.technical.allele_fractions import (
    NormalSupportSummary,
    ObservedVaf,
    clopper_pearson_interval,
    normal_alt_summary,
    observed_vaf,
    wilson_interval,
)
from somaweave.technical.assess import (
    LEVEL_RULES,
    MeasurementAssessment,
    assess_alteration,
    assess_measurement,
    technical_summary,
)
from somaweave.technical.chronology import TreatmentExposure, specimen_chronology, treatment_exposure
from somaweave.technical.depth_quality import DepthQualityResult, QualityThresholds, depth_quality_flags
from somaweave.technical.expected_vaf import (
    SCENARIO_DISCLAIMER,
    PurityScenarioSet,
    Scenario,
    ScenarioAnalysis,
    compare_scenarios,
    enumerate_scenarios,
    evaluate_scenarios,
    expected_vaf,
)
from somaweave.technical.ffpe import (
    FfpeAssessment,
    FfpeThresholds,
    StrandImbalance,
    binomial_two_sided_p,
    ffpe_assessment,
    strand_imbalance,
    substitution_class,
)

__all__ = [name for name in dir() if not name.startswith("_")]
