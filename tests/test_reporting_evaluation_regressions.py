"""Rendering regressions from the real-case evaluation: hypothesis rationale, partial dates, planner exclusion."""

import json
import tempfile
import unittest
from pathlib import Path

from somaweave.domain import Case
from somaweave.domain.io import load_case
from somaweave.workflows.interpret_case import run

ROOT = Path(__file__).resolve().parents[1]


def _case():
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    data = case.model_dump(mode="json", exclude_none=True)
    data["diagnosis"].update({"name": "Pancreatic tumour, morphology 8453/3", "icd_o_morphology": "8453/3"})
    data["diagnosis"].pop("oncotree_code", None)
    data["disease_hypotheses"] = [{"name": "Solid pseudopapillary neoplasm of the pancreas", "oncotree_code": "SPN", "proposed_by": "record review",
                                   "rationale": "recorded morphology 8453/3 versus 8452/3 expected for SPN; pathology review required to reconcile the coding"}]
    data["specimens"][0]["collection_date"] = "2025-07"
    data["specimens"][0]["notes"] = "original collection month 2025-07; frozen storage of the FFPE block noted"
    data["treatments"][0].update({"start_date": "2025-02", "end_date": "2025-06", "response_notes": "systemic therapy; response not recorded"})
    return Case.model_validate(data)


class RenderingRegressionTests(unittest.TestCase):
    def test_report_carries_hypothesis_rationale_partial_dates_and_notes(self):
        case = _case()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "case.json"
            p.write_text(json.dumps(case.model_dump(mode="json", exclude_none=True)), encoding="utf-8")
            (Path(d) / "out").mkdir()
            res = run(p, results_root=Path(d) / "out", offline=True, run_id="render-regression")
            md = res.report_markdown_path.read_text(encoding="utf-8")
            rep = json.loads(res.report_json_path.read_text(encoding="utf-8"))
        self.assertIn("8452/3", md)
        self.assertIn("pathology review required", md)
        self.assertIn("2025-07", md)
        self.assertNotIn("2025-07-01", md)
        self.assertIn("frozen storage", md)
        self.assertIn("response not recorded", md)
        self.assertIn("2025-02 to 2025-06", md)
        self.assertNotIn("planner", md.split("#### Source coverage")[0])
        self.assertNotIn("findings describe metastatic disease", md)
        self.assertIn("recorded as metastatic site", md)
        hyp = rep["case_summary"]["disease_hypotheses"][0]
        self.assertIn("8452/3", hyp["rationale"])
        self.assertEqual(rep["case_summary"]["specimens"][0]["collection_date"], "2025-07")
        self.assertIn("excluded_by_class", rep["findings"][0])


if __name__ == "__main__":
    unittest.main()
