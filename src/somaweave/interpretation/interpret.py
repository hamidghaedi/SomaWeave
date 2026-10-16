"""Four-axis interpretation of one alteration (rules in ``somaweave.interpretation.rules``).

``interpret`` is deterministic: the same inputs always give the same
``FindingAssessment``. Every established claim ends with a bracketed list of
evidence ids; hypotheses end with ``[hypothesis]``; limitations name missing
sources explicitly. Nothing here calls a network or a language model.
"""

from __future__ import annotations

from typing import Optional

from somaweave.domain import (
    ActionabilityAssessment,
    Alteration,
    AnalyticalReliability,
    CaseRelevance,
    DiseaseMatch,
    EvidenceCategory,
    EvidenceDirection,
    EvidenceRecord,
    FindingAssessment,
    MatchSpecificity,
    OncogenicityAssessment,
    SpecimenRole,
)
from somaweave.evidence import EvidenceSet
from somaweave.interpretation.rules import (
    RELIABILITY_ORDER,
    actionability_tier_for,
    amp_level_for,
)
from somaweave.normalization import NormalizedCase
from somaweave.technical import specimen_chronology

CLINICAL_CATEGORIES = (EvidenceCategory.PREDICTIVE, EvidenceCategory.PROGNOSTIC, EvidenceCategory.DIAGNOSTIC)
ONCO_POOL_CATEGORIES = (EvidenceCategory.ONCOGENIC,) + CLINICAL_CATEGORIES
RESISTANCE_SIGNIFICANCE = frozenset({"RESISTANCE", "REDUCED_SENSITIVITY"})
SENSITIVITY_SIGNIFICANCE = frozenset({"SENSITIVITYRESPONSE", "SENSITIVITY", "RESPONSE"})
BENIGN_TOKENS = ("benign",)
ONCOGENIC_TOKENS = ("oncogenic",)
TIER_RANK = {"I": 1, "II": 2, "III": 3, "IV": 4, "not_assessed": 5}
SOURCE_LABELS = {"civic": "CIViC", "clinvar": "ClinVar", "europepmc": "Europe PMC"}


def _cite(ids: list[str]) -> str:
    return "[" + ", ".join(ids) + "]"


def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _disease_text(rec: EvidenceRecord) -> str:
    name = rec.disease.name if rec.disease else "unspecified disease"
    return f"{name} ({rec.disease_match.value})"


def _states(es: EvidenceSet) -> dict[str, str]:
    return {s.source_name: s.state for s in es.source_summaries}


def _curated_queried_ok(es: EvidenceSet) -> bool:
    return any(s.state in ("ok", "no_records") for s in es.source_summaries if s.source_name not in ("europepmc", "planner"))


def _missing_limitations(es: EvidenceSet) -> list[str]:
    out: list[str] = []
    for s in es.source_summaries:
        if s.source_name == "planner":
            continue
        if s.state == "missing":
            statuses = ", ".join(f"{k} x{v}" for k, v in sorted(s.missing_statuses.items()))
            out.append(f"{_label(s.source_name)}: missing evidence ({statuses}); absence of records must not be read as negative")
        elif s.tiers_missing:
            statuses = ", ".join(f"{k} x{v}" for k, v in sorted(s.missing_statuses.items()))
            out.append(f"{_label(s.source_name)}: tiers {', '.join(s.tiers_missing)} missing ({statuses})")
    return out


# --- analytical ---------------------------------------------------------------

def assess_analytical(alteration: Alteration, technical_assessments: list[AnalyticalReliability]) -> AnalyticalReliability:
    """Worst reliability across the tumour-specimen assessments of this alteration."""
    if not technical_assessments:
        return AnalyticalReliability(level="not_assessable", flags=["no_tumor_measurement"],
                                     rationale=[f"no tumour-specimen measurement recorded for {alteration.alteration_id}"])
    worst = min(technical_assessments, key=lambda a: RELIABILITY_ORDER.get(a.level, 0))
    if len(technical_assessments) > 1:
        others = ", ".join(f"{a.specimen_id}:{a.level}" for a in technical_assessments)
        worst = worst.model_copy(update={"rationale": list(worst.rationale) + [f"worst of {len(technical_assessments)} specimens ({others})"]})
    return worst


