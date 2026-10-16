"""Tests for the provider base layer: config, transport, rate limiting, cache, failure states."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from somaweave.domain import EvidenceRecord, MatchSpecificity, SourceQuery, SourceQueryResult, SourceStatus
from somaweave.providers.base import (
    HTTPStatusError,
    PayloadCache,
    Provider,
    ProviderConfig,
    ProviderRegistry,
    ScriptedTransport,
    TokenBucket,
    TransportError,
    TransportRequest,
    TransportResponse,
)
from somaweave.retrieval.plan import PlanItem


def _item(tier=MatchSpecificity.GENE, **terms):
    return PlanItem(tier=tier, terms={"gene": "KRAS", **terms}, providers=["dummy"], alteration_id="A1", case_id="C1")


class DummyProvider(Provider):
    name = "dummy"

    def version(self):
        return "v-test"

    def supports(self, plan_item):
        return "gene" in plan_item.terms

    def _execute(self, plan_item, query, retrieved_at, cache):
        req = TransportRequest(method="GET", url=self.config.base_url, params={"q": plan_item.terms["gene"]})
        payload = self._send(req).json()
        records = [
            EvidenceRecord(evidence_id=f"dummy:{h}", source_name=self.name, source_native_id=str(h), retrieved_at=retrieved_at,
                           query_tier=plan_item.tier, variant_match=plan_item.tier, evidence_category="other", assertion="x")
            for h in payload.get("hits", [])
        ]
        status = SourceStatus.OK if records else SourceStatus.NO_RECORDS
        return self._result(query, status, retrieved_at, records=records, source_version=self.version()), records


def _resp(body, status=200):
    return TransportResponse(status_code=status, text=json.dumps(body))


class ProviderConfigTests(unittest.TestCase):
    def test_defaults_and_user_agent(self):
        cfg = ProviderConfig(base_url="https://example.org/api")
        self.assertEqual(cfg.user_agent, "somaweave/0.1 (research)")
        self.assertEqual(cfg.max_records, 25)
        self.assertIsNone(cfg.api_key_env)

    def test_extra_fields_forbidden(self):
        with self.assertRaises(ValidationError):
            ProviderConfig(base_url="https://example.org", api_key="x")

    def test_api_key_read_from_env_only(self):
        cfg = ProviderConfig(base_url="https://example.org", api_key_env="SW_TEST_KEY")
        p = DummyProvider(cfg, transport=ScriptedTransport([]))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_KEY", None)
            self.assertIsNone(p.api_key())
        with mock.patch.dict(os.environ, {"SW_TEST_KEY": "abc"}):
            self.assertEqual(p.api_key(), "abc")
        self.assertNotIn("abc", cfg.model_dump_json())


class TransportRequestTests(unittest.TestCase):
    def test_native_request_is_canonical_and_redacts(self):
        a = TransportRequest(method="GET", url="https://x/y", params={"b": 1, "a": 2, "api_key": "secret"})
        b = TransportRequest(method="GET", url="https://x/y", params={"a": 2, "api_key": "secret", "b": 1})
        self.assertEqual(a.native_request(), b.native_request())
        redacted = a.native_request(redact={"api_key": "<redacted>"})
        self.assertNotIn("secret", redacted)
        self.assertIn("<redacted>", redacted)


class TokenBucketTests(unittest.TestCase):
    def test_sleeps_to_respect_rate(self):
        t = [0.0]
        slept = []

        def clock():
            return t[0]

        def sleep(s):
            slept.append(s)
            t[0] += s

        bucket = TokenBucket(rate_per_s=2.0, capacity=1, clock=clock, sleep=sleep)
        self.assertEqual(bucket.acquire(), 0.0)
        waited = bucket.acquire()
        self.assertAlmostEqual(waited, 0.5, places=6)
        self.assertAlmostEqual(sum(slept), 0.5, places=6)

    def test_rejects_non_positive_rate(self):
        with self.assertRaises(ValueError):
            TokenBucket(0)


class PayloadCacheTests(unittest.TestCase):
    def test_put_get_roundtrip_and_key(self):
        with tempfile.TemporaryDirectory() as d:
            cache = PayloadCache(d)
            key = PayloadCache.key_for("native")
            self.assertEqual(len(key), 64)
            self.assertIsNone(cache.get("dummy", key))
            ref = cache.put("dummy", key, "native", [{"hits": [1]}])
            self.assertEqual(ref, f"dummy/{key}")
            self.assertTrue((Path(d) / "dummy" / f"{key}.json").exists())
            env = cache.get("dummy", key)
            self.assertEqual(env["payloads"], [{"hits": [1]}])
            self.assertEqual(env["native_request"], "native")


class ProviderQueryStateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = ProviderConfig(base_url="https://example.org/api", rate_limit_per_s=1000)

    def _run(self, script, item=None, cfg=None, cls=DummyProvider):
        p = cls(cfg or self.cfg, transport=ScriptedTransport(script))
        return p.query(item or _item())

    def test_ok_and_no_records(self):
        res, recs = self._run([_resp({"hits": [1, 2]})])
        self.assertEqual(res.status, SourceStatus.OK)
        self.assertEqual(res.record_count, 2)
        self.assertEqual(res.evidence_ids, ["dummy:1", "dummy:2"])
        self.assertEqual(res.source_version, "v-test")
        self.assertIsNotNone(res.duration_ms)
        res, recs = self._run([_resp({"hits": []})])
        self.assertEqual(res.status, SourceStatus.NO_RECORDS)
        self.assertEqual(recs, [])

    def test_transport_error_is_unavailable(self):
        res, recs = self._run([TransportError("connection refused")])
        self.assertEqual(res.status, SourceStatus.UNAVAILABLE)
        self.assertIn("connection refused", res.message)

    def test_exhausted_script_is_unavailable_not_exception(self):
        res, _ = self._run([])
        self.assertEqual(res.status, SourceStatus.UNAVAILABLE)

    def test_http_status_mapping(self):
        self.assertEqual(self._run([_resp({}, 500)])[0].status, SourceStatus.UNAVAILABLE)
        self.assertEqual(self._run([_resp({}, 429)])[0].status, SourceStatus.UNAVAILABLE)
        self.assertEqual(self._run([_resp({}, 400)])[0].status, SourceStatus.ERROR)
        self.assertEqual(self._run([_resp({}, 404)])[0].status, SourceStatus.ERROR)
        self.assertEqual(self._run([_resp({}, 401)])[0].status, SourceStatus.NO_CREDENTIALS)
        self.assertEqual(self._run([_resp({}, 403)])[0].status, SourceStatus.NO_CREDENTIALS)

    def test_malformed_payload_is_error(self):
        res, _ = self._run([TransportResponse(status_code=200, text="<html>not json</html>")])
        self.assertEqual(res.status, SourceStatus.ERROR)
        self.assertIn("JSONDecodeError", res.message)

    def test_missing_required_key_is_no_credentials(self):
        class KeyedProvider(DummyProvider):
            requires_api_key = True

        cfg = ProviderConfig(base_url="https://example.org", api_key_env="SW_TEST_KEY_MISSING")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SW_TEST_KEY_MISSING", None)
            res, _ = self._run([_resp({"hits": [1]})], cfg=cfg, cls=KeyedProvider)
        self.assertEqual(res.status, SourceStatus.NO_CREDENTIALS)
        self.assertIn("SW_TEST_KEY_MISSING", res.message)

    def test_disabled_and_unsupported(self):
        res, _ = self._run([], cfg=self.cfg.model_copy(update={"enabled": False}))
        self.assertEqual(res.status, SourceStatus.NOT_QUERIED)
        p = DummyProvider(self.cfg, transport=ScriptedTransport([]))
        res, _ = p.query(PlanItem(tier=MatchSpecificity.GENE, terms={}, providers=[], alteration_id="A", case_id="C"))
        self.assertEqual(res.status, SourceStatus.NOT_SUPPORTED)

    def test_failure_states_carry_no_records(self):
        for script in ([TransportError("x")], [_resp({}, 503)], [_resp({}, 400)]):
            res, recs = self._run(script)
            self.assertEqual(recs, [])
            self.assertEqual(res.record_count, 0)
            self.assertNotEqual(res.status, SourceStatus.NO_RECORDS, "failure must not look like absence of evidence")

    def test_headers_include_user_agent(self):
        st = ScriptedTransport([_resp({"hits": []})])
        p = DummyProvider(self.cfg, transport=st)
        p._send(TransportRequest(method="GET", url="https://example.org", headers=p._headers()))
        self.assertEqual(st.requests[0].headers["User-Agent"], "somaweave/0.1 (research)")


class RegistryTests(unittest.TestCase):
    def test_register_get_and_duplicates(self):
        p = DummyProvider(ProviderConfig(base_url="https://example.org"), transport=ScriptedTransport([]))
        reg = ProviderRegistry([p])
        self.assertIs(reg.get("dummy"), p)
        self.assertIsNone(reg.get("nope"))
        self.assertIn("dummy", reg)
        self.assertEqual(len(reg), 1)
        with self.assertRaises(ValueError):
            reg.register(p)


if __name__ == "__main__":
    unittest.main()
