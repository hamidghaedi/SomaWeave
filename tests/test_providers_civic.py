"""CIViC adapter tests against recorded GraphQL responses (no network)."""

import json
import unittest
from pathlib import Path

from somaweave.domain import EvidenceCategory, EvidenceDirection, MatchSpecificity, SourceStatus
from somaweave.domain.io import load_case
from somaweave.providers import CivicProvider, ProviderConfig, ScriptedTransport, TransportResponse
from somaweave.retrieval import build_query_plan

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "providers"
CFG = ProviderConfig(base_url="https://civicdb.org/api/graphql", rate_limit_per_s=1000, max_records=100)


def _plan(hgvs_p=None, hgvs_c=None):
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    alt = case.alterations[0]
    if hgvs_p:
        alt = alt.model_copy(update={"hgvs_p": hgvs_p, "hgvs_c": hgvs_c})
    return {it.tier: it for it in build_query_plan(case, alt)}


class CivicProviderTests(unittest.TestCase):
    def test_profile_name_per_tier(self):
        plan = _plan()
        self.assertEqual(CivicProvider.molecular_profile_name(plan[MatchSpecificity.EXACT_VARIANT]), "CTNNB1 D32N")
        self.assertEqual(CivicProvider.molecular_profile_name(plan[MatchSpecificity.CODON]), "CTNNB1 D32")
        self.assertEqual(CivicProvider.molecular_profile_name(plan[MatchSpecificity.GENE]), "CTNNB1")
        self.assertIsNone(CivicProvider.molecular_profile_name(plan[MatchSpecificity.PATHWAY]))
        p = CivicProvider(CFG, transport=ScriptedTransport([]))
        res, recs = p.query(plan[MatchSpecificity.DISEASE_ONLY])
        self.assertEqual(res.status, SourceStatus.NOT_SUPPORTED)

    def test_exact_variant_without_items_is_no_records(self):
        st = ScriptedTransport.from_fixture(FIX / "civic_exact_ctnnb1_d32n.json")
        res, recs = CivicProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.NO_RECORDS)
        self.assertEqual(recs, [])
        self.assertEqual(res.source_version, "civic-release:01-Oct-2026")
        self.assertIn("CTNNB1 D32N", res.message)
        body = st.requests[0].json_body
        self.assertEqual(body["variables"]["mp"], "CTNNB1 D32N")
        self.assertIn("dataReleases", body["query"])
        self.assertIn("CTNNB1 D32N", res.query.native_request)

    def test_codon_tier_match_is_codon_not_exact(self):
        st = ScriptedTransport.from_fixture(FIX / "civic_codon_ctnnb1_d32.json")
        res, recs = CivicProvider(CFG, transport=st).query(_plan()[MatchSpecificity.CODON])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec.evidence_id, "civic:eid:9017")
        self.assertEqual(rec.source_native_id, "9017")
        self.assertEqual(rec.variant_description, "CTNNB1 D32Y")
        self.assertEqual(rec.query_tier, MatchSpecificity.CODON)
        self.assertEqual(rec.variant_match, MatchSpecificity.CODON)
        self.assertEqual(rec.evidence_category, EvidenceCategory.PROGNOSTIC)
        self.assertEqual(rec.source_native_level, "C")
        self.assertIn("submitted_not_accepted", rec.limitations)
        self.assertTrue(rec.is_hypothesis, "submitted items are not validated biomarkers")
        self.assertEqual(rec.disease.doid, "DOID:0080702")
        self.assertEqual(rec.citations[0].pmid, "19197950")
        self.assertTrue(rec.source_url.startswith("https://civicdb.org/"))

    def test_exact_match_sets_exact_variant_and_hypothesis_flags(self):
        plan = _plan("p.Ser45Phe", "c.134C>T")
        st = ScriptedTransport.from_fixture(FIX / "civic_exact_ctnnb1_s45f.json")
        res, recs = CivicProvider(CFG, transport=st).query(plan[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(res.record_count, 6)
        self.assertTrue(all(r.variant_match == MatchSpecificity.EXACT_VARIANT for r in recs))
        self.assertTrue(all(r.variant_description == "CTNNB1 S45F" for r in recs))
        by_id = {r.evidence_id: r for r in recs}
        accepted_predictive = by_id["civic:eid:6049"]
        self.assertEqual(accepted_predictive.evidence_category, EvidenceCategory.PREDICTIVE)
        self.assertFalse(accepted_predictive.is_hypothesis)
        self.assertEqual(accepted_predictive.limitations, [])
        self.assertTrue(accepted_predictive.source_native_status.startswith("accepted"))
        submitted = by_id["civic:eid:11018"]
        self.assertTrue(submitted.is_hypothesis)
        self.assertIn("submitted_not_accepted", submitted.limitations)
        self.assertEqual({r.evidence_category for r in recs} & {EvidenceCategory.DIAGNOSTIC, EvidenceCategory.PROGNOSTIC},
                         {EvidenceCategory.DIAGNOSTIC, EvidenceCategory.PROGNOSTIC})
        self.assertTrue(all(r.direction in (EvidenceDirection.SUPPORTS, EvidenceDirection.DOES_NOT_SUPPORT) for r in recs))
        self.assertTrue(all(r.source_native_rating is None or r.source_native_rating.isdigit() for r in recs))

    def test_gene_tier_caps_records_and_reports_total(self):
        st = ScriptedTransport.from_fixture(FIX / "civic_gene_ctnnb1.json")
        res, recs = CivicProvider(CFG.model_copy(update={"max_records": 10}), transport=st).query(_plan()[MatchSpecificity.GENE])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(len(recs), 10)
        self.assertIn("43 items available, 10 returned", res.message)
        self.assertTrue(all(r.variant_match == MatchSpecificity.GENE for r in recs))
        complex_profiles = [r for r in recs if " OR " in (r.variant_description or "")]
        for r in complex_profiles:
            self.assertIn("complex_molecular_profile", r.limitations)

    def test_graphql_errors_are_error_status(self):
        st = ScriptedTransport([TransportResponse(status_code=200, text=json.dumps({"errors": [{"message": "Field x doesn't exist"}], "data": None}))])
        res, recs = CivicProvider(CFG, transport=st).query(_plan()[MatchSpecificity.GENE])
        self.assertEqual(res.status, SourceStatus.ERROR)
        self.assertIn("Field x", res.message)
        self.assertEqual(recs, [])

    def test_pagination_follows_cursor_until_cap(self):
        def page(ids, has_next, cursor):
            return TransportResponse(status_code=200, text=json.dumps({"data": {
                "dataReleases": [{"name": "nightly"}, {"name": "01-Jan-2026"}],
                "evidenceItems": {"totalCount": 3, "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                                  "nodes": [{"id": i, "name": f"EID{i}", "status": "ACCEPTED", "evidenceType": "PREDICTIVE",
                                             "evidenceLevel": "B", "evidenceDirection": "SUPPORTS", "significance": "SENSITIVITYRESPONSE",
                                             "evidenceRating": 3, "molecularProfile": {"id": 1, "name": "CTNNB1 X"},
                                             "disease": {"name": "Cancer", "doid": "162"}, "therapies": [{"name": "drugA"}],
                                             "source": {"citationId": "1", "sourceType": "PUBMED", "publicationYear": 2020}} for i in ids]}}}))

        st = ScriptedTransport([page([1, 2], True, "c1"), page([3], False, None)])
        res, recs = CivicProvider(CFG.model_copy(update={"max_records": 100}), transport=st).query(_plan()[MatchSpecificity.GENE])
        self.assertEqual(len(st.requests), 2)
        self.assertEqual(st.requests[1].json_body["variables"]["after"], "c1")
        self.assertEqual([r.evidence_id for r in recs], ["civic:eid:1", "civic:eid:2", "civic:eid:3"])
        self.assertEqual(res.source_version, "civic-release:01-Jan-2026")
        self.assertEqual(recs[0].drugs, ["drugA"])
        self.assertFalse(recs[0].is_hypothesis)


if __name__ == "__main__":
    unittest.main()
