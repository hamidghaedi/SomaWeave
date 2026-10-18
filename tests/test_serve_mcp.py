"""MCP serving layer: CLI runner behaviour (offline), run-directory access rules, and optional server registration."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

from somaweave.serve.mcp_server import REPORT_FORMATS, SomaWeaveRunner, build_server

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples" / "synthetic_case.json"
HAS_MCP = importlib.util.find_spec("mcp") is not None


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runner = SomaWeaveRunner(python=sys.executable, results_root=self.tmp.name, timeout_s=300)

    def tearDown(self):
        self.tmp.cleanup()

    def test_validate_case(self):
        res = self.runner.validate_case(str(CASE))
        self.assertTrue(res["ok"], res.get("stderr"))
        self.assertIn("summary", res)
        bad = self.runner.validate_case(str(ROOT / "README.md"))
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["exit_code"], 1)

    def test_offline_interpret_list_get_and_report(self):
        res = self.runner.interpret_case(str(CASE), run_id="mcp-test", offline=True)
        self.assertTrue(res["ok"], res.get("stderr"))
        self.assertEqual(res["run_id"], "mcp-test")
        self.assertTrue(res["offline"])
        self.assertTrue(res["findings"])
        self.assertTrue({"analytical", "oncogenicity", "actionability_tier", "relevance"} <= set(res["findings"][0]))
        self.assertTrue(Path(res["outputs"]["report_markdown"]).exists())

        listed = self.runner.list_runs()
        self.assertEqual([r["run_id"] for r in listed["runs"]], ["mcp-test"])
        self.assertEqual(self.runner.get_run("mcp-test")["case_id"], res["case_id"])

        report = self.runner.get_report("mcp-test", "markdown", max_chars=500)
        self.assertTrue(report["truncated"])
        self.assertEqual(len(report["content"]), 500)
        for fmt in REPORT_FORMATS:
            self.assertTrue(Path(self.runner.get_report("mcp-test", fmt)["path"]).exists(), fmt)

    def test_run_id_cannot_escape_results_root(self):
        for bad in ("../x", "a/b", "..", "", "sub\\dir"):
            with self.assertRaises(ValueError):
                self.runner.get_run(bad)
        with self.assertRaises(FileNotFoundError):
            self.runner.get_run("does-not-exist")
        with self.assertRaises(ValueError):
            self.runner.get_report("x", "html")

    def test_missing_interpreter_and_results_root_are_reported(self):
        res = SomaWeaveRunner(python="/nonexistent/python", results_root=self.tmp.name).validate_case(str(CASE))
        self.assertFalse(res["ok"])
        self.assertIn("interpreter not found", res["error"])
        backup = os.environ.pop("SOMAWEAVE_RESULTS_ROOT", None)
        try:
            with self.assertRaises(ValueError):
                SomaWeaveRunner(python=sys.executable).list_runs()
        finally:
            if backup is not None:
                os.environ["SOMAWEAVE_RESULTS_ROOT"] = backup


@unittest.skipUnless(HAS_MCP, "mcp package not installed in this environment")
class ServerRegistrationTests(unittest.TestCase):
    def test_tools_registered(self):
        import asyncio

        server = build_server(SomaWeaveRunner(python=sys.executable, results_root="."))
        names = sorted(t.name for t in asyncio.run(server.list_tools()))
        self.assertEqual(names, ["somaweave_build_case", "somaweave_get_report", "somaweave_get_run", "somaweave_interpret_case",
                                 "somaweave_list_runs", "somaweave_validate_case"])


if __name__ == "__main__":
    unittest.main()