# --- oncogenicity ---------------------------------------------------------------

def _is_onco_supportive(rec: EvidenceRecord, es: EvidenceSet) -> bool:
    if "clinvar_is_germline_oriented" in rec.limitations:
        return False
    if rec.evidence_category == EvidenceCategory.ONCOGENIC:
        status = (rec.source_native_status or "").lower()
        if any(tok in status for tok in BENIGN_TOKENS):
            return False
        return any(tok in status for tok in ONCOGENIC_TOKENS) or es.significance.get(rec.evidence_id) == "ONCOGENICITY" \
            or rec.direction == EvidenceDirection.SUPPORTS
    if rec.evidence_category in CLINICAL_CATEGORIES:
        return rec.direction != EvidenceDirection.DOES_NOT_SUPPORT
    return False


def _is_benign(rec: EvidenceRecord, es: EvidenceSet) -> bool:
    if "clinvar_is_germline_oriented" in rec.limitations:
        return False
    status = (rec.source_native_status or "").lower()
    if rec.evidence_category == EvidenceCategory.ONCOGENIC and any(tok in status for tok in BENIGN_TOKENS):
        return True
    return es.significance.get(rec.evidence_id) in ("BENIGN", "LIKELY_BENIGN", "PROTECTIVENESS")


def assess_oncogenicity(alteration: Alteration, es: EvidenceSet) -> OncogenicityAssessment:
    accepted = es.accepted()
    supportive = [r for r in accepted if r.evidence_category in ONCO_POOL_CATEGORIES and _is_onco_supportive(r, es)]
    benign = [r for r in accepted if _is_benign(r, es)]
    functional = [r for r in accepted if r.evidence_category == EvidenceCategory.FUNCTIONAL and r.variant_match == MatchSpecificity.EXACT_VARIANT]
    exact = [r for r in supportive if r.variant_match == MatchSpecificity.EXACT_VARIANT]
    codon = [r for r in supportive if r.variant_match == MatchSpecificity.CODON]
    exact_sources = sorted({r.source_name for r in exact})
    criteria: list[str] = []
    rationale: list[str] = []
    used: list[str] = []

    os1 = [r for r in exact if r.evidence_category == EvidenceCategory.ONCOGENIC]
    if os1:
        criteria.append("OS1")
        rationale.append(f"OS1: accepted exact-variant oncogenic classification {_cite([r.evidence_id for r in os1])}")
    os2 = [r for r in functional if r.direction == EvidenceDirection.SUPPORTS]
    sbs2 = [r for r in functional if r.direction == EvidenceDirection.DOES_NOT_SUPPORT]
    if os2:
        criteria.append("OS2")
        rationale.append(f"OS2: accepted functional evidence supports an oncogenic effect {_cite([r.evidence_id for r in os2])}")
    if sbs2:
        criteria.append("SBS2")
        rationale.append(f"SBS2: accepted functional evidence does not support an oncogenic effect {_cite([r.evidence_id for r in sbs2])}")
    hotspot = exact + codon
    if len(hotspot) >= 3:
        criteria.append("OS3")
        rationale.append(f"OS3 (approximation): {len(hotspot)} accepted curated records at exact-variant/codon level {_cite([r.evidence_id for r in hotspot])}")
    elif hotspot:
        criteria.append("OM3")
        rationale.append(f"OM3 (approximation): {len(hotspot)} accepted curated record(s) at exact-variant/codon level {_cite([r.evidence_id for r in hotspot])}")
    if benign:
        criteria.append("SBx")
        rationale.append(f"benign evidence present {_cite([r.evidence_id for r in benign])}")
    rationale.append("OP1/SBP1: computational predictor evidence not assessed (no predictor data available)")
    used = sorted({r.evidence_id for r in supportive + benign + functional})

    if not _curated_queried_ok(es):
        classification = "not_assessed"
        rationale.insert(0, "no curated source could be queried; oncogenicity not assessed (missing evidence, not negative)")
    elif supportive and benign:
        classification = "uncertain_significance"
        rationale.insert(0, "supportive and benign accepted evidence coexist; classification left uncertain for review")
    elif exact and (len(exact_sources) >= 2 or len(exact) >= 3):
        classification = "oncogenic"
        rationale.insert(0, f"oncogenic: {len(exact)} accepted exact-variant record(s) from {len(exact_sources)} source(s) ({', '.join(exact_sources)})")
    elif exact or codon:
        classification = "likely_oncogenic"
        rationale.insert(0, f"likely oncogenic: {len(exact)} exact-variant and {len(codon)} codon-level accepted supportive record(s)")
    elif benign:
        bsources = {r.source_name for r in benign if r.variant_match == MatchSpecificity.EXACT_VARIANT}
        classification = "benign" if len(bsources) >= 2 else "likely_benign"
        rationale.insert(0, f"{classification}: accepted exact-variant benign classification from {len(bsources)} source(s), no supportive record")
    else:
        classification = "uncertain_significance"
        gene_level = [r for r in supportive if r.variant_match not in (MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON)]
        if gene_level:
            rationale.insert(0, f"uncertain: accepted evidence exists only at gene level ({len(gene_level)} record(s)); not variant-specific")
        else:
            rationale.insert(0, "uncertain: no accepted variant- or codon-level curated evidence")
    for key, value in sorted(alteration.annotations.items()):
        rationale.append(f"reported by upstream (not used as evidence): {key}={value}")
    return OncogenicityAssessment(classification=classification, criteria_met=criteria, rationale=rationale, evidence_ids=used)


