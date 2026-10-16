"""Execute a progressive query plan against registered providers.

``run_plan`` walks the plan tiers in ``MatchSpecificity`` order, asks each
provider named on the item, collects every ``SourceQueryResult`` (including
``NOT_QUERIED`` entries for skipped work) and de-duplicates evidence by
``(source_name, source_native_id)`` keeping the most specific match.

Honesty rules: an item that was not run because of ``offline`` mode, a
``stop_when`` condition or a missing provider produces a ``NOT_QUERIED``
result with a message, so the absence of evidence is never silent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import EvidenceRecord, MatchSpecificity, SourceQuery, SourceQueryResult, SourceStatus
from somaweave.providers.base import PayloadCache, ProviderRegistry
from somaweave.retrieval.plan import TIER_RANK, PlanItem


class RetrievalResult(BaseModel):
    """Everything retrieved for one alteration: outcomes per query plus deduplicated evidence."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    alteration_id: str
    started_at: datetime
    finished_at: datetime
    offline: bool = False
    plan: list[PlanItem] = Field(default_factory=list)
    query_results: list[SourceQueryResult] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    duplicates_removed: int = 0
    stopped_after_tier: Optional[MatchSpecificity] = None

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.query_results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        return dict(sorted(counts.items()))

    def results_for(self, tier: MatchSpecificity) -> list[SourceQueryResult]:
        return [r for r in self.query_results if r.query.tier == tier]


StopCondition = Callable[["RetrievalResult", PlanItem], bool]


def stop_after_tier(tier: MatchSpecificity) -> StopCondition:
    """Stop once the given tier has been completed."""

    def _stop(result: RetrievalResult, item: PlanItem) -> bool:
        return TIER_RANK[item.tier] >= TIER_RANK[tier]

    return _stop


def stop_when_curated_evidence(min_records: int = 1, curated_sources: tuple[str, ...] = ("civic", "clinvar")) -> StopCondition:
    """Stop once at least ``min_records`` curated-source records with variant_match at
    or more specific than the completed tier have been collected."""

    def _stop(result: RetrievalResult, item: PlanItem) -> bool:
        n = sum(1 for e in result.evidence if e.source_name in curated_sources and TIER_RANK[e.variant_match] <= TIER_RANK[item.tier])
        return n >= min_records

    return _stop


def _not_queried(item: PlanItem, provider_name: str, message: str, now: datetime) -> SourceQueryResult:
    return SourceQueryResult(
        query=SourceQuery(source_name=provider_name, tier=item.tier, query_terms=dict(item.terms)),
        status=SourceStatus.NOT_QUERIED, retrieved_at=now, message=message,
    )


def dedupe_evidence(records: list[EvidenceRecord]) -> tuple[list[EvidenceRecord], int]:
    """Collapse records sharing ``(source_name, source_native_id)``.

    The surviving record is the one with the most specific ``variant_match``
    (then most specific ``query_tier``); order of first appearance is kept.
    """
    best: dict[tuple[str, str], EvidenceRecord] = {}
    order: list[tuple[str, str]] = []
    removed = 0
    for rec in records:
        key = (rec.source_name, rec.source_native_id)
        if key not in best:
            best[key] = rec
            order.append(key)
            continue
        removed += 1
        cur = best[key]
        if (TIER_RANK[rec.variant_match], TIER_RANK[rec.query_tier]) < (TIER_RANK[cur.variant_match], TIER_RANK[cur.query_tier]):
            best[key] = rec
    return [best[k] for k in order], removed


def run_plan(plan: list[PlanItem], registry: ProviderRegistry, stop_when: StopCondition | None = None, *,
             offline: bool = False, cache_root: str | Path | None = None) -> RetrievalResult:
    """Run every plan item on its providers.

    ``cache_root`` (e.g. the value of ``SOMAWEAVE_CACHE_ROOT`` resolved by the
    caller) enables the raw-payload cache; ``EvidenceRecord.raw_reference``
    then points to ``<provider>/<sha256>`` under that directory.
    """
    if not plan:
        raise ValueError("empty plan")
    started = datetime.now(timezone.utc)
    cache = PayloadCache(cache_root) if cache_root else None
    ordered = sorted(plan, key=lambda it: it.rank)
    result = RetrievalResult(case_id=ordered[0].case_id, alteration_id=ordered[0].alteration_id,
                             started_at=started, finished_at=started, offline=offline, plan=ordered)
    collected: list[EvidenceRecord] = []
    stopped: Optional[MatchSpecificity] = None
    for item in ordered:
        now = datetime.now(timezone.utc)
        if not item.providers:
            result.query_results.append(_not_queried(item, "planner", f"tier {item.tier.value} not applicable: {item.description}", now))
            continue
        for name in item.providers:
            if stopped is not None:
                result.query_results.append(_not_queried(item, name, f"skipped: stop condition met after tier {stopped.value}", now))
                continue
            if offline:
                result.query_results.append(_not_queried(item, name, "offline mode", now))
                continue
            provider = registry.get(name)
            if provider is None:
                result.query_results.append(_not_queried(item, name, "provider not configured in registry", now))
                continue
            qres, records = provider.query(item, cache=cache)
            result.query_results.append(qres)
            collected.extend(records)
        result.evidence, result.duplicates_removed = dedupe_evidence(collected)
        if stopped is None and stop_when is not None and not offline and stop_when(result, item):
            stopped = item.tier
    result.evidence, result.duplicates_removed = dedupe_evidence(collected)
    result.stopped_after_tier = stopped
    result.finished_at = datetime.now(timezone.utc)
    return result
