"""Europe PMC adapter tests against recorded REST responses (no network)."""

import json
import unittest
from pathlib import Path

from somaweave.domain import EvidenceCategory, MatchSpecificity, SourceStatus
from somaweave.domain.io import load_case
from somaweave.providers import EuropePMCProvider, ProviderConfig, ScriptedTransport, TransportResponse
from somaweave.providers.europepmc import LITERATURE_LIMITATION, build_epmc_query
from somaweave.retrieval import build_query_plan

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "providers"
CFG = ProviderConfig(base_url="https://www.ebi.ac.uk/europepmc/webservices/rest/search", rate_limit_per_s=1000, max_records=5)


def _plan():
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    return {it.tier: it for it in build_query_plan(case, case.alterations[0])}


class EuropePMCQueryTests(unittest.TestCase):
    def test_queries_per_tier(self):
        plan = _plan()
        q = {t: build_epmc_query(it) for t, it in plan.items()}
        self.assertEqual(q[MatchSpecificity.EXACT_VARIANT], '"CTNNB1" AND ("D32N" OR "p.D32N" OR "Asp32Asn" OR "p.Asp32Asn" OR "c.94G>A")')
        self.assertEqual(q[MatchSpecificity.CODON], '"CTNNB1" AND ("D32" OR "Asp32" OR "codon 32")')
        self.assertEqual(q[MatchSpecificity.GENE_ALTERATION_CLASS], '"CTNNB1" AND "missense" AND ("Solid pseudopapillary neoplasm of the pancreas")')
        self.assertEqual(q[MatchSpecificity.GENE], '"CTNNB1" AND ("Solid pseudopapillary neoplasm of the pancreas")')
        self.assertEqual(q[MatchSpecificity.PATHWAY], '"WNT pathway" AND ("Solid pseudopapillary neoplasm of the pancreas")')
        self.assertEqual(q[MatchSpecificity.DISEASE_ONLY],
                         '("Solid pseudopapillary neoplasm of the pancreas") AND ("oxaliplatin" OR "irinotecan" OR "leucovorin" OR "fluorouracil") AND ("resistance" OR "response" OR "sensitivity")')

    def test_unformable_query_is_not_supported(self):
        item = _plan()[MatchSpecificity.PATHWAY].model_copy(update={"terms": {"gene": "ZZZ9", "disease": "x"}})
        self.assertIsNone(build_epmc_query(item))
        res, _ = EuropePMCProvider(CFG, transport=ScriptedTransport([])).query(item)
        self.assertEqual(res.status, SourceStatus.NOT_SUPPORTED)


class EuropePMCProviderTests(unittest.TestCase):
    def test_exact_tier_fixture(self):
        st = ScriptedTransport.from_fixture(FIX / "epmc_exact_ctnnb1_d32n.json")
        res, recs = EuropePMCProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(len(recs), 5)
        self.assertIn("total_hits=120", res.message)
        self.assertIn("returned=5", res.message)
        self.assertEqual(res.source_version, "europepmc-api:6.9")
        self.assertEqual(st.requests[0].params["pageSize"], 5)
        self.assertEqual(st.requests[0].params["format"], "json")
        rec = recs[0]
        self.assertEqual(rec.evidence_id, "europepmc:MED:9671767")
        self.assertEqual(rec.variant_match, MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(rec.query_tier, MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(rec.evidence_category, EvidenceCategory.MECHANISTIC)
        self.assertTrue(rec.is_hypothesis)
        self.assertIn(LITERATURE_LIMITATION, rec.limitations)
        self.assertEqual(rec.assertion, rec.citations[0].title)
        cit = rec.citations[0]
        self.assertEqual((cit.pmid, cit.pmcid, cit.doi, cit.year), ("9671767", "PMC21165", "10.1073/pnas.95.15.8847", 1998))
        self.assertEqual(rec.variant_description, "D32N")
        self.assertEqual(rec.disease.name, "Solid pseudopapillary neoplasm of the pancreas")

    def test_gene_class_and_disease_only_fixtures(self):
        plan = _plan()
        st = ScriptedTransport.from_fixture(FIX / "epmc_gene_class_ctnnb1.json")
        res, recs = EuropePMCProvider(CFG, transport=st).query(plan[MatchSpecificity.GENE_ALTERATION_CLASS])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertIn("total_hits=24", res.message)
        self.assertTrue(all(r.variant_match == MatchSpecificity.GENE_ALTERATION_CLASS for r in recs))
        self.assertTrue(all(r.evidence_category == EvidenceCategory.OTHER for r in recs))
        st = ScriptedTransport.from_fixture(FIX / "epmc_disease_only_spn.json")
        res, recs = EuropePMCProvider(CFG, transport=st).query(plan[MatchSpecificity.DISEASE_ONLY])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertIn("total_hits=39", res.message)
        self.assertTrue(all(r.variant_match == MatchSpecificity.DISEASE_ONLY for r in recs))
        self.assertTrue(all("not_gene_specific" in r.limitations for r in recs))
        self.assertTrue(all(r.is_hypothesis for r in recs))

    def test_zero_hits_is_no_records(self):
        st = ScriptedTransport([TransportResponse(status_code=200, text=json.dumps({"version": "6.9", "hitCount": 0, "resultList": {"result": []}}))])
        res, recs = EuropePMCProvider(CFG, transport=st).query(_plan()[MatchSpecificity.CODON])
        self.assertEqual(res.status, SourceStatus.NO_RECORDS)
        self.assertIn("total_hits=0", res.message)
        self.assertEqual(recs, [])

    def test_server_error_is_unavailable(self):
        st = ScriptedTransport([TransportResponse(status_code=503, text="maintenance")])
        res, recs = EuropePMCProvider(CFG, transport=st).query(_plan()[MatchSpecificity.GENE])
        self.assertEqual(res.status, SourceStatus.UNAVAILABLE)
        self.assertEqual(recs, [])


if __name__ == "__main__":
    unittest.main()
