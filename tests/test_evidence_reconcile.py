"""Tests for somaweave.evidence.reconcile (offline, recorded fixtures only)."""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from somaweave.domain import (
    DiseaseMatch,
    EvidenceCategory,
    EvidenceDirection,
    EvidenceRecord,
    MatchSpecificity,
    SourceQuery,
    SourceQueryResult,
    SourceStatus,
)
from somaweave.domain.io import load_case
from somaweave.evidence import civic_significance, coverage_from_results, is_accepted, reconcile
from somaweave.evidence.reconcile import detect_conflicts
from somaweave.normalization import normalize_case
from somaweave.retrieval import RetrievalResult

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "evidence" / "retrieval_ctnnb1_d32n.json"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _case_and_retrieval():
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    rr = RetrievalResult.model_validate_json(FIX.read_text(encoding="utf-8"))
    return case, normalize_case(case), rr


def _rec(eid, source="civic", cat=EvidenceCategory.PREDICTIVE, direction=EvidenceDirection.SUPPORTS, status="accepted; significance=SENSITIVITYRESPONSE",
         drugs=("drugA",), disease="Lung Adenocarcinoma", level="B", vm=MatchSpecificity.EXACT_VARIANT, limitations=()):
    return EvidenceRecord(evidence_id=eid, source_name=source, source_native_id=eid.split(":")[-1], retrieved_at=NOW, query_tier=vm,
                          variant_match=vm, evidence_category=cat, assertion="x", direction=direction, drugs=list(drugs),
                          disease={"name": disease}, source_native_level=level, source_native_status=status, limitations=list(limitations))


def _qr(source, tier, status, n=0):
    return SourceQueryResult(query=SourceQuery(source_name=source, tier=tier), status=status, retrieved_at=NOW, record_count=n,
                             evidence_ids=[f"{source}:{i}" for i in range(n)])


class AcceptanceTests(unittest.TestCase):
    def test_civic_accepted_vs_submitted(self):
        self.assertTrue(is_accepted(_rec("civic:eid:1")))
        self.assertFalse(is_accepted(_rec("civic:eid:2", status="submitted; significance=SENSITIVITYRESPONSE", limitations=["submitted_not_accepted"])))
        self.assertFalse(is_accepted(_rec("civic:eid:3", status="rejected", limitations=["civic_status_rejected"])))

    def test_clinvar_requires_criteria(self):
        self.assertTrue(is_accepted(_rec("clinvar:V1:oncogenicity", source="clinvar", status="Oncogenic", level="criteria provided, single submitter")))
        self.assertFalse(is_accepted(_rec("clinvar:V2:oncogenicity", source="clinvar", status="Oncogenic", level="no assertion criteria provided")))

    def test_literature_never_accepted(self):
        self.assertFalse(is_accepted(_rec("europepmc:MED:1", source="europepmc", status=None, level=None, limitations=["literature_text_match_not_curated"])))

    def test_significance_parse(self):
        self.assertEqual(civic_significance(_rec("civic:eid:1")), "SENSITIVITYRESPONSE")
        self.assertIsNone(civic_significance(_rec("clinvar:V1:x", source="clinvar", status="Oncogenic")))


class CoverageTests(unittest.TestCase):
    def test_three_states_and_missing_never_looks_negative(self):
        results = [
            _qr("civic", MatchSpecificity.EXACT_VARIANT, SourceStatus.NO_RECORDS),
            _qr("civic", MatchSpecificity.GENE, SourceStatus.OK, 2),
            _qr("clinvar", MatchSpecificity.EXACT_VARIANT, SourceStatus.UNAVAILABLE),
            _qr("europepmc", MatchSpecificity.EXACT_VARIANT, SourceStatus.NOT_QUERIED),
            _qr("europepmc", MatchSpecificity.GENE, SourceStatus.NO_RECORDS),
            _qr("civic", MatchSpecificity.PATHWAY, SourceStatus.NOT_SUPPORTED),
        ]
        rows, summaries = coverage_from_results(results)
        states = {(r.source_name, r.tier): r.state for r in rows}
        self.assertEqual(states[("civic", "exact_variant")], "no_records")
        self.assertEqual(states[("civic", "gene")], "ok")
        self.assertEqual(states[("clinvar", "exact_variant")], "missing")
        self.assertEqual(states[("europepmc", "exact_variant")], "missing")
        self.assertEqual(states[("civic", "pathway")], "not_applicable")
        by = {s.source_name: s for s in summaries}
        self.assertEqual(by["civic"].state, "ok")
        self.assertEqual(by["clinvar"].state, "missing")
        self.assertEqual(by["clinvar"].missing_statuses, {"unavailable": 1})
        # europepmc answered one tier but another is missing: partial, with the gap listed
        self.assertEqual(by["europepmc"].state, "no_records")
        self.assertEqual(by["europepmc"].tiers_missing, ["exact_variant"])

    def test_every_missing_status_maps_to_missing(self):
        for st in (SourceStatus.UNAVAILABLE, SourceStatus.ERROR, SourceStatus.NOT_QUERIED, SourceStatus.NO_CREDENTIALS):
            rows, summaries = coverage_from_results([_qr("civic", MatchSpecificity.EXACT_VARIANT, st)])
            self.assertEqual(rows[0].state, "missing", st)
            self.assertEqual(summaries[0].state, "missing", st)


