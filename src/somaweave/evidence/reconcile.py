"""Reconcile retrieved evidence for one alteration into an ``EvidenceSet``.

Responsibilities (see ``reconcile``):

1. Disease matching. Every record gets ``disease_match`` relative to the
   pathology-confirmed OncoTree code via
   ``somaweave.normalization.disease.disease_match_detail`` on the supplied
   ``OncoTreeIndex`` (built-in subset by default). The record's OncoTree code,
   DOID and name are tried in that order; the resolution path (code, doid,
   name, synonym, main_type, ...) is stored in ``EvidenceSet.disease_resolutions``
   and appended to the record's ``limitations`` as
   ``disease_match_resolution=<path>`` so downstream outputs carry it.
   Disease hypotheses are evaluated separately with the same index and stored
   per record in ``EvidenceSet.hypothesis_disease_matches``; they never
   overwrite the confirmed-diagnosis match.
2. Acceptance. ``is_accepted`` decides whether a record is a curated,
   accepted assertion (CIViC status ``accepted``; ClinVar classification with
   assertion criteria) as opposed to a submitted item or a literature text
   match. Acceptance is about curation status only, not about correctness.
3. Grouping by ``(evidence_category, direction)``.
4. Conflict detection among accepted records sharing category and drug set
   whose direction or source-native significance oppose each other.
5. Source-native levels, ratings and statuses are carried verbatim on the
   records; nothing here rewrites them.
6. Coverage. Per source and tier, each ``SourceQueryResult`` is mapped to
   one of three states: ``ok`` (records returned), ``no_records`` (queried
   successfully, nothing found) or ``missing`` (unavailable, error, no
   credentials, not queried). ``not_supported`` queries are reported as
   ``not_applicable`` because the source cannot answer that tier by design.
   Only ``no_records`` may ever be read as absence of curated evidence.
7. Provenance. Each record gets a list of provenance entries (query tier,
   source, retrieval time, source version, raw payload reference, native
   request) assembled from the query results that returned it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from somaweave.domain import (
    Alteration,
    DiseaseMatch,
    EvidenceCategory,
    EvidenceDirection,
    EvidenceRecord,
    SourceQueryResult,
    SourceStatus,
)
from somaweave.normalization import BUILTIN_ONCOTREE, NormalizedCase, OncoTreeTable
from somaweave.normalization.disease import DiseaseMatchResult, OncoTreeIndex, disease_match_detail
from somaweave.evidence.applicability import INAPPLICABLE_LIMITATION_PREFIX, VARIANT_MATCHED_CLASSES, applicability_for
from somaweave.retrieval import RetrievalResult


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


CoverageState = Literal["ok", "no_records", "missing", "not_applicable"]

QUERIED_OK_STATUSES: frozenset[SourceStatus] = frozenset({SourceStatus.OK, SourceStatus.NO_RECORDS})
MISSING_STATUSES: frozenset[SourceStatus] = frozenset({
    SourceStatus.UNAVAILABLE, SourceStatus.ERROR, SourceStatus.NOT_QUERIED, SourceStatus.NO_CREDENTIALS,
})
# ClinVar review-status phrases that indicate a classification with stated criteria.
ACCEPTED_CLINVAR_REVIEW_TERMS: tuple[str, ...] = ("criteria provided", "reviewed by expert panel", "practice guideline")
LITERATURE_SOURCES: frozenset[str] = frozenset({"europepmc"})
PLANNER_SOURCE = "planner"  # pseudo-source recording tiers the planner did not emit; never a knowledge base

# Source-native significance pairs that oppose each other (CIViC vocabulary).
_OPPOSITE_SIGNIFICANCE: dict[str, str] = {
    "SENSITIVITYRESPONSE": "RESISTANCE", "RESISTANCE": "SENSITIVITYRESPONSE",
    "REDUCED_SENSITIVITY": "SENSITIVITYRESPONSE",
    "BETTER_OUTCOME": "POOR_OUTCOME", "POOR_OUTCOME": "BETTER_OUTCOME",
    "POSITIVE": "NEGATIVE", "NEGATIVE": "POSITIVE",
    "ONCOGENICITY": "PROTECTIVENESS", "PROTECTIVENESS": "ONCOGENICITY",
    "GAIN_OF_FUNCTION": "LOSS_OF_FUNCTION", "LOSS_OF_FUNCTION": "GAIN_OF_FUNCTION",
}


class Provenance(_Model):
    query_tier: str
    source_name: str
    retrieved_at: datetime
    source_version: Optional[str] = None
    raw_reference: Optional[str] = None
    native_request: Optional[str] = None


class DiseaseResolutionRecord(_Model):
    """How one record's disease was related to the confirmed diagnosis (provenance)."""

    evidence_id: str
    match: DiseaseMatch
    case_code: Optional[str] = None
    evidence_code: Optional[str] = Field(default=None, description="Resolved OncoTree code or the PAN_CANCER sentinel.")
    resolution_path: str = Field(description="code | doid | pan_cancer | name | synonym | main_type | name_ambiguous | unresolved")
    label_used: Optional[str] = Field(default=None, description="Which record field resolved: oncotree_code, doid or name.")
    detail: Optional[str] = None


