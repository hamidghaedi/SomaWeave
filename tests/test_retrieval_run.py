"""Tests for plan execution: offline mode, stop conditions, dedup, cache."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from somaweave.domain import EvidenceCategory, EvidenceRecord, MatchSpecificity, SourceStatus
from somaweave.domain.io import load_case
from somaweave.providers import ProviderConfig, ProviderRegistry, ScriptedTransport, TransportResponse, build_registry, load_provider_configs
from somaweave.providers.base import TransportError, TransportRequest
from somaweave.retrieval import RetrievalResult, build_query_plan, dedupe_evidence, run_plan, stop_after_tier, stop_when_curated_evidence

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "providers"


class RoutingTransport:
    """Dispatch to a ScriptedTransport by URL substring; unknown hosts fail as transport errors."""

    def __init__(self, routes: dict[str, ScriptedTransport]):
        self.routes = routes
        self.calls = 0

    def __call__(self, request: TransportRequest):
        self.calls += 1
        for key, st in self.routes.items():
            if key in request.url:
                return st(request)
        raise TransportError(f"no route for {request.url}")


def _fixture_script(*names):
    """Concatenate recorded exchanges; the literal "zero" inserts a synthetic zero-hit Europe PMC response."""
    script = []
    for n in names:
        if n == "zero":
            script.append(TransportResponse(status_code=200, text=json.dumps({"version": "6.9", "hitCount": 0, "resultList": {"result": []}})))
            continue
        script.extend(json.loads((FIX / f"{n}.json").read_text(encoding="utf-8")))
    return ScriptedTransport(script)


def _registry(transport):
    cfgs = load_provider_configs(ROOT / "configs" / "providers.example.json")
    # these tests exercise the three providers with recorded fixtures; OncoKB has its own test module
    cfgs.pop("oncokb", None)
    # fixtures were recorded with europepmc max_records=5 and civic max_records=10
    caps = {"europepmc": 5, "civic": 10}
    fast = {k: v.model_copy(update={"rate_limit_per_s": 1000, "max_records": caps.get(k, v.max_records)}) for k, v in cfgs.items()}
    return build_registry(fast, transport=transport)


def _plan():
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    return build_query_plan(case, case.alterations[0])


def _rec(source, native, vm, qt=None, **kw):
    return EvidenceRecord(evidence_id=f"{source}:{native}:{vm.value}", source_name=source, source_native_id=native,
                          retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc), query_tier=qt or vm, variant_match=vm,
                          evidence_category=EvidenceCategory.OTHER, assertion="a", **kw)


class DedupeTests(unittest.TestCase):
    def test_keeps_most_specific_and_order(self):
        recs = [_rec("civic", "1", MatchSpecificity.GENE), _rec("civic", "2", MatchSpecificity.GENE),
                _rec("civic", "1", MatchSpecificity.EXACT_VARIANT), _rec("clinvar", "1", MatchSpecificity.GENE)]
        out, removed = dedupe_evidence(recs)
        self.assertEqual(removed, 1)
        self.assertEqual([(r.source_name, r.source_native_id) for r in out], [("civic", "1"), ("civic", "2"), ("clinvar", "1")])
        self.assertEqual(out[0].variant_match, MatchSpecificity.EXACT_VARIANT)

    def test_tie_broken_by_query_tier(self):
        a = _rec("x", "1", MatchSpecificity.GENE, qt=MatchSpecificity.GENE)
        b = _rec("x", "1", MatchSpecificity.GENE, qt=MatchSpecificity.CODON)
        out, _ = dedupe_evidence([a, b])
        self.assertEqual(out[0].query_tier, MatchSpecificity.CODON)


class RunPlanTests(unittest.TestCase):
    def test_offline_mode_marks_everything_not_queried(self):
        plan = _plan()
        res = run_plan(plan, ProviderRegistry(), offline=True)
        self.assertTrue(res.offline)
        self.assertEqual(res.evidence, [])
        expected = sum(len(it.providers) for it in plan)
        self.assertEqual(len(res.query_results), expected)
        self.assertTrue(all(r.status == SourceStatus.NOT_QUERIED for r in res.query_results))
        self.assertTrue(all(r.message == "offline mode" for r in res.query_results))
        self.assertEqual(res.status_counts(), {"not_queried": expected})

    def test_missing_provider_is_not_queried_not_negative(self):
        plan = [_plan()[0]]
        res = run_plan(plan, ProviderRegistry())
        self.assertEqual({r.query.source_name for r in res.query_results}, {"civic", "clinvar", "oncokb", "europepmc"})
        self.assertTrue(all(r.status == SourceStatus.NOT_QUERIED for r in res.query_results))
        self.assertIn("not configured", res.query_results[0].message)

    def test_full_run_with_recorded_fixtures(self):
        transport = RoutingTransport({
            "civicdb.org": _fixture_script("civic_exact_ctnnb1_d32n", "civic_codon_ctnnb1_d32", "civic_gene_ctnnb1"),
            "ncbi.nlm.nih.gov": _fixture_script("clinvar_exact_ctnnb1_d32n"),
            "ebi.ac.uk": _fixture_script("epmc_exact_ctnnb1_d32n", "zero", "epmc_gene_class_ctnnb1"),
        })
        plan = _plan()
        res = run_plan(plan, _registry(transport))
        self.assertIsInstance(res, RetrievalResult)
        self.assertEqual(res.case_id, "SYN-0001")
        self.assertEqual(res.alteration_id, "A1")
        counts = res.status_counts()
        # civic exact -> no_records; civic codon ok (1); civic gene ok (10, capped); clinvar exact ok (2);
        # epmc exact ok (5); epmc codon -> zero hits -> no_records; epmc gene-class ok (5);
        # epmc gene/pathway/disease -> script exhausted -> unavailable (missing evidence, not negative)
        self.assertEqual(counts["no_records"], 2)
        self.assertEqual(counts["ok"], 5)
        self.assertEqual(counts["unavailable"], 3)
        self.assertEqual(counts["not_queried"], 1)  # oncokb is not in this registry: missing, not negative
        self.assertEqual(len(res.query_results), 11)
        self.assertEqual(len(res.evidence), 1 + 10 + 2 + 5 + 5)
        self.assertEqual(res.duplicates_removed, 0)
        sources = {r.source_name for r in res.evidence}
        self.assertEqual(sources, {"civic", "clinvar", "europepmc"})
        exact = res.results_for(MatchSpecificity.EXACT_VARIANT)
        self.assertEqual({r.query.source_name: r.status for r in exact},
                         {"civic": SourceStatus.NO_RECORDS, "clinvar": SourceStatus.OK, "oncokb": SourceStatus.NOT_QUERIED, "europepmc": SourceStatus.OK})
        self.assertTrue(all(r.query.native_request for r in exact if r.status != SourceStatus.NOT_QUERIED))
        self.assertIsNone(res.stopped_after_tier)
        self.assertTrue(all(r.raw_reference is None for r in res.evidence))

    def test_stop_after_tier_skips_remaining_with_not_queried(self):
        transport = RoutingTransport({
            "civicdb.org": _fixture_script("civic_exact_ctnnb1_d32n"),
            "ncbi.nlm.nih.gov": _fixture_script("clinvar_exact_ctnnb1_d32n"),
            "ebi.ac.uk": _fixture_script("epmc_exact_ctnnb1_d32n"),
        })
        res = run_plan(_plan(), _registry(transport), stop_when=stop_after_tier(MatchSpecificity.EXACT_VARIANT))
        self.assertEqual(res.stopped_after_tier, MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(transport.calls, 4)  # civic 1, clinvar 2, epmc 1
        later = [r for r in res.query_results if r.query.tier != MatchSpecificity.EXACT_VARIANT]
        self.assertTrue(later)
        self.assertTrue(all(r.status == SourceStatus.NOT_QUERIED and "stop condition" in r.message for r in later))
        self.assertEqual(len(res.evidence), 2 + 5)

    def test_stop_when_curated_evidence(self):
        transport = RoutingTransport({
            "civicdb.org": _fixture_script("civic_exact_ctnnb1_d32n"),
            "ncbi.nlm.nih.gov": _fixture_script("clinvar_exact_ctnnb1_d32n"),
            "ebi.ac.uk": _fixture_script("epmc_exact_ctnnb1_d32n"),
        })
        res = run_plan(_plan(), _registry(transport), stop_when=stop_when_curated_evidence(min_records=1))
        self.assertEqual(res.stopped_after_tier, MatchSpecificity.EXACT_VARIANT, "two ClinVar records satisfy the condition")

    def test_dedupes_same_civic_item_across_tiers_keeping_most_specific(self):
        codon = json.loads((FIX / "civic_codon_ctnnb1_d32.json").read_text(encoding="utf-8"))
        transport = RoutingTransport({"civicdb.org": ScriptedTransport(codon + codon + codon)})
        plan = [it.model_copy(update={"providers": ["civic"]}) for it in _plan() if it.tier in (MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON, MatchSpecificity.GENE)]
        res = run_plan(plan, _registry(transport))
        self.assertEqual(len(res.evidence), 1)
        self.assertEqual(res.duplicates_removed, 2)
        # the exact-tier query returned a D32Y profile, so the best honest match is CODON (never EXACT)
        self.assertEqual(res.evidence[0].variant_match, MatchSpecificity.CODON)
        self.assertEqual(res.evidence[0].query_tier, MatchSpecificity.CODON)

    def test_cache_round_trip(self):
        plan = [it for it in _plan() if it.tier == MatchSpecificity.EXACT_VARIANT]
        plan = [plan[0].model_copy(update={"providers": ["clinvar", "europepmc"]})]
        with tempfile.TemporaryDirectory() as d:
            transport = RoutingTransport({"ncbi.nlm.nih.gov": _fixture_script("clinvar_exact_ctnnb1_d32n"), "ebi.ac.uk": _fixture_script("epmc_exact_ctnnb1_d32n")})
            res1 = run_plan(plan, _registry(transport), cache_root=d)
            self.assertEqual(transport.calls, 3)
            refs = {r.raw_reference for r in res1.evidence}
            self.assertEqual(len(refs), 2)
            for ref in refs:
                path = Path(d) / f"{ref}.json"
                self.assertTrue(path.exists(), ref)
                env = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("payloads", env)
                self.assertIn("native_request", env)
            # second run: no transport available at all, everything served from cache
            res2 = run_plan(plan, _registry(RoutingTransport({})), cache_root=d)
            self.assertEqual([r.status for r in res2.query_results], [SourceStatus.OK, SourceStatus.OK])
            self.assertTrue(all("served from cache" in r.message for r in res2.query_results))
            self.assertEqual([e.evidence_id for e in res2.evidence], [e.evidence_id for e in res1.evidence])

    def test_empty_plan_rejected(self):
        with self.assertRaises(ValueError):
            run_plan([], ProviderRegistry())


if __name__ == "__main__":
    unittest.main()
