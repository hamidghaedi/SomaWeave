"""Markdown research report rendered from string templates.

Layout: research-use banner, case summary, one section per finding with the
four axes as separate labelled subsections, established claims (each line
ends with its evidence-id citation), hypotheses, evidence table, source
coverage table, limitations and review flags, methods/versions footer.
Claims without a citation are not rendered; they are counted and reported as
a rendering limitation instead so an uncited statement can never appear as a
finding.
"""

from __future__ import annotations

import re
from typing import Any

from somaweave.domain import EvidenceCategory, EvidenceRecord, FindingAssessment
from somaweave.evidence import EvidenceSet
from somaweave.reporting.bundle import RunBundle
from somaweave.reporting.render_json import case_summary

RESEARCH_USE_BANNER = ("**RESEARCH USE ONLY.** This document is an automatically assembled research interpretation. "
                       "It is not a clinical report, has not been reviewed by a qualified professional, and must not be used "
                       "for patient management without expert review.")

CITATION_RE = re.compile(r"\[[^\[\]]+\]\s*$")
AXIS_HEADINGS = {
    "analytical": "Axis 1 - Analytical reliability",
    "oncogenicity": "Axis 2 - Oncogenicity",
    "actionability": "Axis 3 - Actionability (AMP/ASCO/CAP tier)",
    "relevance": "Axis 4 - Case relevance",
}
COVERAGE_LABELS = {"ok": "ok", "no_records": "no_records", "missing": "missing (not queried / unavailable / error / no credentials)",
                   "not_applicable": "not applicable (tier unsupported by source)"}

HEADER = """# SomaWeave research interpretation report

{banner}

- Run id: `{run_id}`
- Generated (UTC): {generated_at}
- SomaWeave version: {version}
- Mode: {mode}
"""

CASE_TEMPLATE = """## Case summary

| Field | Value |
|---|---|
| Case id | {case_id} |
| Assembly | {assembly} |
| Confirmed diagnosis | {diagnosis} |
| OncoTree code | {oncotree} |
| ICD-O morphology | {morphology} |
| Stage | {stage} |
| Disease hypotheses (unconfirmed) | {hypotheses} |
| Specimens | {specimens} |
| Treatments | {treatments} |
| Clinical events | {events} |
| Case notes | {notes} |
"""

FOOTER = """## Methods and versions

- Analytical reliability: `somaweave.technical` level rules (see `qc/technical.json`, field `level_rules`).
- Oncogenicity, actionability and relevance: deterministic rule tables in `somaweave.interpretation.rules`; ClinGen/CGC/VICC tags are approximations from curated-source counts; AMP/ASCO/CAP tiers are gated on OncoTree disease match and source-native level.
- Evidence reconciliation: `somaweave.evidence` (disease matching against the confirmed OncoTree code, acceptance by curation status, conflict detection, per-source coverage).
- A source in state `missing` is missing evidence; it is never treated as negative evidence.
- Clonality and LOH are never inferred from VAF alone.
{versions}
"""


def _cited(line: str) -> bool:
    return bool(CITATION_RE.search(line.strip()))


def _bullets(lines: list[str], empty: str = "- none") -> str:
    return "\n".join(f"- {ln}" for ln in lines) if lines else empty


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _citation_text(rec: EvidenceRecord) -> str:
    if not rec.citations:
        return rec.source_url or ""
    c = rec.citations[0]
    if c.pmid:
        return f"PMID:{c.pmid}"
    if c.doi:
        return f"doi:{c.doi}"
    return c.source_label or c.url or ""


