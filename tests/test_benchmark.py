"""Benchmark integrity, immutable expectations, no-network default and gates."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from somaweave.domain.io import load_case
from somaweave.workflows.benchmark import Benchmark, _offline, evaluate

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/benchmark"


class BenchmarkTests(unittest.TestCase):
    def copy(self, directory):
        return Path(shutil.copytree(CASES, Path(directory) / "cases"))

    def hashes(self, root):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("*.json")}

    def test_nine_classes_validate_and_replay_without_network(self):
        manifest = Benchmark.model_validate_json((CASES / "benchmark.json").read_text())
        self.assertEqual({s.spec_class for s in manifest.scenarios}, set(range(1, 10)))
        self.assertEqual(len(manifest.scenarios), 9)
        original = self.hashes(CASES)
        with tempfile.TemporaryDirectory() as d, patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            out = Path(d) / "summary.md"
            code = evaluate(CASES, out, allow_draft=True)
            text = out.read_text()
            self.assertEqual(code, int(" | False |" in text))
            self.assertIn("DRAFT EXPECTATIONS", text)
            self.assertIn("analytical: 11/11", text)
            self.assertIn("no composite score", text)
            self.assertIn("Package SHA-256", text)
            self.assertIn("excluded_by_class", text)
            self.assertEqual(evaluate(CASES, Path(d) / "repeat.md", allow_draft=True), code)
            self.assertEqual(text, (Path(d) / "repeat.md").read_text())
        self.assertEqual(self.hashes(CASES), original)

    def test_default_and_live_refuse_unsigned_expectations_before_retrieval(self):
        with tempfile.TemporaryDirectory() as d, patch("somaweave.workflows.benchmark._offline") as offline, patch("somaweave.workflows.benchmark._live") as live:
            for kw in ({}, {"live": True}, {"live": True, "allow_draft": True}):
                with self.assertRaisesRegex(ValueError, "owner-adjudicated"):
                    evaluate(CASES, Path(d) / "out.md", **kw)
            self.assertFalse((Path(d) / "out.md").exists())
            offline.assert_not_called()
            live.assert_not_called()

    def test_mismatch_is_reported_without_rewriting_expectations(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.copy(d)
            path = root / "01_driver.expected.json"
            data = json.loads(path.read_text()); data["findings"]["A1"]["analytical"] = "unreliable"
            path.write_text(json.dumps(data))
            before = self.hashes(root)
            out = Path(d) / "summary.md"
            self.assertEqual(evaluate(root, out, allow_draft=True), 1)
            self.assertIn("expected unreliable, actual high", out.read_text())
            self.assertEqual(self.hashes(root), before)

    def test_invalid_signoff_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.copy(d); path = root / "01_driver.expected.json"
            data = json.loads(path.read_text()); data["adjudication"]["status"] = "owner_signed_off"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "reviewer and review date"):
                evaluate(root, Path(d) / "summary.md", allow_draft=True)

    def test_live_dispatch_with_test_only_signed_copies(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.copy(d)
            for path in root.glob("*.expected.json"):
                data = json.loads(path.read_text())
                # Deliberately synthetic metadata, only in a temporary test copy.
                data["adjudication"] = {"status": "owner_signed_off", "reviewer": "test fixture", "reviewed_at": "2026-01-01"}
                path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "run ID prefix"):
                evaluate(root, Path(d) / "summary.md", live=True)
            def replay(case_path, *args):
                return _offline(load_case(case_path), Path(str(case_path).replace(".case.json", ".evidence.json")))
            with patch("somaweave.workflows.benchmark._live", side_effect=replay) as mock:
                self.assertIn(evaluate(root, Path(d) / "summary.md", live=True, run_id_prefix="test"), (0, 1))
                self.assertEqual(mock.call_count, 9)

    def test_outputs_and_inputs_cannot_overwrite_fixture_paths(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            evaluate(CASES, CASES / "forbidden.md", allow_draft=True)
        self.assertFalse((CASES / "forbidden.md").exists())
        with tempfile.TemporaryDirectory() as d:
            root = self.copy(d); path = root / "benchmark.json"
            data = json.loads(path.read_text());data["scenarios"][0]["case"] = "../outside.json";path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "invalid benchmark input"):
                evaluate(root, Path(d) / "summary.md", allow_draft=True)

    def test_allele_identity_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.copy(d); path = root / "01_driver.evidence.json"
            data = json.loads(path.read_text()); data["A1"]["alteration_id"] = "different";path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                evaluate(root, Path(d) / "summary.md", allow_draft=True)