class ConflictTests(unittest.TestCase):
    def test_sensitivity_vs_resistance_same_drug(self):
        a = _rec("civic:eid:1", status="accepted; significance=SENSITIVITYRESPONSE")
        b = _rec("civic:eid:2", status="accepted; significance=RESISTANCE")
        conflicts = detect_conflicts([a, b], {"civic:eid:1": "SENSITIVITYRESPONSE", "civic:eid:2": "RESISTANCE"})
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(sorted(conflicts[0].evidence_ids), ["civic:eid:1", "civic:eid:2"])
        self.assertTrue(conflicts[0].same_disease)

    def test_supports_vs_does_not_support(self):
        a = _rec("civic:eid:1", cat=EvidenceCategory.PROGNOSTIC, drugs=(), status="accepted; significance=POOR_OUTCOME")
        b = _rec("civic:eid:2", cat=EvidenceCategory.PROGNOSTIC, drugs=(), direction=EvidenceDirection.DOES_NOT_SUPPORT,
                 status="accepted; significance=POOR_OUTCOME", disease="Colorectal Cancer")
        conflicts = detect_conflicts([a, b], {"civic:eid:1": "POOR_OUTCOME", "civic:eid:2": "POOR_OUTCOME"})
        self.assertEqual(len(conflicts), 1)
        self.assertFalse(conflicts[0].same_disease)

    def test_different_drugs_do_not_conflict(self):
        a = _rec("civic:eid:1", drugs=("drugA",))
        b = _rec("civic:eid:2", drugs=("drugB",), status="accepted; significance=RESISTANCE")
        self.assertEqual(detect_conflicts([a, b], {"civic:eid:1": "SENSITIVITYRESPONSE", "civic:eid:2": "RESISTANCE"}), [])


class ReconcileFixtureTests(unittest.TestCase):
    def test_reconcile_recorded_retrieval(self):
        case, nc, rr = _case_and_retrieval()
        es = reconcile(nc, case.alterations[0], rr)
        self.assertEqual(es.alteration_id, "A1")
        self.assertEqual(len(es.records), len(rr.evidence))
        # disease labels outside the built-in OncoTree subset stay UNKNOWN, never DIFFERENT
        civic = [r for r in es.records if r.source_name == "civic"]
        self.assertTrue(civic)
        self.assertTrue(all(r.disease_match == DiseaseMatch.UNKNOWN for r in civic))
        self.assertTrue(any("does not resolve" in n for n in es.notes))
        # literature exact-tier hits carry the query disease, not the article's: forced UNKNOWN
        lit_exact = [r for r in es.records if r.source_name == "europepmc" and r.query_tier == MatchSpecificity.EXACT_VARIANT]
        self.assertTrue(lit_exact and all(r.disease_match == DiseaseMatch.UNKNOWN for r in lit_exact))
        # acceptance: CIViC accepted + ClinVar with criteria; submitted and literature excluded
        self.assertIn("civic:eid:2973", es.accepted_ids)
        self.assertIn("clinvar:VCV000376228:clinical", es.accepted_ids)
        self.assertNotIn("civic:eid:12023", es.accepted_ids)
        self.assertFalse(any(e.startswith("europepmc") for e in es.accepted_ids))
        # source-native levels retained verbatim
        self.assertEqual(es.record("civic:eid:12023").source_native_level, "A")
        self.assertEqual(es.record("clinvar:VCV000376228:clinical").source_native_status, "Tier I - Strong")
        # grouping and provenance
        keys = {(g.evidence_category, g.direction) for g in es.groups}
        self.assertIn((EvidenceCategory.DIAGNOSTIC, EvidenceDirection.SUPPORTS), keys)
        prov = es.provenance["civic:eid:9017"]
        self.assertEqual(prov[0].query_tier, "codon")
        self.assertEqual(prov[0].source_name, "civic")
        self.assertIsNotNone(prov[0].native_request)
        # hypotheses evaluated separately
        self.assertEqual(es.hypothesis_labels, ["PAAC"])
        self.assertIn("PAAC", es.hypothesis_disease_matches["civic:eid:2973"])
        # coverage: everything queried ok in this fixture, no missing
        self.assertEqual([s.state for s in es.source_summaries], ["ok", "ok", "ok"])
        self.assertEqual(es.missing_sources(), [])

    def test_alteration_mismatch_rejected(self):
        case, nc, rr = _case_and_retrieval()
        with self.assertRaises(ValueError):
            reconcile(nc, case.alterations[1], rr)

    def test_hypothesis_match_differs_from_confirmed(self):
        case, nc, rr = _case_and_retrieval()
        paac = _rec("civic:eid:999", disease="Acinar Cell Carcinoma of the Pancreas")
        rr2 = rr.model_copy(update={"evidence": list(rr.evidence) + [paac]})
        es = reconcile(nc, case.alterations[0], rr2)
        self.assertEqual(es.record("civic:eid:999").disease_match, DiseaseMatch.RELATED)
        self.assertEqual(es.hypothesis_disease_matches["civic:eid:999"]["PAAC"], DiseaseMatch.SAME)


if __name__ == "__main__":
    unittest.main()