def _evidence_table(es: EvidenceSet) -> str:
    rows = ["| Evidence id | Source | Query tier / variant match | Disease (match) | Category | Direction | Native level / status | Accepted | Citation |",
            "|---|---|---|---|---|---|---|---|---|"]
    acc = set(es.accepted_ids)
    for r in es.records:
        disease = f"{r.disease.name if r.disease else '-'} ({r.disease_match.value})"
        status = r.source_native_status or ""
        level = f"{r.source_native_level or '-'} / {status}" if status else (r.source_native_level or "-")
        rows.append("| " + " | ".join(_cell(x) for x in (
            r.evidence_id, r.source_name, f"{r.query_tier.value} / {r.variant_match.value}", disease, r.evidence_category.value,
            r.direction.value, level, "yes" if r.evidence_id in acc else "no", _citation_text(r))) + " |")
    if len(rows) == 2:
        rows.append("| (no records retrieved) | | | | | | | | |")
    return "\n".join(rows)


TRIAL_LISTING_CLASSES = frozenset({"oncogenic", "likely_oncogenic"})


def _trials_block(es: EvidenceSet, fa: FindingAssessment | None = None) -> str:
    """Clinical-trial registry entries (category ``trial``): context listed verbatim, never evidence.

    The registry search is gene-level text matching, so a variant of uncertain
    significance in a well-known gene retrieves every trial for that gene.
    Trials are therefore listed only when the oncogenicity axis is oncogenic or
    likely oncogenic; otherwise the count is stated and the records stay in the
    evidence JSON. This is a presentation rule and changes no axis.
    """
    trials = [r for r in es.records if r.evidence_category == EvidenceCategory.TRIAL]
    if not trials:
        queried = any(c.source_name == "tooluniverse" for c in es.coverage)
        return "- none retrieved" if queried else "- not queried"
    onc = fa.oncogenicity.classification if fa is not None else None
    if onc is not None and onc not in TRIAL_LISTING_CLASSES:
        return (f"- {len(trials)} registry match(es) retrieved on the gene symbol but not listed: oncogenicity is "
                f"{onc.replace('_', ' ')}, so gene-level trial matching is not informative for this variant; records remain in the evidence JSON")
    lines = []
    for r in trials:
        phases = f" {r.source_native_level}" if r.source_native_level else ""
        drugs = "; ".join(r.drugs) if r.drugs else "interventions not listed"
        conds = "; ".join(c.name for c in r.conditions[:4]) if r.conditions else "conditions not listed"
        via = f"; matched at {r.source_native_rating}" if r.source_native_rating else ""
        lines.append(f"- {r.source_native_id} ({r.source_native_status or 'status unknown'}{phases}{via}): {drugs} — {conds} [{r.evidence_id}]")
    lines.append("- Registry matches on gene symbol plus a condition term (diagnosis, OncoTree node, lineage or tumour-class basket, as stated per line); eligibility was not evaluated and no tier is derived")
    return "\n".join(lines)


def _coverage_table(es: EvidenceSet) -> str:
    rows = ["| Source | Tier | State | Status | Records | Note |", "|---|---|---|---|---|---|"]
    for c in es.coverage:
        state = "not applicable (tier not emitted by planner)" if c.source_name == "planner" else COVERAGE_LABELS.get(c.state, c.state)
        rows.append("| " + " | ".join(_cell(x) for x in (
            c.source_name, c.tier, state, c.status.value, c.record_count, (c.message or "")[:160])) + " |")
    summary = ["", "| Source | Overall | Tiers ok | Tiers no_records | Tiers missing |", "|---|---|---|---|---|"]
    for s in es.source_summaries:
        if s.source_name == "planner":
            continue
        summary.append("| " + " | ".join(_cell(x) for x in (
            s.source_name, s.state, ", ".join(s.tiers_ok) or "-", ", ".join(s.tiers_no_records) or "-", ", ".join(s.tiers_missing) or "-")) + " |")
    return "\n".join(rows + summary)


