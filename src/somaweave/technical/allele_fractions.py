"""Observed allele fractions from raw read counts.

The observed VAF is derived only from ``ReadSupport`` counts. When counts are
missing the VAF is ``None`` and ``vaf_source`` is ``"none"``; the caller-reported
VAF is carried separately in ``reported_vaf`` so that it is never silently
used in place of counts.
"""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import ReadSupport

Z_95 = 1.959963984540054  # two-sided 95% normal quantile

VafSource = Literal["raw_counts", "none"]
DenominatorSource = Literal["depth", "ref_plus_alt", "none"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ObservedVaf(_Model):
    """Observed VAF with its provenance and a 95% interval."""

    alt_count: Optional[int] = None
    denominator: Optional[int] = Field(default=None, description="Reads used as the VAF denominator.")
    denominator_source: DenominatorSource = "none"
    vaf: Optional[float] = Field(default=None, description="alt_count / denominator; None when counts are missing.")
    vaf_source: VafSource = "none"
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    ci_method: Optional[str] = None
    reported_vaf: Optional[float] = Field(default=None, description="Caller-reported VAF, carried as-is for comparison only.")
    reported_vs_observed_delta: Optional[float] = Field(default=None, description="reported_vaf - vaf when both exist.")


class NormalSupportSummary(_Model):
    """ALT support in the matched normal specimen."""

    available: bool
    alt_count: Optional[int] = None
    denominator: Optional[int] = None
    denominator_source: DenominatorSource = "none"
    vaf: Optional[float] = None
    vaf_source: VafSource = "none"
    reported_vaf: Optional[float] = None


def _denominator(support: ReadSupport) -> tuple[Optional[int], DenominatorSource]:
    if support.depth is not None and support.depth > 0:
        return support.depth, "depth"
    if support.ref_count is not None and support.alt_count is not None and (support.ref_count + support.alt_count) > 0:
        return support.ref_count + support.alt_count, "ref_plus_alt"
    return None, "none"


def wilson_interval(successes: int, trials: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Deterministic closed form; preferred over the Wald interval at low counts.
    Raises ``ValueError`` when ``trials`` is zero or counts are inconsistent.
    """
    if trials <= 0:
        raise ValueError("trials must be positive")
    if successes < 0 or successes > trials:
        raise ValueError("successes must lie in [0, trials]")
    p_hat = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    centre = (p_hat + z2 / (2.0 * trials)) / denom
    half = z * math.sqrt(p_hat * (1.0 - p_hat) / trials + z2 / (4.0 * trials * trials)) / denom
    lower = 0.0 if successes == 0 else max(0.0, centre - half)
    upper = 1.0 if successes == trials else min(1.0, centre + half)
    return lower, upper


def _log_binom_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p), computed in log space."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(math.exp(_log_binom_pmf(i, n, p)) for i in range(0, k + 1))


def clopper_pearson_interval(successes: int, trials: int, alpha: float = 0.05, tol: float = 1e-10) -> tuple[float, float]:
    """Exact (Clopper-Pearson) binomial interval via deterministic bisection.

    No scipy dependency. Bisection runs to a fixed tolerance so results are
    reproducible to ~1e-10 across platforms.
    """
    if trials <= 0:
        raise ValueError("trials must be positive")
    if successes < 0 or successes > trials:
        raise ValueError("successes must lie in [0, trials]")

    def _solve(target_fn, lo: float, hi: float) -> float:
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if target_fn(mid) > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol:
                break
        return 0.5 * (lo + hi)

    half = alpha / 2.0
    if successes == 0:
        lower = 0.0
    else:
        # lower bound: P(X >= k | p) = alpha/2  <=>  1 - CDF(k-1) - alpha/2 = 0; increasing in p
        lower = _solve(lambda p: half - (1.0 - binomial_cdf(successes - 1, trials, p)), 0.0, 1.0)
    if successes == trials:
        upper = 1.0
    else:
        # upper bound: P(X <= k | p) = alpha/2; decreasing in p
        upper = _solve(lambda p: binomial_cdf(successes, trials, p) - half, 0.0, 1.0)
    return lower, upper


def observed_vaf(support: Optional[ReadSupport], ci_method: str = "wilson") -> ObservedVaf:
    """Compute the observed VAF from raw counts.

    ``ci_method`` is ``"wilson"`` (default) or ``"clopper_pearson"``. The
    caller-reported VAF is passed through untouched; it never replaces counts.
    """
    if support is None:
        return ObservedVaf()
    result = ObservedVaf(reported_vaf=support.reported_vaf, alt_count=support.alt_count)
    if support.alt_count is None:
        return result
    denominator, source = _denominator(support)
    if denominator is None:
        return result
    vaf = support.alt_count / denominator
    if ci_method == "wilson":
        lo, hi = wilson_interval(support.alt_count, denominator)
    elif ci_method == "clopper_pearson":
        lo, hi = clopper_pearson_interval(support.alt_count, denominator)
    else:
        raise ValueError(f"unknown ci_method: {ci_method}")
    delta = None if support.reported_vaf is None else support.reported_vaf - vaf
    return result.model_copy(update={
        "denominator": denominator,
        "denominator_source": source,
        "vaf": vaf,
        "vaf_source": "raw_counts",
        "ci_lower": lo,
        "ci_upper": hi,
        "ci_method": ci_method,
        "reported_vs_observed_delta": delta,
    })


def normal_alt_summary(support: Optional[ReadSupport]) -> NormalSupportSummary:
    """Summarise ALT support in the matched normal; VAF only from counts."""
    if support is None:
        return NormalSupportSummary(available=False)
    denominator, source = _denominator(support)
    vaf = None
    vaf_source: VafSource = "none"
    if support.alt_count is not None and denominator is not None:
        vaf = support.alt_count / denominator
        vaf_source = "raw_counts"
    return NormalSupportSummary(
        available=True,
        alt_count=support.alt_count,
        denominator=denominator,
        denominator_source=source,
        vaf=vaf,
        vaf_source=vaf_source,
        reported_vaf=support.reported_vaf,
    )
