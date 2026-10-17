"""Offline exact-allele population/hotspot and conservative rule regressions."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from somaweave.domain import EvidenceCategory, MatchSpecificity, SourceStatus
from somaweave.domain.evidence import PopulationFrequency
from somaweave.evidence import reconcile
from somaweave.normalization import normalize_case
from somaweave.interpretation.interpret import assess_oncogenicity
from somaweave.providers import PayloadCache, ScriptedTransport, TransportResponse
from somaweave.providers.gnomad import GnomADConfig, GnomADProvider
from somaweave.providers.oncokb import OncoKBProvider
from somaweave.retrieval.plan import PlanItem, build_query_plan
from test_interpretation_rules import _interpret, _records, _luad_case, _retrieval
from test_providers_oncokb import CFG, _payload, _plan, _resp, DUMMY_TOKEN

FIX = Path(__file__).parent / "fixtures/providers/gnomad_frequency.json"
CONFIG = GnomADConfig(base_url="https://gnomad.broadinstitute.org/api")


def item(**over):
    return PlanItem(tier=MatchSpecificity.EXACT_VARIANT, case_id="synthetic", alteration_id="A",
                    terms={"gene": "KMT2C", "alteration_type": "SNV", "assembly": "GRCh38", "chromosome": "chr7", "position": 100,
                           "ref": "C", "alt": "A", **over})


def response(payload):
    return TransportResponse(status_code=200, text=json.dumps(payload))


class PopulationProviderTests(unittest.TestCase):
    def query(self, payload, **kw):
        return GnomADProvider(CONFIG, transport=ScriptedTransport([response(payload)]), sleep=lambda _: None).query(item(), **kw)

    def test_counts_major_population_and_cache(self):
        payload = json.loads(FIX.read_text())
        with tempfile.TemporaryDirectory() as d:
            cache = PayloadCache(d)
            result, records = self.query(payload, cache=cache)
            self.assertEqual(result.status, SourceStatus.OK)
            rec = records[0]
            self.assertEqual(rec.evidence_category, EvidenceCategory.EPIDEMIOLOGIC)
            self.assertEqual(rec.variant_match, MatchSpecificity.EXACT_VARIANT)
            self.assertEqual(rec.source_version, "gnomad_r4")
            self.assertEqual(rec.population_frequency.allele_count, 10)
            self.assertEqual(rec.population_frequency.overall_af, .01)
            self.assertEqual(rec.population_frequency.max_population_af, .05)
            self.assertEqual(set(rec.population_frequency.populations), {"afr", "nfe"})
            transport = ScriptedTransport([])
            again, repeated = GnomADProvider(CONFIG, transport=transport).query(item(), cache=cache)
            self.assertEqual(again.status, SourceStatus.OK)
            self.assertEqual(records[0].evidence_id, repeated[0].evidence_id)
            self.assertEqual(transport.requests, [])

    def test_absence_and_failure_are_distinct(self):
        result, records = self.query({"errors": [{"message": "Service overloaded"}]})
        self.assertEqual(result.status, SourceStatus.UNAVAILABLE)
        self.assertEqual(records, [])
        for payload in ({"data": {"variant": None}},
                        {"data": {"variant": None}, "errors": [{"message": "Variant not found"}]}):
            result, records = self.query(payload)
            self.assertEqual(result.status, SourceStatus.NO_RECORDS)
            self.assertEqual(records, [])
        for payload in ({"errors": [{"message": "rate limit"}]}, {},
                        {"data": {"variant": None}, "errors": [{"message": "timed out"}]}):
            result, _ = self.query(payload)
            self.assertEqual(result.status, SourceStatus.ERROR)

    def test_wrong_allele_and_missing_denominator_fail_closed(self):
        base = json.loads(FIX.read_text())
        for field, value in (("ref", "T"), ("variantId", "7-101-C-A"), ("joint", None)):
            bad = copy.deepcopy(base)
            bad["data"]["variant"][field] = value
            self.assertEqual(self.query(bad)[0].status, SourceStatus.ERROR)
        base["data"]["variant"]["joint"]["an"] = 0
        self.assertEqual(self.query(base)[0].status, SourceStatus.ERROR)

    def test_no_liftover_or_symbolic_alleles_and_planner_fields(self):
        provider = GnomADProvider(CONFIG, transport=ScriptedTransport([]))
        for terms in ({"assembly": "GRCh37"}, {"alt": "<DEL>"}, {"ref": None}, {"position": None}, {"alteration_type": "CNA"}):
            self.assertEqual(provider.query(item(**terms))[0].status, SourceStatus.NOT_SUPPORTED)
        case = _luad_case()
        exact = build_query_plan(case, case.alterations[0])[0]
        self.assertIn("gnomad", exact.providers)
        self.assertEqual(exact.terms["position"], case.alterations[0].position.position)

    def test_rate_and_http_status(self):
        with self.assertRaises(ValueError):
            GnomADConfig(base_url=CONFIG.base_url, rate_limit_per_s=2)
        now = [0.0]
        def advance(delay):
            now[0] += delay
        result, _ = GnomADProvider(CONFIG, transport=ScriptedTransport([
            TransportResponse(status_code=503, text="down") for _ in range(4)
        ]), clock=lambda: now[0], sleep=advance).query(item())
        self.assertEqual(result.status, SourceStatus.UNAVAILABLE)


class PopulationRulesTests(unittest.TestCase):
    def record(self, af):
        _, records = GnomADProvider(CONFIG, transport=ScriptedTransport([response(json.loads(FIX.read_text()))])).query(item())
        return records[0].model_copy(update={"population_frequency": PopulationFrequency(dataset="synthetic-v4", overall_af=af),
                                           "gene_symbol": "EGFR"})

    def test_kmt2c_like_five_percent_allele_never_oncogenic(self):
        # Synthetic splice-region allele frequency plus generic/curated support.
        records = _records("same_disease_level_A_sensitivity", "clinvar_oncogenic_exact")
        fa, _ = _interpret(records + [self.record(.05)])
        self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")
        self.assertIn("SBVS1", fa.oncogenicity.criteria_met)
        self.assertTrue(any("probable germline polymorphism" in s for s in fa.oncogenicity.rationale))
        self.assertIn(self.record(.05).evidence_id, fa.oncogenicity.evidence_ids)

    def test_synthetic_splice_region_with_population_caution(self):
        case = _luad_case()
        alt = case.alterations[0].model_copy(update={"gene_symbol": "KMT2C", "hgvs_p": None,
                                                   "hgvs_c": "c.99+5G>T", "consequence": "splice_region_variant"})
        case = case.model_copy(update={"alterations": [alt]})
        record = self.record(.05).model_copy(update={"gene_symbol": "KMT2C"})
        es = reconcile(normalize_case(case), alt, _retrieval(case, alt, [record]))
        result = assess_oncogenicity(alt, es)
        self.assertEqual(result.classification, "uncertain_significance")
        self.assertIn("SBVS1", result.criteria_met)

    def test_population_maximum_caution_when_overall_is_rare(self):
        record = self.record(.0001).model_copy(update={"population_frequency": PopulationFrequency(
            dataset="synthetic-v4", overall_af=.0001, populations={"afr": .05}, max_population="afr", max_population_af=.05)})
        fa, _ = _interpret([record])
        self.assertIn("SBVS1", fa.oncogenicity.criteria_met)

    def test_thresholds_and_zero_frequency_never_promotes(self):
        for af, tag in ((.01, "SBS1"), (.0011, "SBS1"), (.0101, "SBVS1"), (.001, None), (0, None)):
            fa, _ = _interpret([self.record(af)])
            self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")
            self.assertEqual([t for t in fa.oncogenicity.criteria_met if t in ("SBS1", "SBVS1")], [tag] if tag else [])
        fa, _ = _interpret([self.record(.05)], {("gnomad", "exact_variant"): SourceStatus.OK})
        self.assertEqual(fa.oncogenicity.classification, "not_assessed")
        self.assertEqual(fa.actionability.tier, "not_assessed")

    def test_hotspot_flag_not_treatment_counts(self):
        with patch.dict("os.environ", {"ONCOKB_API_TOKEN": DUMMY_TOKEN}):
            for flag in (True, False):
                _, records = OncoKBProvider(CFG, transport=ScriptedTransport([_resp(_payload(hotspot=flag))])).query(_plan(1)[MatchSpecificity.EXACT_VARIANT])
                hotspots = [r for r in records if r.hotspot is True]
                self.assertEqual(len(hotspots), int(flag))
                fa, _ = _interpret(records)
                self.assertEqual("OS3" in fa.oncogenicity.criteria_met, flag)
                self.assertNotIn("OM3", fa.oncogenicity.criteria_met)

    def test_unknown_hotspot_alone_does_not_promote(self):
        with patch.dict("os.environ", {"ONCOKB_API_TOKEN": DUMMY_TOKEN}):
            _, records = OncoKBProvider(CFG, transport=ScriptedTransport([_resp(_payload(
                oncogenic="Unknown", mutationEffect={}, treatments=[], diagnosticImplications=[], prognosticImplications=[]))])).query(_plan(1)[MatchSpecificity.EXACT_VARIANT])
        fa, _ = _interpret(records)
        self.assertEqual(fa.oncogenicity.classification, "uncertain_significance")
        self.assertIn("OS3", fa.oncogenicity.criteria_met)
