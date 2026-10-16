"""ClinVar adapter tests against recorded E-utilities responses (no network)."""

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from somaweave.domain import EvidenceCategory, MatchSpecificity, SourceStatus
from somaweave.domain.io import load_case
from somaweave.providers import ClinVarProvider, ProviderConfig, ScriptedTransport, TransportResponse
from somaweave.providers.clinvar import GERMLINE_LIMITATION, NCBI_RATE_WITHOUT_KEY
from somaweave.retrieval import build_query_plan

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "providers"
CFG = ProviderConfig(base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils", rate_limit_per_s=1000, api_key_env="SW_TEST_NCBI_KEY")


def _plan():
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    return {it.tier: it for it in build_query_plan(case, case.alterations[0])}


class ClinVarProviderTests(unittest.TestCase):
    def test_search_term_only_for_exact_tier(self):
        plan = _plan()
        self.assertEqual(ClinVarProvider.search_term(plan[MatchSpecificity.EXACT_VARIANT]), "CTNNB1[gene] AND D32N")
        self.assertIsNone(ClinVarProvider.search_term(plan[MatchSpecificity.CODON]))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_NCBI_KEY", None)
            res, _ = ClinVarProvider(CFG, transport=ScriptedTransport([])).query(plan[MatchSpecificity.GENE])
        self.assertEqual(res.status, SourceStatus.NOT_SUPPORTED)

    def test_rate_capped_without_key(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_NCBI_KEY", None)
            p = ClinVarProvider(CFG, transport=ScriptedTransport([]))
            self.assertEqual(p.config.rate_limit_per_s, NCBI_RATE_WITHOUT_KEY)
        with mock.patch.dict(os.environ, {"SW_TEST_NCBI_KEY": "k"}):
            p = ClinVarProvider(CFG, transport=ScriptedTransport([]))
            self.assertEqual(p.config.rate_limit_per_s, 1000)

    def test_recorded_d32n_maps_classification_blocks(self):
        st = ScriptedTransport.from_fixture(FIX / "clinvar_exact_ctnnb1_d32n.json")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_NCBI_KEY", None)
            res, recs = ClinVarProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(len(st.requests), 2)
        self.assertTrue(st.requests[0].url.endswith("/esearch.fcgi"))
        self.assertEqual(st.requests[0].params["term"], "CTNNB1[gene] AND D32N")
        self.assertNotIn("api_key", st.requests[0].params)
        self.assertTrue(st.requests[1].url.endswith("/esummary.fcgi"))
        self.assertEqual(st.requests[1].params["id"], "376228")
        self.assertTrue(res.source_version.startswith("retrieved:"))
        by_native = {r.source_native_id: r for r in recs}
        self.assertEqual(set(by_native), {"VCV000376228#germline_classification", "VCV000376228#clinical_impact_classification"},
                         "oncogenicity block is empty in the record and must not produce a record")
        germ = by_native["VCV000376228#germline_classification"]
        self.assertEqual(germ.evidence_id, "clinvar:VCV000376228:germline")
        self.assertEqual(germ.evidence_category, EvidenceCategory.OTHER)
        self.assertIn(GERMLINE_LIMITATION, germ.limitations)
        self.assertEqual(germ.source_native_status, "Pathogenic")
        self.assertEqual(germ.source_native_level, "criteria provided, single submitter")
        self.assertEqual(germ.variant_match, MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(germ.variant_description, "NM_001904.4(CTNNB1):c.94G>A (p.Asp32Asn)")
        self.assertEqual(germ.gene_symbol, "CTNNB1")
        somatic = by_native["VCV000376228#clinical_impact_classification"]
        self.assertEqual(somatic.source_native_status, "Tier I - Strong")
        self.assertNotIn(GERMLINE_LIMITATION, somatic.limitations)
        self.assertIn("multiple_conditions:3", somatic.limitations)
        self.assertEqual(somatic.disease.name, "Adamantinous craniopharyngioma")
        self.assertIn("MONDO", somatic.disease.other_identifiers)
        self.assertFalse(any(r.is_hypothesis for r in recs))

    def test_oncogenicity_block_maps_to_oncogenic(self):
        search = {"esearchresult": {"count": "1", "idlist": ["1"]}}
        summary = {"result": {"uids": ["1"], "1": {"uid": "1", "accession": "VCV000000001", "title": "NM_x(KRAS):c.35G>A (p.Gly12Asp)",
                   "protein_change": "G12D", "genes": [{"symbol": "KRAS"}],
                   "oncogenicity_classification": {"description": "Oncogenic", "review_status": "criteria provided, single submitter",
                                                    "trait_set": [{"trait_name": "Pancreatic adenocarcinoma"}]}}}}
        st = ScriptedTransport([TransportResponse(status_code=200, text=json.dumps(search)), TransportResponse(status_code=200, text=json.dumps(summary))])
        item = _plan()[MatchSpecificity.EXACT_VARIANT].model_copy(update={"terms": {"gene": "KRAS", "protein_change": "G12D", "variant_terms": ["G12D", "p.Gly12Asp"]}})
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_NCBI_KEY", None)
            res, recs = ClinVarProvider(CFG, transport=st).query(item)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].evidence_category, EvidenceCategory.ONCOGENIC)
        self.assertEqual(recs[0].variant_match, MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(recs[0].limitations, [])

    def test_non_matching_title_downgrades_variant_match(self):
        search = {"esearchresult": {"count": "1", "idlist": ["2"]}}
        summary = {"result": {"uids": ["2"], "2": {"uid": "2", "accession": "VCV000000002", "title": "NM_x(KRAS):c.34G>T (p.Gly12Cys)",
                   "protein_change": "G12C", "genes": [{"symbol": "KRAS"}],
                   "germline_classification": {"description": "Pathogenic", "review_status": "no assertion criteria provided", "trait_set": []}}}}
        st = ScriptedTransport([TransportResponse(status_code=200, text=json.dumps(search)), TransportResponse(status_code=200, text=json.dumps(summary))])
        item = _plan()[MatchSpecificity.EXACT_VARIANT].model_copy(update={"terms": {"gene": "KRAS", "protein_change": "G12D", "variant_terms": ["G12D"]}})
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_NCBI_KEY", None)
            res, recs = ClinVarProvider(CFG, transport=st).query(item)
        self.assertEqual(recs[0].variant_match, MatchSpecificity.GENE)
        self.assertIn("protein_change_not_in_record_title", recs[0].limitations)

    def test_empty_search_is_no_records_with_single_request(self):
        st = ScriptedTransport([TransportResponse(status_code=200, text=json.dumps({"esearchresult": {"count": "0", "idlist": []}}))])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_NCBI_KEY", None)
            res, recs = ClinVarProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.NO_RECORDS)
        self.assertEqual(len(st.requests), 1)
        self.assertEqual(recs, [])

    def test_api_key_sent_but_redacted_from_audit(self):
        st = ScriptedTransport([TransportResponse(status_code=200, text=json.dumps({"esearchresult": {"count": "0", "idlist": []}}))])
        with mock.patch.dict(os.environ, {"SW_TEST_NCBI_KEY": "sekrit-value"}):
            res, _ = ClinVarProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(st.requests[0].params["api_key"], "sekrit-value")
        self.assertNotIn("sekrit-value", res.query.native_request)
        self.assertNotIn("sekrit-value", res.model_dump_json())

    def test_esearch_error_payload_is_error(self):
        st = ScriptedTransport([TransportResponse(status_code=200, text=json.dumps({"esearchresult": {"ERROR": "Invalid db name"}}))])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_NCBI_KEY", None)
            res, _ = ClinVarProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.ERROR)
        self.assertIn("Invalid db name", res.message)


if __name__ == "__main__":
    unittest.main()