# --- actionability ---------------------------------------------------------------

def _therapy_text(rec: EvidenceRecord) -> list[str]:
    return [f"{d} ({_disease_text(rec)}; {rec.evidence_id})" for d in rec.drugs]


def assess_actionability(es: EvidenceSet) -> ActionabilityAssessment:
    accepted = es.accepted()
    clinical = [r for r in accepted if r.evidence_category in CLINICAL_CATEGORIES and r.direction == EvidenceDirection.SUPPORTS]
    if not _curated_queried_ok(es):
        return ActionabilityAssessment(tier="not_assessed", level="not_assessed",
                                       rationale=["no curated source could be queried; actionability not assessed (missing evidence, not negative)"])
    if not clinical:
        return ActionabilityAssessment(tier="IV", level="not_assessed", rationale=["curated sources queried; no accepted predictive, prognostic or diagnostic record applies"])
    tiered: list[tuple[str, bool, str, EvidenceRecord]] = []
    for r in clinical:
        tier, cross, reason = actionability_tier_for(r.disease_match, r.source_native_level, r.variant_match)
        tiered.append((tier, cross, reason, r))
    tiered.sort(key=lambda t: (TIER_RANK[t[0]], t[3].evidence_id))
    best_tier, best_cross, _, best_rec = tiered[0]
    rationale: list[str] = []
    for tier, _cross, reason, r in tiered:
        rationale.append(f"tier {tier} candidate: {_label(r.source_name)} {r.evidence_category.value} level {r.source_native_level or 'n/a'}, "
                         f"{_disease_text(r)}; {reason} {_cite([r.evidence_id])}")
    therapies: list[str] = []
    resistance: list[str] = []
    for r in clinical:
        if r.evidence_category != EvidenceCategory.PREDICTIVE:
            continue
        sig = es.significance.get(r.evidence_id, "")
        target = resistance if sig in RESISTANCE_SIGNIFICANCE else therapies
        for item in _therapy_text(r):
            if item not in target:
                target.append(item)
    same_dz = [c for c in es.conflicts if c.same_disease]
    cross_dz = [c for c in es.conflicts if not c.same_disease]
    if same_dz:
        rationale.append("conflicting accepted records within one source disease: " + "; ".join(c.description for c in same_dz))
    if cross_dz:
        rationale.append(f"{len(cross_dz)} opposite-direction pair(s) across different source diseases (expected disease-specific "
                         f"divergence, listed in the evidence object, not counted as conflicts)")
    for r in accepted:
        if r.source_name == "clinvar" and "clinical impact" in r.assertion and r.evidence_category == EvidenceCategory.OTHER:
            rationale.append(f"ClinVar somatic clinical impact classification as submitted: '{r.source_native_status}'; "
                             f"not used for SomaWeave tiering (no structured drug/disease context) {_cite([r.evidence_id])}")
    return ActionabilityAssessment(
        tier=best_tier, level=amp_level_for(best_rec.source_native_level), disease_match=best_rec.disease_match,
        therapies=therapies, resistance_to=resistance, rationale=rationale,
        evidence_ids=[r.evidence_id for _, _, _, r in tiered], cross_cancer_extrapolation=best_cross,
    )


