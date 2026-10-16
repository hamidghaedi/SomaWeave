"""Tests for somaweave.reporting renderers (offline, recorded fixtures)."""

import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from somaweave import __version__
from somaweave.domain import FindingAssessment
from somaweave.domain.io import load_case
from somaweave.evidence import reconcile
from somaweave.interpretation import interpret
from somaweave.normalization import normalize_case
from somaweave.reporting import RESEARCH_USE_BANNER, RunBundle, render_json, render_markdown
from somaweave.reporting.render_markdown import AXIS_HEADINGS
from somaweave.retrieval import RetrievalResult
from somaweave.technical import assess_alteration, technical_summary

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "evidence" / "retrieval_ctnnb1_d32n.json"
CITED = re.compile(r"\[[^\[\]]+\]\s*$")


def _bundle(offline=False):
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    nc = normalize_case(case)
    alt = case.alterations[0]
    rr = RetrievalResult.model_validate_json(FIX.read_text(encoding="utf-8"))
    es = reconcile(nc, alt, rr)
    fa = interpret(nc, alt, assess_alteration(case, alt), es)
    return RunBundle(run_id="test-run", generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc), somaweave_version=__version__, offline=offline,
                     case=nc, technical_summary=technical_summary(case), evidence_sets=[es], findings=[fa],
                     provenance={"python_version": "3.11", "input_sha256": "abc"}), fa, es


def _section(md: str, heading: str) -> str:
    start = md.index(heading) + len(heading)
    rest = md[start:]
    m = re.search(r"\n#{2,4} ", rest)
    return rest[: m.start()] if m else rest


class MarkdownTests(unittest.TestCase):
    def test_structure_and_citations(self):
        bundle, fa, es = _bundle()
        md = render_markdown(bundle)
        self.assertTrue(md.startswith("# SomaWeave research interpretation report"))
        self.assertIn(RESEARCH_USE_BANNER, md)
        for heading in AXIS_HEADINGS.values():
            self.assertEqual(md.count(f"#### {heading}"), 1)
        for h in ("#### Established claims", "#### Hypotheses and non-curated signals", "#### Evidence table", "#### Source coverage",
                  "#### Limitations", "#### Review flags", "## Methods and versions", "## Case summary"):
            self.assertIn(h, md)
        claims = [ln for ln in _section(md, "#### Established claims").splitlines() if ln.startswith("- ")]
        self.assertTrue(claims)
        for ln in claims:
            self.assertRegex(ln, CITED)
        hyps = [ln for ln in _section(md, "#### Hypotheses and non-curated signals").splitlines() if ln.startswith("- ")]
        for ln in hyps:
            self.assertTrue(ln.endswith("[hypothesis]"), ln)
        # evidence table lists every record with its native level verbatim
        for r in es.records:
            self.assertIn(r.evidence_id, md)
        self.assertIn("| A / submitted; significance=SENSITIVITYRESPONSE |", md)
        self.assertIn("| civic | ok |", md)

    def test_uncited_claims_are_withheld(self):
        bundle, fa, es = _bundle()
        fa2 = fa.model_copy(update={"established_claims": list(fa.established_claims) + ["An uncited statement that must not appear"]})
        md = render_markdown(bundle.model_copy(update={"findings": [fa2]}))
        self.assertNotIn("An uncited statement that must not appear", md)
        self.assertIn("1 statement(s) without an evidence citation were withheld", md)

    def test_missing_source_rendering(self):
        bundle, fa, es = _bundle(offline=True)
        md = render_markdown(bundle)
        self.assertIn("Mode: offline", md)


class JsonTests(unittest.TestCase):
    def test_json_is_serialisable_and_complete(self):
        bundle, fa, es = _bundle()
        obj = render_json(bundle)
        text = json.dumps(obj)
        self.assertTrue(obj["research_use_only"])
        self.assertEqual(obj["run_id"], "test-run")
        self.assertEqual(obj["case_summary"]["case_id"], "SYN-0001")
        self.assertEqual(len(obj["findings"]), 1)
        f = obj["findings"][0]
        self.assertEqual(FindingAssessment.model_validate(f["assessment"]).alteration_id, "A1")
        self.assertEqual(len(f["evidence_records"]), len(es.records))
        self.assertEqual(len(f["source_query_results"]), len(es.query_results))
        self.assertEqual(set(f["provenance"]), {r.evidence_id for r in es.records})
        self.assertIn("level_rules", obj["technical_summary"])
        self.assertEqual(obj["provenance"]["input_sha256"], "abc")
        self.assertIn("source_coverage", f)
        self.assertNotIn("hostname", text)


if __name__ == "__main__":
    unittest.main()
