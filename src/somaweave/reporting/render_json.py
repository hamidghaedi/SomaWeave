"""JSON evidence object."""

from __future__ import annotations

from typing import Any

from somaweave.domain.dates import PartialDate
from somaweave.domain.io import dump_model


def _date(value):
    """Render a full or partial date exactly at its recorded precision."""
    p = PartialDate.parse(value)
    return p.isoformat() if p else None
from somaweave.reporting.bundle import RunBundle


def case_summary(bundle: RunBundle) -> dict[str, Any]:
    """Compact, de-identified case summary used by both renderers."""
    case = bundle.case.case
    dz = bundle.case.disease
    return {
        "case_id": case.case_id,
        "assembly": case.assembly.value,
        "diagnosis": {
            "name": dz.confirmed_name, "oncotree_code": dz.confirmed_oncotree_code, "code_in_table": dz.confirmed_code_known,
            "icd_o_morphology": dz.icd_o_morphology, "confirmed_by_pathology": dz.confirmed_by_pathology,
            "stage": case.diagnosis.stage, "primary_site": case.diagnosis.primary_site,
        },
        "disease_hypotheses": [{"label": h.oncotree_code or h.name, "name": h.name, "relation_to_confirmed": h.relation_to_confirmed.value,
                                "proposed_by": h.proposed_by, "rationale": h.rationale} for h in dz.hypotheses],
        "disease_flags": [{"code": f.code, "severity": f.severity, "message": f.message} for f in dz.flags],
        "diagnosis_date": _date(case.diagnosis.diagnosis_date),
        "clinical_events": [{"event_type": e.event_type.value, "event_date": _date(e.event_date), "site": e.site, "description": e.description}
                            for e in case.clinical_events],
        "case_notes": case.notes,
        "specimens": [{"specimen_id": s.specimen_id, "role": s.role.value, "tissue": s.tissue, "anatomical_site": s.anatomical_site,
                       "is_metastatic_site": s.is_metastatic_site, "preservation": s.preservation.value, "assay": s.sequencing_assay,
                       "collection_date": _date(s.collection_date), "notes": s.notes,
                       "purity": dump_model(s.purity) if s.purity else None} for s in case.specimens],
        "treatments": [{"treatment_id": t.treatment_id, "name": t.name, "agents": t.agents, "intent": t.intent,
                        "start_date": _date(t.start_date), "end_date": _date(t.end_date), "ongoing": t.ongoing,
                        "best_response": t.best_response.value if t.best_response else None,
                        "response_notes": t.response_notes} for t in case.treatments],
        "alterations": [{"alteration_id": a.alteration_id, "gene_symbol": a.gene_symbol, "alteration_type": a.alteration_type.value,
                         "hgvs_c": a.hgvs_c, "hgvs_p": a.hgvs_p, "transcript": a.transcript, "consequence": a.consequence,
                         "annotations_as_reported": dict(a.annotations)} for a in case.alterations],
        "normalization_flags": [dump_model(f) for f in bundle.case.flags],
    }


def render_json(run_bundle: RunBundle) -> dict[str, Any]:
    """Full evidence object: summary, findings, records, query results, technical summary, provenance."""
    findings = []
    for fa in run_bundle.findings:
        es = run_bundle.evidence_set(fa.alteration_id)
        findings.append({
            "assessment": dump_model(fa),
            "evidence_records": [dump_model(r) for r in es.records],
            "accepted_ids": list(es.accepted_ids),
            "accepted_all_ids": list(getattr(es, "accepted_all_ids", [])),
            "inapplicable_ids": list(getattr(es, "inapplicable_ids", [])),
            "excluded_by_class": dict(getattr(es, "excluded_by_class", {})),
            "profile_classes": dict(getattr(es, "profile_classes", {})),
            "variant_matched_ids": list(getattr(es, "variant_matched_ids", [])),
            "matched_conditions": dict(getattr(es, "matched_conditions", {})),
            "hypothesis_match_summary": dict(getattr(es, "hypothesis_match_summary", {})),
            "significance": dict(es.significance),
            "hypothesis_disease_matches": {k: {h: m.value for h, m in v.items()} for k, v in es.hypothesis_disease_matches.items()},
            "groups": [dump_model(g) for g in es.groups],
            "conflicts": [dump_model(c) for c in es.conflicts],
            "source_coverage": [dump_model(c) for c in es.coverage],
            "source_summaries": [dump_model(s) for s in es.source_summaries],
            "source_query_results": [dump_model(q) for q in es.query_results],
            "provenance": {k: [dump_model(p) for p in v] for k, v in es.provenance.items()},
            "notes": list(es.notes),
        })
    return {
        "report": "somaweave_interpretation",
        "report_schema_version": "report.v1",
        "research_use_only": True,
        "run_id": run_bundle.run_id,
        "generated_at": run_bundle.generated_at.isoformat(),
        "somaweave_version": run_bundle.somaweave_version,
        "offline": run_bundle.offline,
        "case_summary": case_summary(run_bundle),
        "findings": findings,
        "technical_summary": run_bundle.technical_summary,
        "provenance": run_bundle.provenance,
    }