def _axis_block(fa: FindingAssessment) -> str:
    a, o, t, rlv = fa.analytical, fa.oncogenicity, fa.actionability, fa.relevance
    parts = [
        f"#### {AXIS_HEADINGS['analytical']}",
        f"- Level: **{a.level}**" + (f" (specimen {a.specimen_id})" if a.specimen_id else ""),
        f"- Flags: {', '.join(a.flags) or 'none'}",
        "- Rationale:",
        "\n".join(f"  - {x}" for x in a.rationale),
        "",
        f"#### {AXIS_HEADINGS['oncogenicity']}",
        f"- Classification: **{o.classification}**",
        f"- Criteria tags (approximations): {', '.join(o.criteria_met) or 'none'}",
        "- Rationale:",
        "\n".join(f"  - {x}" for x in o.rationale),
        "",
        f"#### {AXIS_HEADINGS['actionability']}",
        f"- Tier: **{t.tier}**; level: {t.level}; disease match of best record: {t.disease_match.value}; cross-cancer extrapolation: {t.cross_cancer_extrapolation}",
        f"- Therapies named by variant-matched accepted predictive evidence: {'; '.join(t.therapies) or 'none'}",
        f"- Resistance named by variant-matched accepted predictive evidence: {'; '.join(t.resistance_to) or 'none'}",
        "- Rationale:",
        "\n".join(f"  - {x}" for x in t.rationale) or "  - none",
        "",
        f"#### {AXIS_HEADINGS['relevance']}",
        f"- Level: **{rlv.level}**",
        "- Rationale:",
        "\n".join(f"  - {x}" for x in rlv.rationale) or "  - none",
        "- Treatment context:",
        "\n".join(f"  - {x}" for x in rlv.treatment_context) or "  - none",
        "- Unresolved questions:",
        "\n".join(f"  - {x}" for x in rlv.unresolved_questions) or "  - none",
    ]
    return "\n".join(parts)


def _finding_section(bundle: RunBundle, fa: FindingAssessment) -> tuple[str, int]:
    alt = next(a for a in bundle.case.case.alterations if a.alteration_id == fa.alteration_id)
    es = bundle.evidence_set(fa.alteration_id)
    cited_claims = [c for c in fa.established_claims if _cited(c)]
    dropped = len(fa.established_claims) - len(cited_claims)
    hyps = [h for h in fa.hypotheses if _cited(h)]
    dropped += len(fa.hypotheses) - len(hyps)
    title = " ".join(x for x in (alt.gene_symbol, alt.hgvs_p or alt.hgvs_c or alt.copy_number_call, f"({alt.alteration_type.value})") if x)
    limitations = list(fa.limitations)
    if dropped:
        limitations.append(f"{dropped} statement(s) without an evidence citation were withheld from this report")
    excluded = dict(getattr(es, "excluded_by_class", {}) or {})
    excluded_line = (f"- Accepted records excluded as not applicable to this alteration class: "
                     + ", ".join(f"{k} {v}" for k, v in sorted(excluded.items())) if excluded else
                     "- Accepted records excluded as not applicable to this alteration class: none")
    body = [
        f"## Finding {fa.alteration_id}: {title}",
        "",
        f"- Transcript: {alt.transcript or 'n/a'}; coding: {alt.hgvs_c or 'n/a'}; consequence: {alt.consequence or 'n/a'}"
        + (f"; consequence class: {alt.consequence_class()}" if alt.consequence_class() else ""),
        f"- Recorded exon: {alt.exon or 'not recorded'} / {alt.exon_count or 'not recorded'}; region source: {alt.region_source or 'not recorded'}",
        f"- Upstream annotations as reported (not used as evidence): {', '.join(f'{k}={v}' for k, v in alt.annotations.items()) or 'none'}",
        excluded_line,
        "",
        _axis_block(fa),
        "",
        "#### Established claims",
        _bullets(cited_claims, "- none (no accepted curated evidence with a citation)"),
        "",
        "#### Hypotheses and non-curated signals",
        _bullets(hyps),
        "",
        "#### Evidence table",
        _evidence_table(es),
        "",
        "#### Clinical trials (registry search; context only)",
        _trials_block(es, fa),
        "",
        "#### Source coverage",
        _coverage_table(es),
        "",
        "#### Limitations",
        _bullets(limitations),
        "",
        "#### Review flags",
        _bullets(fa.review_flags),
        "",
    ]
    return "\n".join(body), dropped