# --- relevance ---------------------------------------------------------------

def assess_relevance(normalized_case: NormalizedCase, alteration: Alteration, es: EvidenceSet,
                     actionability: ActionabilityAssessment) -> CaseRelevance:
    case = normalized_case.case
    rationale: list[str] = []
    treatment_context: list[str] = []
    unresolved: list[str] = []
    specimen_ids = [m.specimen_id for m in alteration.measurements if case.specimen(m.specimen_id).role == SpecimenRole.TUMOR]
    specimens = [case.specimen(s) for s in specimen_ids]

    for sp in specimens:
        if sp.is_metastatic_site is True:
            rationale.append(f"specimen {sp.specimen_id} is from a metastatic site ({sp.anatomical_site or 'site not recorded'}); findings describe metastatic disease, not the primary")
        elif sp.is_metastatic_site is False:
            rationale.append(f"specimen {sp.specimen_id} is from the primary site ({sp.anatomical_site or 'site not recorded'})")
        else:
            unresolved.append(f"specimen {sp.specimen_id}: metastatic vs primary site not recorded")
        if sp.purity is None:
            unresolved.append(f"specimen {sp.specimen_id}: no purity estimate; allele-fraction context cannot be constrained")
        elif sp.purity.fit_ambiguous:
            unresolved.append(f"specimen {sp.specimen_id}: molecular purity fit reported as ambiguous")
        elif sp.purity.molecular_fit is None and sp.purity.pathology_min is None:
            unresolved.append(f"specimen {sp.specimen_id}: purity fields present but empty")

    accepted = es.accepted()
    predictive = [r for r in accepted if r.evidence_category == EvidenceCategory.PREDICTIVE and r.drugs]
    linked_ids: list[str] = []
    for sp in specimens:
        for exp in specimen_chronology(case, sp.specimen_id):
            agents = {a.lower() for a in exp.agents} | {exp.name.lower()}
            hits = [r for r in predictive if any(d.lower() in agents for d in r.drugs)]
            if exp.relation == "unknown_dates":
                unresolved.append(f"treatment {exp.treatment_id} ({exp.name}): chronology relative to {sp.specimen_id} unknown ({exp.note or 'dates missing'})")
            if not hits:
                continue
            ids = [r.evidence_id for r in hits]
            linked_ids.extend(ids)
            if exp.relation == "before_specimen":
                treatment_context.append(f"variant detected in {sp.specimen_id} {exp.days_end_to_collection} days after the end of {exp.name} "
                                         f"({', '.join(exp.agents)}); predictive evidence concerns these agents {_cite(ids)}")
            elif exp.relation == "ongoing_at_collection":
                treatment_context.append(f"variant detected in {sp.specimen_id} while on {exp.name} ({', '.join(exp.agents)}), started "
                                         f"{exp.days_start_to_collection} days earlier; predictive evidence concerns these agents {_cite(ids)}")
            elif exp.relation == "after_specimen":
                treatment_context.append(f"{exp.name} started after collection of {sp.specimen_id}; predictive evidence concerns these agents {_cite(ids)}")
            else:
                treatment_context.append(f"{exp.name}: chronology unknown; predictive evidence concerns these agents {_cite(ids)}")
    if not case.treatments:
        unresolved.append("no treatments recorded; treatment chronology cannot be evaluated")

    dz = normalized_case.disease
    for h in dz.hypotheses:
        label = h.oncotree_code or h.name
        diff = [eid for eid, m in es.hypothesis_disease_matches.items()
                if m.get(label) in (DiseaseMatch.SAME, DiseaseMatch.PARENT) and es.record(eid).disease_match not in (DiseaseMatch.SAME, DiseaseMatch.PARENT)]
        if diff:
            unresolved.append(f"disease hypothesis {label} ({h.name}) would change the disease match of {len(diff)} record(s) {_cite(diff)}; pathology reconciliation required")
        else:
            unresolved.append(f"disease hypothesis {label} ({h.name}) is unconfirmed; no retrieved record changes match under it")
    if dz.has_conflicts():
        unresolved.append("recorded diagnosis carries a morphology/OncoTree conflict flag; disease-specific conclusions depend on its resolution")

    curated_ok = _curated_queried_ok(es)
    same_gene_level = [r for r in accepted if r.evidence_category in CLINICAL_CATEGORIES and r.disease_match in (DiseaseMatch.SAME, DiseaseMatch.PARENT)
                       and r.variant_match not in (MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON)]
    if not curated_ok:
        level = "not_assessable"
        rationale.append("curated sources missing; relevance not assessable")
    elif actionability.tier in ("I", "II"):
        level = "high"
        rationale.append(f"tier {actionability.tier} evidence in the confirmed or parent disease {_cite(actionability.evidence_ids[:1])}")
    elif actionability.tier == "III" and (linked_ids or same_gene_level):
        level = "moderate"
        if linked_ids:
            rationale.append(f"tier III evidence concerns agents in the recorded treatment history {_cite(sorted(set(linked_ids)))}")
        if same_gene_level:
            rationale.append(f"same-disease evidence available at gene level only {_cite([r.evidence_id for r in same_gene_level])}")
    elif actionability.tier == "III":
        level = "low"
        rationale.append(f"only cross-cancer or unresolved-disease evidence; no link to recorded treatments {_cite(actionability.evidence_ids)}")
    else:
        level = "none"
        rationale.append("curated sources queried; no accepted evidence applies to this case")
    return CaseRelevance(level=level, rationale=rationale, treatment_context=treatment_context, unresolved_questions=unresolved)