class EvidenceGroup(_Model):
    evidence_category: EvidenceCategory
    direction: EvidenceDirection
    evidence_ids: list[str] = Field(default_factory=list)
    accepted_ids: list[str] = Field(default_factory=list)


class Conflict(_Model):
    evidence_category: EvidenceCategory
    drugs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    same_disease: bool = Field(description="True if the conflicting records concern the same source disease label.")
    description: str


class SourceCoverage(_Model):
    source_name: str
    tier: str
    state: CoverageState
    status: SourceStatus
    record_count: int = 0
    message: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    source_version: Optional[str] = None


class SourceSummary(_Model):
    source_name: str
    state: Literal["ok", "no_records", "missing", "not_applicable"]
    record_count: int = 0
    tiers_ok: list[str] = Field(default_factory=list)
    tiers_no_records: list[str] = Field(default_factory=list)
    tiers_missing: list[str] = Field(default_factory=list)
    missing_statuses: dict[str, int] = Field(default_factory=dict)


class EvidenceSet(_Model):
    case_id: str
    alteration_id: str
    confirmed_oncotree_code: Optional[str] = None
    hypothesis_labels: list[str] = Field(default_factory=list, description="Hypothesis identifiers (code or name) evaluated separately.")
    records: list[EvidenceRecord] = Field(default_factory=list, description="Records with disease_match set against the confirmed diagnosis.")
    accepted_ids: list[str] = Field(default_factory=list, description="Accepted AND alteration-class-applicable records: the pool for interpretation.")
    accepted_all_ids: list[str] = Field(default_factory=list, description="All accepted records, including those excluded for alteration-class mismatch.")
    profile_classes: dict[str, str] = Field(default_factory=dict, description="evidence_id -> molecular-profile class of the record.")
    inapplicable_ids: list[str] = Field(default_factory=list, description="Records whose profile class cannot be produced by the case alteration.")
    excluded_by_class: dict[str, int] = Field(default_factory=dict, description="Accepted records excluded, counted by profile class.")
    variant_matched_ids: list[str] = Field(default_factory=list, description="Applicable records whose profile is variant-, codon- or class-matched (not merely gene-level).")
    matched_conditions: dict[str, str] = Field(default_factory=dict, description="evidence_id -> which listed condition produced the disease match (multi-condition records).")
    hypothesis_match_summary: dict[str, dict[str, int]] = Field(default_factory=dict, description="hypothesis label -> {same_disease: n, parent_disease: n} among applicable accepted records.")
    significance: dict[str, str] = Field(default_factory=dict, description="evidence_id -> source-native significance token if parsable.")
    hypothesis_disease_matches: dict[str, dict[str, DiseaseMatch]] = Field(default_factory=dict, description="evidence_id -> {hypothesis label -> match}.")
    disease_resolutions: dict[str, DiseaseResolutionRecord] = Field(default_factory=dict, description="evidence_id -> how its disease was resolved against the confirmed code.")
    oncotree_source: Optional[str] = Field(default=None, description="Source of the OncoTree index used (file path or 'builtin-subset').")
    groups: list[EvidenceGroup] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    coverage: list[SourceCoverage] = Field(default_factory=list)
    source_summaries: list[SourceSummary] = Field(default_factory=list)
    query_results: list[SourceQueryResult] = Field(default_factory=list)
    provenance: dict[str, list[Provenance]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    def record(self, evidence_id: str) -> EvidenceRecord:
        for r in self.records:
            if r.evidence_id == evidence_id:
                return r
        raise KeyError(evidence_id)

    def accepted(self) -> list[EvidenceRecord]:
        """Accepted records that are applicable to the case alteration (the interpretation pool)."""
        ids = set(self.accepted_ids)
        return [r for r in self.records if r.evidence_id in ids]

    def accepted_all(self) -> list[EvidenceRecord]:
        ids = set(self.accepted_all_ids)
        return [r for r in self.records if r.evidence_id in ids]

    def inapplicable_accepted(self) -> list[EvidenceRecord]:
        ids = set(self.accepted_all_ids) & set(self.inapplicable_ids)
        return [r for r in self.records if r.evidence_id in ids]

    def is_variant_matched(self, evidence_id: str) -> bool:
        return evidence_id in set(self.variant_matched_ids)

    def missing_sources(self) -> list[SourceSummary]:
        return [s for s in self.source_summaries if s.state == "missing" and s.source_name != PLANNER_SOURCE]

    def queried_ok_sources(self) -> list[str]:
        return [s.source_name for s in self.source_summaries if s.state in ("ok", "no_records")]


def civic_significance(record: EvidenceRecord) -> Optional[str]:
    """Extract ``significance=<TOKEN>`` from a CIViC ``source_native_status``; ``None`` otherwise."""
    status = record.source_native_status or ""
    marker = "significance="
    if marker not in status:
        return None
    token = status.split(marker, 1)[1].strip()
    return token.split(";")[0].strip().upper() or None


def is_accepted(record: EvidenceRecord) -> bool:
    """Whether a record is an accepted curated assertion.

    - literature text matches are never accepted;
    - CIViC: ``source_native_status`` starts with ``accepted`` and no
      ``submitted_not_accepted``/``civic_status_*`` limitation;
    - ClinVar: review status (``source_native_level``) states criteria
      (``criteria provided``, ``reviewed by expert panel``, ``practice guideline``);
    - other curated sources: ``is_hypothesis`` is False and status does not
      say ``submitted``.
    """
    if record.source_name in LITERATURE_SOURCES or "literature_text_match_not_curated" in record.limitations:
        return False
    if any(lim == "submitted_not_accepted" or lim.startswith("civic_status_") for lim in record.limitations):
        return False
    status = (record.source_native_status or "").strip().lower()
    if record.source_name == "civic":
        return status.startswith("accepted")
    if record.source_name == "clinvar":
        level = (record.source_native_level or "").lower()
        if level.startswith("no assertion") or level.startswith("no classification"):
            return False
        return any(term in level for term in ACCEPTED_CLINVAR_REVIEW_TERMS)
    if status.startswith("submitted"):
        return False
    return not record.is_hypothesis


RESOLUTION_LIMITATION_PREFIX = "disease_match_resolution="
CONDITION_LIMITATION_PREFIX = "disease_match_condition="
# Preference order when a multi-condition record matches on several conditions.
MATCH_RANK: dict[DiseaseMatch, int] = {DiseaseMatch.SAME: 0, DiseaseMatch.PARENT: 1, DiseaseMatch.RELATED: 2,
                                        DiseaseMatch.PAN_CANCER: 3, DiseaseMatch.DIFFERENT: 4, DiseaseMatch.UNKNOWN: 5}


def match_record_disease_detail(record: EvidenceRecord, case_code: Optional[str],
                                index: OncoTreeTable) -> tuple[DiseaseMatchResult, Optional[str]]:
    """Best resolvable match between a record's disease and a case code.

    Tries the record's OncoTree code, then its DOID, then its name; returns the
    first that resolves together with the field that resolved it. A literature
    hit whose recorded disease is only the query term (limitation
    ``disease_not_constrained_in_query``) is forced to ``UNKNOWN``.
    """
    idx = OncoTreeIndex.from_table(index)
    if "disease_not_constrained_in_query" in record.limitations:
        return DiseaseMatchResult(match=DiseaseMatch.UNKNOWN, case_code=case_code, resolution_path="unresolved",
                                  detail="literature hit: recorded disease is the query term, not the article's subject"), None
    if record.disease is None and not record.conditions:
        return DiseaseMatchResult(match=DiseaseMatch.UNKNOWN, case_code=case_code, resolution_path="unresolved", detail="record has no disease"), None
    candidates = list(record.conditions) if record.conditions else []
    if record.disease is not None and record.disease not in candidates:
        candidates.insert(0, record.disease)
    best: Optional[tuple[DiseaseMatchResult, str]] = None
    last: Optional[DiseaseMatchResult] = None
    for cond in candidates:
        attempts: list[tuple[str, Optional[str], Optional[str]]] = []
        if cond.oncotree_code:
            attempts.append(("oncotree_code", cond.oncotree_code, None))
        if cond.doid:
            attempts.append(("doid", None, cond.doid))
        if cond.name:
            attempts.append(("name", cond.name, None))
        for field, label, doid in attempts:
            res = disease_match_detail(case_code, label, idx, doid=doid)
            if res.match != DiseaseMatch.UNKNOWN:
                tag = f"{field}:{cond.name}" if len(candidates) > 1 else field
                if best is None or MATCH_RANK[res.match] < MATCH_RANK[best[0].match]:
                    best = (res, tag)
                break
            last = res
    if best is not None:
        return best
    if last is None:
        last = DiseaseMatchResult(match=DiseaseMatch.UNKNOWN, case_code=case_code, resolution_path="unresolved", detail="record disease has no code, DOID or name")
    return last, None


def match_record_disease(record: EvidenceRecord, case_code: Optional[str], table: OncoTreeTable) -> DiseaseMatch:
    """Best resolvable match between a record's disease label and a case code (code, then DOID, then name)."""
    return match_record_disease_detail(record, case_code, table)[0].match


def coverage_state(status: SourceStatus) -> CoverageState:
    if status == SourceStatus.OK:
        return "ok"
    if status == SourceStatus.NO_RECORDS:
        return "no_records"
    if status == SourceStatus.NOT_SUPPORTED:
        return "not_applicable"
    return "missing"


def coverage_from_results(query_results: list[SourceQueryResult]) -> tuple[list[SourceCoverage], list[SourceSummary]]:
    """Per (source, tier) coverage rows plus a per-source summary.

    Summary rule: ``ok`` if any tier returned records; otherwise ``no_records``
    if at least one tier was queried successfully; otherwise ``missing`` if any
    tier is missing; ``not_applicable`` only when every query was unsupported.
    Partially missing tiers are always listed in ``tiers_missing`` so a source
    that answered one tier but failed another is not read as complete.
    """
    rows: list[SourceCoverage] = []
    per_source: dict[str, list[SourceCoverage]] = {}
    for qr in query_results:
        state = "not_applicable" if qr.query.source_name == PLANNER_SOURCE else coverage_state(qr.status)
        row = SourceCoverage(
            source_name=qr.query.source_name, tier=qr.query.tier.value, state=state, status=qr.status,
            record_count=qr.record_count, message=qr.message, retrieved_at=qr.retrieved_at, source_version=qr.source_version,
        )
        rows.append(row)
        per_source.setdefault(row.source_name, []).append(row)
    summaries: list[SourceSummary] = []
    for name in sorted(per_source):
        src_rows = per_source[name]
        tiers_ok = [r.tier for r in src_rows if r.state == "ok"]
        tiers_nr = [r.tier for r in src_rows if r.state == "no_records"]
        tiers_missing = [r.tier for r in src_rows if r.state == "missing"]
        missing_statuses: dict[str, int] = {}
        for r in src_rows:
            if r.state == "missing":
                missing_statuses[r.status.value] = missing_statuses.get(r.status.value, 0) + 1
        if tiers_ok:
            state = "ok"
        elif tiers_nr:
            state = "no_records"
        elif tiers_missing:
            state = "missing"
        else:
            state = "not_applicable"
        summaries.append(SourceSummary(
            source_name=name, state=state, record_count=sum(r.record_count for r in src_rows),
            tiers_ok=tiers_ok, tiers_no_records=tiers_nr, tiers_missing=tiers_missing, missing_statuses=missing_statuses,
        ))
    return rows, summaries


def _drug_key(record: EvidenceRecord) -> tuple[str, ...]:
    return tuple(sorted({d.strip().lower() for d in record.drugs if d and d.strip()}))


def _stance(record: EvidenceRecord, significance: Optional[str]) -> tuple[str, str]:
    return (record.direction.value, significance or "")


def _opposed(a: tuple[str, str], b: tuple[str, str]) -> bool:
    dir_a, sig_a = a
    dir_b, sig_b = b
    if EvidenceDirection.NOT_APPLICABLE.value in (dir_a, dir_b):
        return False
    if sig_a == sig_b:
        return dir_a != dir_b and {dir_a, dir_b} == {EvidenceDirection.SUPPORTS.value, EvidenceDirection.DOES_NOT_SUPPORT.value}
    if dir_a == dir_b == EvidenceDirection.SUPPORTS.value:
        return _OPPOSITE_SIGNIFICANCE.get(sig_a) == sig_b
    return False


def detect_conflicts(records: list[EvidenceRecord], significance: dict[str, str]) -> list[Conflict]:
    """Conflicts among *accepted* records with the same category and drug set.

    Records are compared only when they also share the source's variant
    description (e.g. the CIViC molecular profile name), so gene-tier hits
    for different profiles are not read as conflicting.
    Two records oppose each other when they share a significance token but
    differ in direction (supports vs does_not_support), or both support
    mutually exclusive significances (e.g. sensitivity vs resistance,
    better vs poor outcome). Records from different source diseases are still
    reported, flagged ``same_disease=False``, so a reviewer can judge.
    """
    buckets: dict[tuple[EvidenceCategory, tuple[str, ...], str], list[EvidenceRecord]] = {}
    for r in records:
        buckets.setdefault((r.evidence_category, _drug_key(r), (r.variant_description or "").strip().lower()), []).append(r)
    conflicts: list[Conflict] = []
    for (cat, drugs, _variant), items in buckets.items():
        if len(items) < 2:
            continue
        seen_pairs: set[tuple[str, str]] = set()
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if not _opposed(_stance(a, significance.get(a.evidence_id)), _stance(b, significance.get(b.evidence_id))):
                    continue
                pair = tuple(sorted((a.evidence_id, b.evidence_id)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                da = a.disease.name if a.disease else "unspecified disease"
                db = b.disease.name if b.disease else "unspecified disease"
                conflicts.append(Conflict(
                    evidence_category=cat, drugs=list(drugs), evidence_ids=list(pair), same_disease=(da.lower() == db.lower()),
                    description=(f"{cat.value}: {a.evidence_id} ({a.direction.value}; {significance.get(a.evidence_id) or 'n/a'}; {da}) vs "
                                 f"{b.evidence_id} ({b.direction.value}; {significance.get(b.evidence_id) or 'n/a'}; {db})"),
                ))
    return conflicts


def _provenance(record: EvidenceRecord, query_results: list[SourceQueryResult]) -> list[Provenance]:
    out: list[Provenance] = []
    for qr in query_results:
        if record.evidence_id in qr.evidence_ids:
            out.append(Provenance(query_tier=qr.query.tier.value, source_name=qr.query.source_name, retrieved_at=qr.retrieved_at,
                                  source_version=qr.source_version, raw_reference=record.raw_reference,
                                  native_request=qr.query.native_request))
    if not out:
        out.append(Provenance(query_tier=record.query_tier.value, source_name=record.source_name, retrieved_at=record.retrieved_at,
                              source_version=record.source_version, raw_reference=record.raw_reference))
    return out


def reconcile(normalized_case: NormalizedCase, alteration: Alteration, retrieval_result: RetrievalResult,
              index: Optional[OncoTreeTable] = None) -> EvidenceSet:
    """Build the ``EvidenceSet`` for one alteration (see module docstring).

    ``index`` is the OncoTree index used for every disease match and for the
    disease hypotheses; ``None`` means the built-in subset.
    """
    if retrieval_result.alteration_id != alteration.alteration_id:
        raise ValueError(f"retrieval result is for {retrieval_result.alteration_id}, not {alteration.alteration_id}")
    table = OncoTreeIndex.from_table(index) if index is not None else BUILTIN_ONCOTREE
    disease_ctx = normalized_case.disease
    case_code = disease_ctx.confirmed_oncotree_code
    hyps = [(h.oncotree_code or h.name, h.oncotree_code or h.name) for h in disease_ctx.hypotheses]

    records: list[EvidenceRecord] = []
    accepted_ids: list[str] = []
    accepted_all_ids: list[str] = []
    profile_classes: dict[str, str] = {}
    inapplicable_ids: list[str] = []
    variant_matched_ids: list[str] = []
    excluded_by_class: dict[str, int] = {}
    matched_conditions: dict[str, str] = {}
    significance: dict[str, str] = {}
    hyp_matches: dict[str, dict[str, DiseaseMatch]] = {}
    resolutions: dict[str, DiseaseResolutionRecord] = {}
    notes: list[str] = []
    for rec in retrieval_result.evidence:
        res, field = match_record_disease_detail(rec, case_code, table)
        limitations = [lim for lim in rec.limitations
                       if not lim.startswith((RESOLUTION_LIMITATION_PREFIX, CONDITION_LIMITATION_PREFIX, INAPPLICABLE_LIMITATION_PREFIX))]
        limitations.append(f"{RESOLUTION_LIMITATION_PREFIX}{res.resolution_path}")
        if field and ":" in field:
            cond_name = field.split(":", 1)[1]
            limitations.append(f"{CONDITION_LIMITATION_PREFIX}{cond_name}")
            matched_conditions[rec.evidence_id] = cond_name
        app = applicability_for(rec, alteration, list(normalized_case.case.alterations))
        if app.profile_class == "codon" and app.applicable:
            limitations.append("codon_match_not_identical_substitution: a different amino-acid change at the same codon; "
                               "equivalence is not assumed, context review required")
        profile_classes[rec.evidence_id] = app.profile_class
        if not app.applicable:
            limitations.append(f"{INAPPLICABLE_LIMITATION_PREFIX}{app.profile_class} ({app.reason})")
            inapplicable_ids.append(rec.evidence_id)
        elif app.variant_matched:
            variant_matched_ids.append(rec.evidence_id)
        new = rec.model_copy(update={"disease_match": res.match, "limitations": limitations})
        records.append(new)
        resolutions[new.evidence_id] = DiseaseResolutionRecord(
            evidence_id=new.evidence_id, match=res.match, case_code=res.case_code, evidence_code=res.evidence_code,
            resolution_path=res.resolution_path, label_used=(field.split(":", 1)[0] if field else None), detail=res.detail,
        )
        if is_accepted(new):
            accepted_all_ids.append(new.evidence_id)
            if app.applicable:
                accepted_ids.append(new.evidence_id)
            else:
                excluded_by_class[app.profile_class] = excluded_by_class.get(app.profile_class, 0) + 1
        sig = civic_significance(new)
        if sig:
            significance[new.evidence_id] = sig
        if hyps:
            per_h: dict[str, DiseaseMatch] = {}
            for label, code in hyps:
                per_h[label] = match_record_disease(new, code, table)
            hyp_matches[new.evidence_id] = per_h

    if excluded_by_class:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(excluded_by_class.items()))
        notes.append(f"{sum(excluded_by_class.values())} accepted record(s) excluded from the interpretation pools because their molecular profile "
                     f"cannot be produced by this alteration ({parts}); retained as context")
    hyp_summary: dict[str, dict[str, int]] = {}
    if hyps:
        acc_app = set(accepted_ids)
        for label, _code in hyps:
            counts = {"same_disease": 0, "parent_disease": 0, "variant_matched_same_or_parent": 0}
            for eid, per_h in hyp_matches.items():
                if eid not in acc_app:
                    continue
                m = per_h.get(label)
                if m == DiseaseMatch.SAME:
                    counts["same_disease"] += 1
                elif m == DiseaseMatch.PARENT:
                    counts["parent_disease"] += 1
                if m in (DiseaseMatch.SAME, DiseaseMatch.PARENT) and eid in set(variant_matched_ids):
                    counts["variant_matched_same_or_parent"] += 1
            hyp_summary[label] = counts
    unresolved = sum(1 for r in records if r.disease is not None and r.disease_match == DiseaseMatch.UNKNOWN)
    if unresolved:
        notes.append(f"{unresolved} record(s) have a disease label that does not resolve in the OncoTree table "
                     f"({table.source}); disease_match left UNKNOWN, not DIFFERENT")
    if case_code is None:
        notes.append("confirmed diagnosis has no OncoTree code; all disease matches are UNKNOWN")

    groups_map: dict[tuple[EvidenceCategory, EvidenceDirection], EvidenceGroup] = {}
    acc = set(accepted_ids)
    for r in records:
        key = (r.evidence_category, r.direction)
        g = groups_map.setdefault(key, EvidenceGroup(evidence_category=key[0], direction=key[1]))
        g.evidence_ids.append(r.evidence_id)
        if r.evidence_id in acc:
            g.accepted_ids.append(r.evidence_id)
    groups = sorted(groups_map.values(), key=lambda g: (g.evidence_category.value, g.direction.value))

    conflicts = detect_conflicts([r for r in records if r.evidence_id in acc], significance)
    coverage, summaries = coverage_from_results(retrieval_result.query_results)
    provenance = {r.evidence_id: _provenance(r, retrieval_result.query_results) for r in records}

    return EvidenceSet(
        case_id=normalized_case.case.case_id, alteration_id=alteration.alteration_id, confirmed_oncotree_code=case_code,
        hypothesis_labels=[label for label, _ in hyps], records=records, accepted_ids=accepted_ids, accepted_all_ids=accepted_all_ids,
        profile_classes=profile_classes, inapplicable_ids=inapplicable_ids, excluded_by_class=excluded_by_class,
        variant_matched_ids=variant_matched_ids, matched_conditions=matched_conditions, hypothesis_match_summary=hyp_summary,
        significance=significance,
        hypothesis_disease_matches=hyp_matches, disease_resolutions=resolutions, oncotree_source=table.source, groups=groups,
        conflicts=conflicts, coverage=coverage, source_summaries=summaries, query_results=list(retrieval_result.query_results),
        provenance=provenance, notes=notes,
    )