def render_markdown(run_bundle: RunBundle) -> str:
    """Render the Markdown research report for a run bundle."""
    cs = case_summary(run_bundle)
    header = HEADER.format(banner=RESEARCH_USE_BANNER, run_id=run_bundle.run_id, generated_at=run_bundle.generated_at.isoformat(),
                           version=run_bundle.somaweave_version, mode="offline (no sources queried)" if run_bundle.offline else "online")
    dz = cs["diagnosis"]
    case_block = CASE_TEMPLATE.format(
        case_id=_cell(cs["case_id"]), assembly=cs["assembly"], diagnosis=_cell(dz["name"]),
        oncotree=("not recorded in the confirmed diagnosis" if not dz["oncotree_code"]
                  else dz["oncotree_code"] + ("" if dz["code_in_table"] else " (code not found in the OncoTree table)")),
        morphology=_cell(dz["icd_o_morphology"] or "n/a"), stage=_cell(dz["stage"] or "n/a"),
        hypotheses=_cell("; ".join(f"{h['label']} ({h['relation_to_confirmed']})" for h in cs["disease_hypotheses"]) or "none"),
        specimens=_cell("; ".join(
            f"{s['specimen_id']} {s['role']} {s['preservation']} {s['anatomical_site'] or ''}".strip()
            + (f" collected {s['collection_date']}" if s.get("collection_date") else "")
            + (f" stored {s['storage']}" if s.get('storage') else '')
            + (f" [note: {s['notes']}]" if s.get("notes") else "") for s in cs["specimens"])),
        treatments=_cell("; ".join(
            f"{t['name']} ({t['start_date'] or '?'} to {t['end_date'] or ('ongoing' if t['ongoing'] else '?')})"
            + (f" [{t['modality']}]" if t.get('modality') else '')
            + (f" [note: {t['notes']}]" if t.get('notes') else '')
            + (f" [note: {t['response_notes']}]" if t.get("response_notes") else "") for t in cs["treatments"]) or "none"),
        events=_cell("; ".join(f"{e['event_type']} {e['event_date'] or '?'}" + (f" ({e['site']})" if e.get("site") else "")
                               + (f" - {e['description']}" if e.get("description") else "") for e in cs.get("clinical_events", [])) or "none"),
        notes=_cell(cs.get("case_notes") or "none"),
    )
    flags = [f"{f['severity']}: {f['message']}" for f in cs["disease_flags"] if f["severity"] != "info"]
    hyp_lines = []
    for h in cs["disease_hypotheses"]:
        line = f"hypothesis {h['label']} ({h['name']}; relation to confirmed diagnosis: {h['relation_to_confirmed']}; proposed by {h.get('proposed_by') or 'n/a'})"
        if h.get("rationale"):
            line += f": {h['rationale']}"
        hyp_lines.append(line)
    flags_block = ""
    if flags or hyp_lines:
        flags_block = "### Diagnosis flags and hypotheses\n\n" + _bullets(flags + hyp_lines) + "\n"
    sections: list[str] = []
    withheld = 0
    for fa in run_bundle.findings:
        text, dropped = _finding_section(run_bundle, fa)
        sections.append(text)
        withheld += dropped
    prov = run_bundle.provenance
    versions = _bullets([f"{k}: {v}" for k, v in sorted(prov.items()) if isinstance(v, (str, int, float, bool)) and v is not None])
    footer = FOOTER.format(versions=versions)
    if withheld:
        footer += f"\n{withheld} uncited statement(s) were withheld across findings.\n"
    return "\n".join([header, case_block, flags_block, *sections, footer])
