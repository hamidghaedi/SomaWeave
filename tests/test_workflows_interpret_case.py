"""End-to-end offline tests for the interpret-case workflow and CLI (no network)."""

import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from somaweave.cli import main
from somaweave.domain import SourceStatus
from somaweave.providers import ProviderConfig, ProviderRegistry, ScriptedTransport, build_registry
from somaweave.providers.base import TransportError
from somaweave.reporting import RESEARCH_USE_BANNER
from somaweave.reporting.render_markdown import AXIS_HEADINGS
from somaweave.workflows import RootsError, resolve_roots, run

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic_case.json"
EXPECTED_FILES = ["manifest.json", "evidence/evidence.json", "evidence/source_queries.json", "reports/report.json", "reports/report.md",
                  "qc/technical.json", "logs/run.log"]
MANIFEST_KEYS = {"run_id", "somaweave_version", "python_version", "pydantic_version", "git_commit", "input", "providers_config", "offline",
                 "started_utc", "finished_utc", "source_status_counts", "per_source_status_counts", "environment_variable_names", "roots",
                 "outputs", "findings"}
CITED = re.compile(r"\[[^\[\]]+\]\s*$")


def _claim_lines(md: str) -> list[str]:
    out = []
    for block in md.split("#### Established claims")[1:]:
        body = block.split("\n####", 1)[0]
        out.extend(ln for ln in body.splitlines() if ln.startswith("- ") and not ln.startswith("- none"))
    return out


