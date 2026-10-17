"""OncoKB adapter tests against recorded response bodies (no network, no real token)."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from somaweave.domain import (
    AlterationType,
    DiseaseMatch,
    EvidenceCategory,
    EvidenceDirection,
    MatchSpecificity,
    SourceStatus,
)
from somaweave.domain.io import load_case
from somaweave.evidence import is_accepted
from somaweave.providers import (
    OncoKBConfig,
    OncoKBProvider,
    PayloadCache,
    ProviderConfig,
    ScriptedTransport,
    TransportResponse,
    build_registry,
    load_provider_configs,
)
from somaweave.providers.base import TransportError
from somaweave.retrieval import build_query_plan

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "providers"
DUMMY_TOKEN = "dummy-test-value"
NO_FILE = "/nonexistent/somaweave-oncokb-token"
CFG = OncoKBConfig(base_url="https://www.oncokb.org/api/v1", rate_limit_per_s=1000, token_file=NO_FILE)


def _env_token(value=DUMMY_TOKEN):
    """Patch the token environment variable (set, or removed when ``value`` is None)."""
    if value is None:
        return mock.patch.dict(os.environ, {}, clear=False), ("ONCOKB_API_TOKEN",)
    return mock.patch.dict(os.environ, {"ONCOKB_API_TOKEN": value}, clear=False), ()


class _EnvMixin:
    def with_env(self, value=DUMMY_TOKEN):
        patcher, drop = _env_token(value)
        patcher.start()
        self.addCleanup(patcher.stop)
        for k in drop:
            os.environ.pop(k, None)


def _case():
    return load_case(ROOT / "examples" / "synthetic_case.json")


def _plan(alteration_index=0, hgvs_p=None, drop_tumor_type=False):
    case = _case()
    alt = case.alterations[alteration_index]
    if hgvs_p:
        alt = alt.model_copy(update={"hgvs_p": hgvs_p, "hgvs_c": None})
    items = {it.tier: it for it in build_query_plan(case, alt)}
    if drop_tumor_type:
        it = items[MatchSpecificity.EXACT_VARIANT]
        items[MatchSpecificity.EXACT_VARIANT] = it.model_copy(update={"terms": {k: v for k, v in it.terms.items() if k != "oncotree_code"}})
    return items


def _payload(**overrides):
    base = {
        "query": {"hugoSymbol": "KRAS", "alteration": "G12C", "tumorType": "LUAD", "referenceGenome": "GRCh38"},
        "geneExist": True, "variantExist": True, "alleleExist": True, "hotspot": True, "oncogenic": "Oncogenic",
        "mutationEffect": {"knownEffect": "Gain-of-function", "description": "KRAS G12C locks RAS in the GTP-bound state.",
                           "citations": {"pmids": ["1", "2"], "abstracts": [{"link": "https://example.org/abs", "abstract": "Meeting abstract"}]}},
        "highestSensitiveLevel": "LEVEL_1", "highestResistanceLevel": "LEVEL_R1", "highestDiagnosticImplicationLevel": None,
        "highestPrognosticImplicationLevel": None, "highestFdaLevel": "LEVEL_Fda2",
        "treatments": [
            {"alterations": ["G12C"], "drugs": [{"drugName": "Sotorasib"}], "approvedIndications": ["Sotorasib is FDA-approved for KRAS G12C NSCLC"],
             "level": "LEVEL_1", "fdaLevel": "LEVEL_Fda2", "levelAssociatedCancerType": {"code": "NSCLC", "name": "Non-Small Cell Lung Cancer"},
             "levelExcludedCancerTypes": [], "pmids": ["3"], "abstracts": [], "description": "Sotorasib is approved."},
            {"alterations": ["G12C"], "drugs": [{"drugName": "Cetuximab"}, {"drugName": "Panitumumab"}], "approvedIndications": [],
             "level": "LEVEL_R1", "fdaLevel": None, "levelAssociatedCancerType": {"code": "COADREAD", "name": "Colorectal Adenocarcinoma"},
             "levelExcludedCancerTypes": [], "pmids": ["4"], "abstracts": [], "description": "Resistance to anti-EGFR antibodies."},
            {"alterations": ["Oncogenic Mutations"], "drugs": [{"drugName": "Investigational"}], "approvedIndications": [],
             "level": "LEVEL_4", "fdaLevel": None, "levelAssociatedCancerType": {"code": "", "name": "", "mainType": {"name": "All Solid Tumors"}},
             "levelExcludedCancerTypes": [{"code": "X", "name": "Excluded Type"}], "pmids": [], "abstracts": [], "description": ""},
        ],
        "diagnosticImplications": [{"levelOfEvidence": "LEVEL_Dx1", "alterations": ["G12C"], "tumorType": {"code": "LUAD", "name": "Lung Adenocarcinoma"},
                                    "pmids": ["5"], "abstracts": [], "description": "Diagnostic implication text."}],
        "prognosticImplications": [{"levelOfEvidence": "LEVEL_Px2", "alterations": ["G12"], "tumorType": {"code": "LUAD", "name": "Lung Adenocarcinoma"},
                                    "pmids": [], "abstracts": [], "description": ""}],
        "dataVersion": "v9.9", "lastUpdate": "01/01/2026", "vus": False,
    }
    base.update(overrides)
    return base


def _resp(payload, status=200):
    return TransportResponse(status_code=status, text=json.dumps(payload))


class OncoKBSupportTests(_EnvMixin, unittest.TestCase):
    def test_supports_only_exact_small_variant_items(self):
        plan = _plan()
        self.assertEqual(OncoKBProvider.query_terms(plan[MatchSpecificity.EXACT_VARIANT]),
                         {"gene": "CTNNB1", "alteration": "D32N", "tumor_type": "SPN"})
        for tier in (MatchSpecificity.CODON, MatchSpecificity.GENE, MatchSpecificity.PATHWAY, MatchSpecificity.DISEASE_ONLY):
            self.assertIsNone(OncoKBProvider.query_terms(plan[tier]))
        self.with_env()
        st = ScriptedTransport([])
        res, recs = OncoKBProvider(CFG, transport=st).query(plan[MatchSpecificity.GENE])
        self.assertEqual(res.status, SourceStatus.NOT_SUPPORTED)
        self.assertEqual(st.requests, [])

    def test_non_small_variants_are_not_supported(self):
        case = _case()
        cna = case.alterations[0].model_copy(update={"alteration_type": AlterationType.CNA, "copy_number_call": "amplification", "hgvs_p": "p.Asp32Asn"})
        exact = {it.tier: it for it in build_query_plan(case, cna)}[MatchSpecificity.EXACT_VARIANT]
        self.assertIsNone(OncoKBProvider.query_terms(exact))

    def test_plan_exact_tier_lists_oncokb(self):
        self.assertIn("oncokb", _plan()[MatchSpecificity.EXACT_VARIANT].providers)

    def test_plain_provider_config_is_upgraded(self):
        p = OncoKBProvider(ProviderConfig(base_url="https://www.oncokb.org/api/v1"), transport=ScriptedTransport([]))
        self.assertIsInstance(p.config, OncoKBConfig)
        self.assertEqual(p.config.api_key_env, "ONCOKB_API_TOKEN")
        self.assertEqual(p.config.token_file, "~/.oncokb_token")


class OncoKBCredentialTests(_EnvMixin, unittest.TestCase):
    def test_no_credentials_when_env_and_file_absent(self):
        self.with_env(None)
        st = ScriptedTransport([_resp(_payload())])
        res, recs = OncoKBProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.NO_CREDENTIALS)
        self.assertEqual(res.message, "OncoKB token not configured")
        self.assertEqual(recs, [])
        self.assertEqual(st.requests, [], "no request may be sent without a token")

    def test_token_from_env_goes_only_into_the_header(self):
        self.with_env()
        st = ScriptedTransport.from_fixture(FIX / "oncokb_exact_ctnnb1_d32n_spn.json")
        res, recs = OncoKBProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.OK)
        req = st.requests[0]
        self.assertEqual(req.method, "GET")
        self.assertTrue(req.url.endswith("/annotate/mutations/byProteinChange"))
        self.assertEqual(req.params, {"hugoSymbol": "CTNNB1", "alteration": "D32N", "referenceGenome": "GRCh38", "tumorType": "SPN"})
        self.assertEqual(req.headers["Authorization"], f"Bearer {DUMMY_TOKEN}")
        self.assertNotIn(DUMMY_TOKEN, res.query.native_request)
        self.assertNotIn(DUMMY_TOKEN, json.dumps(res.model_dump(mode="json")))
        self.assertNotIn(DUMMY_TOKEN, json.dumps([r.model_dump(mode="json") for r in recs]))

    def test_token_file_fallback_is_stripped(self):
        self.with_env(None)
        with tempfile.TemporaryDirectory() as d:
            tf = Path(d) / "token"
            tf.write_text(f"  {DUMMY_TOKEN}\n", encoding="utf-8")
            st = ScriptedTransport.from_fixture(FIX / "oncokb_exact_ctnnb1_d32n_spn.json")
            cfg = CFG.model_copy(update={"token_file": str(tf)})
            res, _ = OncoKBProvider(cfg, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
            self.assertEqual(res.status, SourceStatus.OK)
            self.assertEqual(st.requests[0].headers["Authorization"], f"Bearer {DUMMY_TOKEN}")

    def test_401_is_error_with_message_and_no_token(self):
        self.with_env()
        st = ScriptedTransport([TransportResponse(status_code=401, text='{"message":"Unauthorized"}')])
        res, recs = OncoKBProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.ERROR)
        self.assertIn("401", res.message)
        self.assertNotIn(DUMMY_TOKEN, res.message)
        self.assertEqual(recs, [])

    def test_server_error_and_transport_failure_are_unavailable(self):
        self.with_env()
        res, _ = OncoKBProvider(CFG, transport=ScriptedTransport([TransportResponse(status_code=503, text="down")])).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.UNAVAILABLE)
        res, _ = OncoKBProvider(CFG, transport=ScriptedTransport([TransportError("refused")])).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.UNAVAILABLE)


class OncoKBRecordedMappingTests(_EnvMixin, unittest.TestCase):
    def setUp(self):
        self.with_env()

    def test_ctnnb1_d32n_oncogenic_record(self):
        st = ScriptedTransport.from_fixture(FIX / "oncokb_exact_ctnnb1_d32n_spn.json")
        res, recs = OncoKBProvider(CFG, transport=st).query(_plan()[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(res.record_count, 2)
        self.assertEqual(res.source_version, "oncokb-data:v7.6")
        self.assertIn("variantExist=true", res.message)
        rec = recs[0]
        self.assertEqual(rec.evidence_id, "oncokb:CTNNB1:D32N:oncogenic:0")
        self.assertEqual(rec.evidence_category, EvidenceCategory.ONCOGENIC)
        self.assertEqual(rec.direction, EvidenceDirection.SUPPORTS)
        self.assertEqual(rec.variant_match, MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(rec.query_tier, MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(rec.disease_match, DiseaseMatch.UNKNOWN)
        self.assertEqual(rec.source_native_status, "Likely Oncogenic")
        self.assertTrue(rec.assertion.startswith("OncoKB oncogenicity: Likely Oncogenic; mutation effect: Gain-of-function"))
        self.assertEqual(len(rec.citations), 5)
        self.assertTrue(all(c.pmid for c in rec.citations))
        self.assertIn("oncokb_hotspot_flag=true", rec.limitations)
        self.assertIn("highestSensitiveLevel=none", rec.source_native_rating)
        self.assertFalse(rec.is_hypothesis)
        self.assertTrue(is_accepted(rec), "curated OncoKB classification must enter the accepted pool")
        self.assertEqual(rec.source_url, "https://www.oncokb.org/gene/CTNNB1/D32N")

    def test_egfr_g719s_with_tumor_type_spn(self):
        st = ScriptedTransport.from_fixture(FIX / "oncokb_exact_egfr_g719s_spn.json")
        res, recs = OncoKBProvider(CFG, transport=st).query(_plan(1)[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(res.record_count, 11)
        onc = [r for r in recs if r.evidence_category == EvidenceCategory.ONCOGENIC]
        tx = [r for r in recs if r.evidence_category == EvidenceCategory.PREDICTIVE]
        self.assertEqual((len(onc), len(tx)), (1, 9))
        self.assertEqual(onc[0].source_native_status, "Oncogenic")
        self.assertIn("highestSensitiveLevel=LEVEL_3B", onc[0].source_native_rating)
        self.assertEqual({r.source_native_level for r in tx}, {"LEVEL_3B"})
        self.assertTrue(all(r.direction == EvidenceDirection.SUPPORTS for r in tx))
        self.assertTrue(all(r.drugs for r in tx))
        self.assertEqual([r.evidence_id for r in tx], [f"oncokb:EGFR:G719S:treatment:{i}" for i in range(9)])
        # the level is attached to the OncoTree main type (no code); the reconciliation layer decides the disease match
        self.assertTrue(all(r.disease is not None and r.disease.name == "Non-Small Cell Lung Cancer" for r in tx))
        self.assertTrue(all(r.disease.oncotree_code is None for r in tx))
        self.assertTrue(all(r.disease.other_identifiers.get("oncokb_cancer_type_level") == "main_type" for r in tx))
        self.assertTrue(all(r.disease_match == DiseaseMatch.UNKNOWN for r in tx))
        codon = [r for r in tx if r.variant_match == MatchSpecificity.CODON]
        cls = [r for r in tx if r.variant_match == MatchSpecificity.GENE_ALTERATION_CLASS]
        self.assertTrue(codon, "treatments attached to the OncoKB codon alteration G719 are codon-level matches")
        self.assertEqual(len(cls), 1)
        self.assertTrue(all(r.study_design.startswith("OncoKB LEVEL_3B") for r in tx))
        self.assertTrue(all(not r.is_hypothesis for r in tx))

    def test_egfr_g719s_without_tumor_type(self):
        st = ScriptedTransport.from_fixture(FIX / "oncokb_exact_egfr_g719s_no_tumortype.json")
        res, recs = OncoKBProvider(CFG, transport=st).query(_plan(1, drop_tumor_type=True)[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertNotIn("tumorType", st.requests[0].params)
        self.assertIn("queried without tumorType", res.message)
        tx = [r for r in recs if r.evidence_category == EvidenceCategory.PREDICTIVE]
        self.assertEqual({r.source_native_level for r in tx}, {"LEVEL_1", "LEVEL_2", "LEVEL_3A"})
        self.assertTrue(all("queried_without_tumor_type" in r.limitations for r in recs))
        lvl1 = [r for r in tx if r.source_native_level == "LEVEL_1"]
        self.assertTrue(lvl1)
        self.assertEqual(lvl1[0].disease.name, "Non-Small Cell Lung Cancer")
        self.assertIsNone(lvl1[0].disease.oncotree_code)
        self.assertIn("Afatinib", lvl1[0].drugs)
        self.assertTrue(all(r.disease is not None for r in tx))

    def test_nonexistent_alteration_is_no_records_not_negative(self):
        st = ScriptedTransport.from_fixture(FIX / "oncokb_exact_ctnnb1_z999z_spn.json")
        res, recs = OncoKBProvider(CFG, transport=st).query(_plan(hgvs_p="p.Z999Z")[MatchSpecificity.EXACT_VARIANT])
        self.assertEqual(res.status, SourceStatus.NO_RECORDS)
        self.assertEqual(recs, [])
        self.assertIn("variantExist=false", res.message)
        self.assertIn("oncogenic=Unknown", res.message)
        self.assertEqual(res.source_version, "oncokb-data:v7.6")

    def test_fixtures_hold_response_bodies_only(self):
        for path in sorted(FIX.glob("oncokb_*.json")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Authorization", text, path.name)
            self.assertNotIn("Bearer", text, path.name)
            for entry in json.loads(text):
                self.assertEqual(set(entry) - {"recorded_at", "source", "query_terms"}, {"response"}, path.name)
                self.assertEqual(set(entry["response"]), {"status_code", "text"}, path.name)


class OncoKBSyntheticMappingTests(_EnvMixin, unittest.TestCase):
    def setUp(self):
        self.with_env()
        self.item = _plan()[MatchSpecificity.EXACT_VARIANT].model_copy(update={"terms": {**_plan()[MatchSpecificity.EXACT_VARIANT].terms, "gene": "KRAS", "protein_change": "G12C", "oncotree_code": "LUAD"}})

    def _query(self, payload, cfg=CFG, cache=None):
        return OncoKBProvider(cfg, transport=ScriptedTransport([_resp(payload)])).query(self.item, cache=cache)

    def test_levels_directions_and_implications(self):
        res, recs = self._query(_payload())
        self.assertEqual(res.status, SourceStatus.OK)
        by_id = {r.evidence_id: r for r in recs}
        self.assertEqual(set(by_id), {"oncokb:KRAS:G12C:oncogenic:0", "oncokb:KRAS:G12C:hotspot:0", "oncokb:KRAS:G12C:treatment:0", "oncokb:KRAS:G12C:treatment:1",
                                      "oncokb:KRAS:G12C:treatment:2", "oncokb:KRAS:G12C:diagnostic:0", "oncokb:KRAS:G12C:prognostic:0"})
        onc = by_id["oncokb:KRAS:G12C:oncogenic:0"]
        self.assertEqual(len(onc.citations), 3)
        self.assertEqual(onc.citations[2].source_label, "abstract")
        self.assertIn("highestResistanceLevel=LEVEL_R1", onc.source_native_rating)
        sens = by_id["oncokb:KRAS:G12C:treatment:0"]
        self.assertEqual((sens.direction, sens.source_native_level, sens.drugs), (EvidenceDirection.SUPPORTS, "LEVEL_1", ["Sotorasib"]))
        self.assertEqual(sens.disease.oncotree_code, "NSCLC")
        self.assertIn("FDA level LEVEL_Fda2", sens.study_design)
        self.assertIn("approved indications", sens.study_design)
        self.assertEqual(sens.variant_match, MatchSpecificity.EXACT_VARIANT)
        self.assertFalse(sens.is_hypothesis)
        self.assertTrue(is_accepted(sens))
        res_rec = by_id["oncokb:KRAS:G12C:treatment:1"]
        self.assertEqual(res_rec.direction, EvidenceDirection.DOES_NOT_SUPPORT)
        self.assertEqual(res_rec.source_native_level, "LEVEL_R1")
        self.assertTrue(any("resistance" in l for l in res_rec.limitations))
        self.assertEqual(res_rec.drugs, ["Cetuximab", "Panitumumab"])
        l4 = by_id["oncokb:KRAS:G12C:treatment:2"]
        self.assertTrue(l4.is_hypothesis, "LEVEL_4 is biological evidence, not a validated biomarker")
        self.assertEqual(l4.variant_match, MatchSpecificity.GENE_ALTERATION_CLASS)
        self.assertEqual(l4.disease.name, "All Solid Tumors")
        self.assertTrue(any("excludes cancer types" in l for l in l4.limitations))
        dx = by_id["oncokb:KRAS:G12C:diagnostic:0"]
        self.assertEqual((dx.evidence_category, dx.source_native_level, dx.direction), (EvidenceCategory.DIAGNOSTIC, "LEVEL_DX1", EvidenceDirection.SUPPORTS))
        self.assertEqual(dx.citations[0].pmid, "5")
        px = by_id["oncokb:KRAS:G12C:prognostic:0"]
        self.assertEqual((px.evidence_category, px.source_native_level, px.variant_match), (EvidenceCategory.PROGNOSTIC, "LEVEL_PX2", MatchSpecificity.CODON))
        self.assertEqual(res.source_version, "oncokb-data:v9.9")

    def test_gene_exist_false_is_no_records(self):
        res, recs = self._query(_payload(geneExist=False, variantExist=False, alleleExist=False, oncogenic="Unknown",
                                         mutationEffect={"knownEffect": "Unknown", "description": "", "citations": {"pmids": [], "abstracts": []}},
                                         treatments=[], diagnosticImplications=[], prognosticImplications=[]))
        self.assertEqual(res.status, SourceStatus.NO_RECORDS)
        self.assertEqual(recs, [])
        self.assertIn("not an OncoKB-curated gene", res.message)
        self.assertIn("geneExist=false", res.message)

    def test_variant_exist_false_with_class_level_treatment_is_flagged(self):
        res, recs = self._query(_payload(variantExist=False, alleleExist=True, oncogenic="Likely Oncogenic",
                                         treatments=[_payload()["treatments"][2]], diagnosticImplications=[], prognosticImplications=[]))
        self.assertEqual(res.status, SourceStatus.OK)
        onc = recs[0]
        self.assertEqual(onc.variant_match, MatchSpecificity.CODON)
        self.assertIn("oncokb_variant_not_curated (variantExist=false)", onc.limitations)
        self.assertIn("oncokb_other_alteration_at_same_position (alleleExist=true)", onc.limitations)

    def test_unnamed_level_cancer_type_is_flagged(self):
        tx = dict(_payload()["treatments"][0], level="LEVEL_3B", levelAssociatedCancerType={"code": "", "name": ""})
        res, recs = self._query(_payload(treatments=[tx], diagnosticImplications=[], prognosticImplications=[]))
        rec = [r for r in recs if r.evidence_category == EvidenceCategory.PREDICTIVE][0]
        self.assertIsNone(rec.disease)
        self.assertTrue(any(l.startswith("level_associated_cancer_type_not_stated_by_api") for l in rec.limitations))

    def test_likely_neutral_and_unknown_oncogenicity(self):
        res, recs = self._query(_payload(oncogenic="Likely Neutral", treatments=[], diagnosticImplications=[], prognosticImplications=[]))
        self.assertEqual(recs[0].direction, EvidenceDirection.DOES_NOT_SUPPORT)
        self.assertFalse(recs[0].is_hypothesis)
        res, recs = self._query(_payload(oncogenic="Unknown", mutationEffect={"knownEffect": "Unknown", "citations": {}},
                                         treatments=[_payload()["treatments"][0]], diagnosticImplications=[], prognosticImplications=[]))
        self.assertEqual(recs[0].direction, EvidenceDirection.NOT_APPLICABLE)
        self.assertTrue(recs[0].is_hypothesis)
        self.assertFalse(is_accepted(recs[0]))
        self.assertTrue(any(l.startswith("oncokb_oncogenicity_not_curated") for l in recs[0].limitations))

    def test_missing_data_version_falls_back_to_retrieval_date(self):
        payload = _payload()
        payload.pop("dataVersion")
        res, _ = self._query(payload)
        self.assertTrue(res.source_version.startswith("retrieved:"))
        self.assertIn("dataVersion absent", res.message)

    def test_max_records_caps_output(self):
        res, recs = self._query(_payload(), cfg=CFG.model_copy(update={"max_records": 2}))
        self.assertEqual(len(recs), 2)

    def test_cache_roundtrip_excludes_token(self):
        with tempfile.TemporaryDirectory() as d:
            cache = PayloadCache(d)
            res1, recs1 = self._query(_payload(), cache=cache)
            self.assertEqual(res1.status, SourceStatus.OK)
            self.assertTrue(recs1[0].raw_reference.startswith("oncokb/"))
            cached_files = list(Path(d).rglob("*.json"))
            self.assertEqual(len(cached_files), 1)
            self.assertNotIn(DUMMY_TOKEN, cached_files[0].read_text(encoding="utf-8"))
            st = ScriptedTransport([])
            res2, recs2 = OncoKBProvider(CFG, transport=st).query(self.item, cache=cache)
            self.assertEqual(res2.status, SourceStatus.OK)
            self.assertIn("served from cache", res2.message)
            self.assertEqual(st.requests, [])
            self.assertEqual([r.evidence_id for r in recs2], [r.evidence_id for r in recs1])

    def test_reference_genome_from_plan_terms_or_config(self):
        st = ScriptedTransport([_resp(_payload())])
        no_assembly = self.item.model_copy(update={"terms": {k: v for k, v in self.item.terms.items() if k != "assembly"}})
        OncoKBProvider(CFG.model_copy(update={"reference_genome": "GRCh37"}), transport=st).query(no_assembly)
        self.assertEqual(st.requests[0].params["referenceGenome"], "GRCh37")
        # the planner now carries the case assembly, which takes precedence over the config default
        st = ScriptedTransport([_resp(_payload())])
        OncoKBProvider(CFG.model_copy(update={"reference_genome": "GRCh37"}), transport=st).query(self.item)
        self.assertEqual(st.requests[0].params["referenceGenome"], self.item.terms["assembly"])
        st = ScriptedTransport([_resp(_payload())])
        OncoKBProvider(CFG, transport=st).query(self.item.model_copy(update={"terms": {**self.item.terms, "assembly": "GRCh37"}}))
        self.assertEqual(st.requests[0].params["referenceGenome"], "GRCh37")


class OncoKBConfigAndRegistryTests(unittest.TestCase):
    def test_example_config_loads_oncokb_entry(self):
        cfgs = load_provider_configs(ROOT / "configs" / "providers.example.json")
        self.assertIn("oncokb", cfgs)
        cfg = cfgs["oncokb"]
        self.assertIsInstance(cfg, OncoKBConfig)
        self.assertEqual(cfg.api_key_env, "ONCOKB_API_TOKEN")
        self.assertEqual(cfg.token_file, "~/.oncokb_token")
        self.assertIn("licence", cfg.licence.lower())
        registry = build_registry(cfgs, transport=ScriptedTransport([]))
        self.assertIn("oncokb", registry)
        self.assertIsInstance(registry.get("oncokb"), OncoKBProvider)

    def test_dict_config_uses_oncokb_model(self):
        registry = build_registry({"oncokb": {"base_url": "https://www.oncokb.org/api/v1", "token_file": NO_FILE, "licence": "note"}}, transport=ScriptedTransport([]))
        self.assertEqual(registry.get("oncokb").config.token_file, NO_FILE)

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(Exception):
            OncoKBConfig(base_url="https://www.oncokb.org/api/v1", token="not-allowed")
        with self.assertRaises(Exception):
            OncoKBConfig(base_url="https://www.oncokb.org/api/v1", reference_genome="hg19")


if __name__ == "__main__":
    unittest.main()


class OncoKBClassLevelTests(_EnvMixin, unittest.TestCase):
    """OncoKB annotates uncurated truncating variants from its gene-level 'Truncating Mutations' entry."""

    def setUp(self):
        self.with_env()
        base = _plan()[MatchSpecificity.EXACT_VARIANT]
        self.item = base.model_copy(update={"terms": {**base.terms, "gene": "SETD2", "protein_change": "T305Nfs*4",
                                                    "oncotree_code": "PLEMESO", "consequence_class": "truncating"}})

    def _trunc_payload(self, **over):
        p = _payload(variantExist=False, alleleExist=False, hotspot=False, oncogenic="Likely Oncogenic",
                     treatments=[], diagnosticImplications=[], prognosticImplications=[],
                     highestSensitiveLevel=None, highestResistanceLevel=None, highestFdaLevel=None)
        p["query"] = {"hugoSymbol": "SETD2", "alteration": "T305Nfs*4", "tumorType": "PLEMESO", "referenceGenome": "GRCh38"}
        p["mutationEffect"] = {"knownEffect": "Likely Loss-of-function",
                               "description": "The mutation effect description for truncating mutations in SETD2 is: ...", "citations": {"pmids": ["23417712"]}}
        p.update(over)
        return p

    def test_truncating_lof_becomes_class_level_record(self):
        res, recs = OncoKBProvider(CFG, transport=ScriptedTransport([_resp(self._trunc_payload())])).query(self.item)
        self.assertEqual(res.status, SourceStatus.OK)
        onc = [r for r in recs if r.evidence_category.value == "oncogenic"][0]
        self.assertEqual(onc.variant_match, MatchSpecificity.GENE_ALTERATION_CLASS)
        self.assertIn("Truncating Mutations", onc.variant_description)
        self.assertIn("oncokb_class_level_annotation", onc.limitations)
        self.assertEqual(onc.source_native_status, "Likely Oncogenic")
        self.assertFalse(onc.is_hypothesis)

    def test_missense_uncurated_stays_gene_level(self):
        item = self.item.model_copy(update={"terms": {**self.item.terms, "protein_change": "R123C", "consequence_class": "missense"}})
        payload = self._trunc_payload(mutationEffect={"knownEffect": "Unknown", "description": "", "citations": {}}, oncogenic="Unknown")
        payload["query"]["alteration"] = "R123C"
        res, recs = OncoKBProvider(CFG, transport=ScriptedTransport([_resp(payload)])).query(item)
        self.assertEqual(res.status, SourceStatus.NO_RECORDS)
        self.assertEqual(recs, [])

    def test_truncating_inferred_from_protein_change_when_class_term_absent(self):
        item = self.item.model_copy(update={"terms": {k: v for k, v in self.item.terms.items() if k != "consequence_class"}})
        res, recs = OncoKBProvider(CFG, transport=ScriptedTransport([_resp(self._trunc_payload())])).query(item)
        onc = [r for r in recs if r.evidence_category.value == "oncogenic"][0]
        self.assertEqual(onc.variant_match, MatchSpecificity.GENE_ALTERATION_CLASS)