# --- claims, hypotheses, limitations ---------------------------------------------------------------

def _claim_sentences(es: EvidenceSet) -> list[str]:
    groups: dict[tuple, list[EvidenceRecord]] = {}
    for r in es.accepted():
        key = (r.source_name, r.evidence_category.value, r.direction.value, es.significance.get(r.evidence_id, ""),
               r.disease.name if r.disease else "unspecified disease", r.disease_match.value, r.source_native_level or "",
               r.variant_match.value, tuple(sorted(r.drugs)))
        groups.setdefault(key, []).append(r)
    out: list[str] = []
    for key in sorted(groups, key=lambda k: (k[0], k[1], k[4], k[2])):
        src, cat, direction, sig, disease, dm, level, vm, drugs = key
        recs = groups[key]
        if src == "clinvar":
            text = recs[0].assertion if recs[0].assertion.startswith("ClinVar") else f"ClinVar {recs[0].assertion}"
            out.append(f"{text} (review status: {level or 'n/a'}; variant match {vm}; submitted classification, not a SomaWeave tier) {_cite([r.evidence_id for r in recs])}")
            continue
        verb = "supports" if direction == "supports" else ("does not support" if direction == "does_not_support" else "reports")
        what = f"{cat} significance {sig.lower().replace('_', ' ')}" if sig else f"{cat} association"
        drug_txt = f" with {', '.join(drugs)}" if drugs else ""
        out.append(f"{_label(src)} accepted evidence (level {level or 'n/a'}, variant match {vm}) {verb} {what}{drug_txt} in {disease} "
                   f"({dm} relative to the confirmed diagnosis) {_cite([r.evidence_id for r in recs])}")
    return out