class OfflineEndToEndTests(unittest.TestCase):
    def test_offline_run_tree_manifest_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            res = run(EXAMPLE, results_root=d, offline=True, run_id="offline-test")
            self.assertEqual(res.run_dir, Path(d).resolve() / "offline-test")
            for rel in EXPECTED_FILES:
                self.assertTrue((res.run_dir / rel).exists(), rel)
            manifest = json.loads(res.manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(MANIFEST_KEYS <= set(manifest), MANIFEST_KEYS - set(manifest))
            self.assertTrue(manifest["offline"])
            self.assertEqual(manifest["input"]["case_id"], "SYN-0001")
            self.assertEqual(len(manifest["input"]["sha256"]), 64)
            self.assertEqual(set(manifest["source_status_counts"]), {"not_queried"})
            self.assertNotIn("hostname", json.dumps(manifest))
            for name in manifest["environment_variable_names"]:
                self.assertTrue(name.startswith("SOMAWEAVE_"))
            self.assertEqual(len(manifest["findings"]), 2)
            for f in manifest["findings"]:
                self.assertEqual(f["oncogenicity"], "not_assessed")
                self.assertEqual(f["actionability_tier"], "not_assessed")
            md = res.report_markdown_path.read_text(encoding="utf-8")
            self.assertIn(RESEARCH_USE_BANNER, md)
            for heading in AXIS_HEADINGS.values():
                self.assertEqual(md.count(f"#### {heading}"), 2, heading)
            self.assertIn("not queried", md)
            self.assertEqual(_claim_lines(md), [])
            lower = md.lower()
            self.assertNotIn("no evidence", lower)
            self.assertIn("missing evidence", lower)
            queries = json.loads(res.source_queries_path.read_text(encoding="utf-8"))
            self.assertEqual({a["alteration_id"] for a in queries["alterations"]}, {"A1", "A2"})
            self.assertTrue(all(q["status"] == "not_queried" for a in queries["alterations"] for q in a["query_results"]))
            report = json.loads(res.report_json_path.read_text(encoding="utf-8"))
            self.assertTrue(report["research_use_only"])
            log = res.log_path.read_text(encoding="utf-8")
            self.assertIn("finished", log)

    def test_scripted_registry_claims_are_cited(self):
        """A registry whose transport fails for ClinVar and returns recorded CIViC data: missing source is named, claims cited."""
        fix = ROOT / "tests" / "fixtures" / "providers"
        civic_script = []
        for n in ("civic_exact_ctnnb1_d32n", "civic_codon_ctnnb1_d32", "civic_gene_ctnnb1"):
            civic_script.extend(json.loads((fix / f"{n}.json").read_text(encoding="utf-8")))

        class Routing:
            def __init__(self):
                self.civic = ScriptedTransport(civic_script)

            def __call__(self, request):
                if "civicdb.org" in request.url:
                    return self.civic(request)
                raise TransportError("simulated outage")

        cfgs = {
            "civic": ProviderConfig(base_url="https://civicdb.org/api/graphql", rate_limit_per_s=1000, max_records=10),
            "clinvar": ProviderConfig(base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils", rate_limit_per_s=1000),
            "europepmc": ProviderConfig(base_url="https://www.ebi.ac.uk/europepmc/webservices/rest/search", rate_limit_per_s=1000, max_records=5),
        }
        registry = build_registry(cfgs, transport=Routing())
        with tempfile.TemporaryDirectory() as d:
            res = run(EXAMPLE, results_root=d, registry=registry, run_id="scripted")
            self.assertIn("unavailable", res.status_counts)
            md = res.report_markdown_path.read_text(encoding="utf-8")
            claims = _claim_lines(md)
            self.assertTrue(claims)
            for ln in claims:
                self.assertRegex(ln, CITED)
            self.assertIn("ClinVar: missing evidence (unavailable", md)
            self.assertNotIn("no evidence", md.lower())
            manifest = json.loads(res.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["per_source_status_counts"]["clinvar"], {"unavailable": 2})  # one exact-tier query per alteration

    def test_missing_source_never_yields_no_evidence_statement(self):
        """Every provider errors: nothing in the report may read as negative evidence."""
        class Failing:
            def __call__(self, request):
                raise TransportError("simulated outage")

        cfgs = {"civic": ProviderConfig(base_url="https://civicdb.org/api/graphql", rate_limit_per_s=1000),
                "clinvar": ProviderConfig(base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils", rate_limit_per_s=1000),
                "europepmc": ProviderConfig(base_url="https://www.ebi.ac.uk/europepmc/webservices/rest/search", rate_limit_per_s=1000)}
        with tempfile.TemporaryDirectory() as d:
            res = run(EXAMPLE, results_root=d, registry=build_registry(cfgs, transport=Failing()), run_id="failing")
            self.assertEqual(set(res.status_counts), {"unavailable"})
            md = res.report_markdown_path.read_text(encoding="utf-8")
            lower = md.lower()
            for phrase in ("no evidence", "no curated evidence", "no known", "not oncogenic", "benign", "tier iv", "tier: **iv**"):
                self.assertNotIn(phrase, lower, phrase)
            self.assertIn("missing evidence", lower)
            self.assertIn("not_assessed", lower)
            for f in res.findings_summary:
                self.assertEqual(f["actionability_tier"], "not_assessed")
                self.assertEqual(f["relevance"], "not_assessable")


class RootsTests(unittest.TestCase):
    def test_roots_from_env_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            roots = resolve_roots(env={"SOMAWEAVE_RESULTS_ROOT": d})
            self.assertEqual(roots.results_root, Path(d).resolve())
            self.assertIsNone(roots.cache_root)
            with self.assertRaises(RootsError):
                resolve_roots(env={})
            with self.assertRaises(RootsError):
                resolve_roots(results_root=os.path.join(d, "does-not-exist"), env={})
            roots = resolve_roots(results_root=d, cache_root=os.path.join(d, "cache"), env={})
            self.assertTrue(roots.cache_root.is_dir())

    def test_non_empty_run_dir_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            run(EXAMPLE, results_root=d, offline=True, run_id="dup")
            with self.assertRaises(RootsError):
                run(EXAMPLE, results_root=d, offline=True, run_id="dup")


class CliTests(unittest.TestCase):
    def run_cli(self, argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("SOMAWEAVE_")}
        os.environ.update(env or {})
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = main(argv)
        finally:
            for k in list(os.environ):
                if k.startswith("SOMAWEAVE_"):
                    del os.environ[k]
            os.environ.update(saved)
        return rc, out.getvalue(), err.getvalue()

    def test_interpret_case_offline_ok(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = self.run_cli(["interpret-case", str(EXAMPLE), "--results-root", d, "--offline", "--run-id", "cli"])
            self.assertEqual(rc, 0, err)
            self.assertIn("run cli complete", out)
            self.assertTrue((Path(d) / "cli" / "manifest.json").exists())

    def test_results_root_from_env(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, _ = self.run_cli(["interpret-case", str(EXAMPLE), "--offline", "--run-id", "env"], env={"SOMAWEAVE_RESULTS_ROOT": d})
            self.assertEqual(rc, 0)
            manifest = json.loads((Path(d) / "env" / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("SOMAWEAVE_RESULTS_ROOT", manifest["environment_variable_names"])

    def test_usage_errors_exit_2(self):
        rc, _, err = self.run_cli(["interpret-case", "/nonexistent/case.json", "--offline"])
        self.assertEqual(rc, 2)
        rc, _, err = self.run_cli(["interpret-case", str(EXAMPLE), "--offline"])
        self.assertEqual(rc, 2)
        self.assertIn("results root", err)

    def test_invalid_case_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text(json.dumps({"case_id": "X"}), encoding="utf-8")
            rc, _, err = self.run_cli(["interpret-case", str(bad), "--results-root", d, "--offline"])
            self.assertEqual(rc, 1)
            self.assertIn("invalid case", err)

    def test_validate_case_unchanged(self):
        rc, out, _ = self.run_cli(["validate-case", str(EXAMPLE), "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["case_id"], "SYN-0001")


if __name__ == "__main__":
    unittest.main()
