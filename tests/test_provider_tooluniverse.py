"""ToolUniverse adapter: bridge protocol, record mapping, failure modes, and inertness for interpretation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from somaweave.domain import EvidenceCategory, MatchSpecificity, SourceStatus
from somaweave.evidence.reconcile import is_accepted
from somaweave.providers import PROVIDER_CLASSES, PayloadCache, ScriptedTransport, TransportResponse, build_registry
from somaweave.providers.base import TransportError
from somaweave.providers.tooluniverse import BRIDGE_SCRIPT, PYTHON_ENV_VAR, ToolUniverseBridgeTransport, ToolUniverseConfig, ToolUniverseProvider
from somaweave.retrieval.plan import DEFAULT_TIER_PROVIDERS, PlanItem

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "providers" / "tooluniverse_clinicaltrials_gene.json"
CONFIG = ToolUniverseConfig(python_executable="/nonexistent/python", max_records=25)


def item(tier=MatchSpecificity.GENE, **terms) -> PlanItem:
    base = {"gene": "PIK3CA", "disease": "Solid Tumor", "alteration_type": "SNV", "assembly": "GRCh38"}
    base.update(terms)
    return PlanItem(tier=tier, terms=base, providers=["tooluniverse"], alteration_id="A1", case_id="SYN-1", description="gene tier")


def response(payload, status=200) -> TransportResponse:
    return TransportResponse(status_code=status, text=json.dumps(payload))


class MappingTests(unittest.TestCase):
    def test_recorded_fixture_maps_to_trial_records(self):
        payload = json.loads(FIX.read_text(encoding="utf-8"))
        provider = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([response(payload)]))
        result, records = provider.query(item())
        self.assertEqual(result.status, SourceStatus.OK)
        self.assertTrue(records)
        self.assertEqual(len(records), min(len(payload["data"]["studies"]), CONFIG.max_records))
        rec = records[0]
        self.assertTrue(rec.evidence_id.startswith("tooluniverse:clinicaltrials:NCT"))
        self.assertEqual(rec.evidence_category, EvidenceCategory.TRIAL)
        self.assertEqual(rec.variant_match, MatchSpecificity.GENE)
        self.assertTrue(rec.is_hypothesis)
        self.assertFalse(is_accepted(rec), "trial records must never enter the accepted pool")
        self.assertIn("clinicaltrials.gov/study/", rec.source_url)
        self.assertIn("not evidence of efficacy", " ".join(rec.limitations))
        self.assertEqual(rec.source_native_status, payload["data"]["studies"][0]["status"])
        self.assertEqual(rec.drugs, [str(i) for i in payload["data"]["studies"][0]["interventions"]])

    def test_empty_result_is_no_records_not_error(self):
        payload = {"status": "success", "data": {"studies": [], "total_count": 0}, "metadata": {"source": "ClinicalTrials.gov API v2"}}
        result, records = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([response(payload)])).query(item())
        self.assertEqual(result.status, SourceStatus.NO_RECORDS)
        self.assertEqual(records, [])
        self.assertIn("absence is not evidence", result.message)

    def test_tool_error_and_malformed_payload_fail_closed(self):
        result, _ = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([TransportResponse(status_code=502, text="tool failed")])).query(item())
        self.assertEqual(result.status, SourceStatus.UNAVAILABLE)
        result, _ = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([response({"status": "error", "error": "bad"})])).query(item())
        self.assertEqual(result.status, SourceStatus.ERROR)
        result, _ = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([response({"data": {"nope": 1}})])).query(item())
        self.assertEqual(result.status, SourceStatus.ERROR)

    def test_supports_gene_tier_only(self):
        provider = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([]))
        self.assertTrue(provider.supports(item()))
        self.assertFalse(provider.supports(item(tier=MatchSpecificity.EXACT_VARIANT)))
        self.assertFalse(provider.supports(item(disease="")))
        result, _ = provider.query(item(tier=MatchSpecificity.CODON))
        self.assertEqual(result.status, SourceStatus.NOT_SUPPORTED)

    def test_cache_round_trip(self):
        payload = json.loads(FIX.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            cache = PayloadCache(tmp)
            first, recs1 = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([response(payload)])).query(item(), cache=cache)
            second, recs2 = ToolUniverseProvider(CONFIG, transport=ScriptedTransport([])).query(item(), cache=cache)
            self.assertEqual(second.status, SourceStatus.OK)
            self.assertIn("served from cache", second.message)
            self.assertEqual([r.evidence_id for r in recs1], [r.evidence_id for r in recs2])

    def test_arguments_follow_config(self):
        cfg = ToolUniverseConfig(python_executable="/x", statuses=["RECRUITING"], page_size=7)
        transport = ScriptedTransport([response({"data": {"studies": []}})])
        ToolUniverseProvider(cfg, transport=transport).query(item())
        req = transport.requests[0]
        self.assertEqual(req.url, "tooluniverse://ClinicalTrials_search_studies")
        self.assertEqual(req.json_body, {"query_term": "PIK3CA", "condition": "Solid Tumor", "status": "RECRUITING", "page_size": 7})

    def test_registered_and_planned(self):
        self.assertIs(PROVIDER_CLASSES["tooluniverse"], ToolUniverseProvider)
        self.assertIn("tooluniverse", DEFAULT_TIER_PROVIDERS[MatchSpecificity.GENE])
        for tier, names in DEFAULT_TIER_PROVIDERS.items():
            if tier != MatchSpecificity.GENE:
                self.assertNotIn("tooluniverse", names)
        registry = build_registry({"tooluniverse": {"python_executable": "/nonexistent/python"}})
        self.assertIsInstance(registry.get("tooluniverse").transport, ToolUniverseBridgeTransport)


class BridgeTransportTests(unittest.TestCase):
    """Exercise the real bridge script and transport with a stub ``tooluniverse`` package on sys.path."""

    STUB = textwrap.dedent('''
        class ToolUniverse:
            def __init__(self):
                self.all_tools = [{"name": "ClinicalTrials_search_studies"}, {"name": "Other"}]
            def load_tools(self):
                print("loading noise on stdout")
            def run(self, call):
                if call["name"] == "boom":
                    raise RuntimeError("tool exploded")
                return {"status": "success", "data": {"studies": [{"nct_id": "NCT00000001", "status": "RECRUITING",
                        "conditions": ["Solid Tumor"], "interventions": ["DrugX"], "phases": ["PHASE2"], "brief_title": "Stub"}],
                        "total_count": 1}, "echo": call["arguments"]}
    ''')

    def _transport(self, tmp: str, **cfg) -> ToolUniverseBridgeTransport:
        pkg = Path(tmp) / "tooluniverse"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(self.STUB, encoding="utf-8")
        # The bridge is started with a clean environment; a tiny launcher injects the stub path.
        launcher = Path(tmp) / "launcher.py"
        launcher.write_text(f"import sys, runpy\nsys.path.insert(0, {tmp!r})\nsys.argv = [sys.argv[1]]\nrunpy.run_path(sys.argv[0], run_name='__main__')\n", encoding="utf-8")
        wrapper = Path(tmp) / ("py.cmd" if os.name == "nt" else "py")
        if os.name == "nt":
            wrapper.write_text(f'@"{sys.executable}" "{launcher}" %*\n', encoding="utf-8")
        else:
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{launcher}" "$@"\n', encoding="utf-8")
            wrapper.chmod(0o755)
        return ToolUniverseBridgeTransport(ToolUniverseConfig(python_executable=str(wrapper), startup_timeout_s=60, **cfg))

    def test_handshake_request_and_tool_error(self):
        self.assertTrue(BRIDGE_SCRIPT.exists())
        with tempfile.TemporaryDirectory() as tmp:
            transport = self._transport(tmp)
            try:
                from somaweave.providers.base import TransportRequest

                resp = transport(TransportRequest(method="POST", url="tooluniverse://ClinicalTrials_search_studies", json_body={"query_term": "X"}, timeout_s=60))
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["echo"], {"query_term": "X"})
                self.assertEqual(transport.ready_info.get("tool_count"), 2)
                err = transport(TransportRequest(method="POST", url="tooluniverse://boom", json_body={}, timeout_s=60))
                self.assertEqual(err.status_code, 502)
                self.assertIn("tool exploded", err.text)
                provider = ToolUniverseProvider(ToolUniverseConfig(python_executable=str(transport.config.python_executable)), transport=transport)
                result, records = provider.query(item())
                self.assertEqual(result.status, SourceStatus.OK)
                self.assertEqual(records[0].evidence_id, "tooluniverse:clinicaltrials:NCT00000001")
                self.assertTrue(result.source_version and result.source_version.startswith("tooluniverse"))
            finally:
                transport.close()

    def test_missing_interpreter_is_unavailable(self):
        env_backup = os.environ.pop(PYTHON_ENV_VAR, None)
        try:
            provider = ToolUniverseProvider(ToolUniverseConfig())
            result, _ = provider.query(item())
            self.assertEqual(result.status, SourceStatus.UNAVAILABLE)
            self.assertIn(PYTHON_ENV_VAR, result.message)
            provider = ToolUniverseProvider(ToolUniverseConfig(python_executable="/nonexistent/python"))
            result, _ = provider.query(item())
            self.assertEqual(result.status, SourceStatus.UNAVAILABLE)
            with self.assertRaises(TransportError):
                from somaweave.providers.base import TransportRequest

                ToolUniverseBridgeTransport(ToolUniverseConfig(python_executable="/nonexistent/python"))(
                    TransportRequest(method="GET", url="https://example.org/not-a-tool"))
        finally:
            if env_backup is not None:
                os.environ[PYTHON_ENV_VAR] = env_backup


if __name__ == "__main__":
    unittest.main()