def _hypothesis_sentences(es: EvidenceSet) -> list[str]:
    acc = set(es.accepted_ids)
    out: list[str] = []
    submitted = [r for r in es.records if r.evidence_id not in acc and r.source_name != "europepmc"]
    for r in submitted:
        sig = es.significance.get(r.evidence_id)
        drug_txt = f" with {', '.join(r.drugs)}" if r.drugs else ""
        out.append(f"{_label(r.source_name)} non-accepted item ({(r.source_native_status or 'status n/a').split(';')[0]}; level {r.source_native_level or 'n/a'}) "
                   f"{r.direction.value.replace('_', ' ')} {r.evidence_category.value} {sig.lower().replace('_', ' ') if sig else ''}{drug_txt} in "
                   f"{_disease_text(r)} {_cite([r.evidence_id])} [hypothesis]")
    lit: dict[str, list[EvidenceRecord]] = {}
    for r in es.records:
        if r.source_name == "europepmc":
            lit.setdefault(r.query_tier.value, []).append(r)
    for tier, recs in lit.items():
        out.append(f"{len(recs)} Europe PMC literature hit(s) at the {tier} tier (text match, not curated; article content not assessed) "
                   f"{_cite([r.evidence_id for r in recs])} [hypothesis]")
    for c in es.conflicts:
        kind = "conflict between accepted records" if c.same_disease else "cross-disease disagreement between accepted records"
        out.append(f"{kind}: {c.description} {_cite(c.evidence_ids)} [hypothesis]")
    return out


def interpret(normalized_case: NormalizedCase, alteration: Alteration, technical_assessments: list[AnalyticalReliability],
              evidence_set: EvidenceSet) -> FindingAssessment:
    """Assess one alteration along four independent axes; see module and rules docstrings."""
    if evidence_set.alteration_id != alteration.alteration_id:
        raise ValueError(f"evidence set is for {evidence_set.alteration_id}, not {alteration.alteration_id}")
    analytical = assess_analytical(alteration, technical_assessments)
    oncogenicity = assess_oncogenicity(alteration, evidence_set)
    actionability = assess_actionability(evidence_set)
    relevance = assess_relevance(normalized_case, alteration, evidence_set, actionability)

    limitations: list[str] = _missing_limitations(evidence_set)
    for s in evidence_set.source_summaries:
        if s.state == "no_records":
            limitations.append(f"{_label(s.source_name)}: queried successfully, no records (tiers {', '.join(s.tiers_no_records)})")
    limitations.extend(evidence_set.notes)
    multi = [r.evidence_id for r in evidence_set.records if any(l.startswith("multiple_conditions") for l in r.limitations)]
    if multi:
        limitations.append(f"record(s) listing multiple conditions were disease-matched on the first condition only {_cite(multi)}")
    limitations.append("computational predictor evidence not assessed")
    if alteration.annotations:
        limitations.append("upstream annotations are quoted as reported and were not used as evidence")
    limitations.append("clonality and LOH are not inferred from VAF; see technical summary for compatible scenarios only")

    review_flags: list[str] = []
    if analytical.level in ("low", "unreliable", "not_assessable"):
        review_flags.append(f"analytical reliability {analytical.level}: {', '.join(analytical.flags) or 'see rationale'}")
    same_dz = [c for c in evidence_set.conflicts if c.same_disease]
    cross_dz = [c for c in evidence_set.conflicts if not c.same_disease]
    if same_dz:
        review_flags.append(f"{len(same_dz)} conflict(s) among accepted records within one source disease"
                            + (f" ({len(cross_dz)} further cross-disease disagreement(s))" if cross_dz else ""))
    if actionability.cross_cancer_extrapolation:
        review_flags.append("best actionability evidence is a cross-cancer extrapolation")
    if actionability.disease_match == DiseaseMatch.UNKNOWN and actionability.tier != "IV" and actionability.tier != "not_assessed":
        review_flags.append("disease match of the best actionability record is unresolved")
    if normalized_case.disease.has_conflicts() or normalized_case.disease.hypotheses:
        review_flags.append("diagnosis has unresolved hypotheses or conflict flags")
    if evidence_set.missing_sources():
        review_flags.append("one or more curated sources missing: " + ", ".join(_label(s.source_name) for s in evidence_set.missing_sources()))

    return FindingAssessment(
        alteration_id=alteration.alteration_id, analytical=analytical, oncogenicity=oncogenicity, actionability=actionability,
        relevance=relevance, established_claims=_claim_sentences(evidence_set), hypotheses=_hypothesis_sentences(evidence_set),
        limitations=limitations, review_flags=review_flags, evidence_ids=[r.evidence_id for r in evidence_set.records],
    )
