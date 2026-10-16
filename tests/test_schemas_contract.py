"""Contract tests: committed JSON Schemas match the models, and the example
validates against the committed schema with an independent validator."""

import json
import unittest
from pathlib import Path

import jsonschema

from somaweave.domain.io import SCHEMA_VERSIONS, case_json_schema, evidence_json_schema

ROOT = Path(__file__).resolve().parents[1]


class SchemaContractTests(unittest.TestCase):
    def _committed(self, name: str) -> dict:
        path = ROOT / "schemas" / f"{name}.{SCHEMA_VERSIONS[name]}.schema.json"
        self.assertTrue(path.exists(), f"missing {path}; run scripts/export_schemas.py")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_case_schema_up_to_date(self):
        self.assertEqual(self._committed("case"), json.loads(json.dumps(case_json_schema())))

    def test_evidence_schema_up_to_date(self):
        self.assertEqual(self._committed("evidence"), json.loads(json.dumps(evidence_json_schema())))

    def test_example_validates_against_committed_schema(self):
        schema = self._committed("case")
        example = json.loads((ROOT / "examples" / "synthetic_case.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(example, schema)

    def test_assessment_has_no_composite_score(self):
        from somaweave.domain.assessment import FindingAssessment
        fields = set(FindingAssessment.model_fields)
        for forbidden in ("score", "confidence", "overall", "composite"):
            self.assertFalse(any(forbidden in f for f in fields), f"forbidden composite field: {forbidden}")


if __name__ == "__main__":
    unittest.main()
