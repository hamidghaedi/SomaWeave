import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from somaweave.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic_case.json"


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_validate_example_ok(self):
        rc, out, _ = self.run_cli(["validate-case", str(EXAMPLE), "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["case_id"], "SYN-0001")

    def test_validate_invalid_case(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text(json.dumps({"case_id": "X"}), encoding="utf-8")
            rc, _, err = self.run_cli(["validate-case", str(p)])
        self.assertEqual(rc, 1)
        self.assertIn("invalid case", err)

    def test_missing_file(self):
        rc, _, err = self.run_cli(["validate-case", "/nonexistent/case.json"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
