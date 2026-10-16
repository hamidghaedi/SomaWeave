import json
import unittest
from pathlib import Path

from somaweave.normalization.hgvs import ParsedCodingChange, ParsedProteinChange, parse_coding_hgvs, parse_protein_hgvs

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "normalization"
CASES = json.loads((FIXTURES / "hgvs_cases.json").read_text(encoding="utf-8"))


class ProteinHgvsTests(unittest.TestCase):
    def test_table_driven_valid(self):
        self.assertGreaterEqual(len(CASES["protein"]), 20)
        for row in CASES["protein"]:
            with self.subTest(hgvs=row["input"]):
                parsed, reason = parse_protein_hgvs(row["input"])
                self.assertIsNotNone(parsed, reason)
                self.assertIsInstance(parsed, ParsedProteinChange)
                self.assertEqual(parsed.original, row["input"].strip())
                for key, expected in row.items():
                    if key == "input":
                        continue
                    self.assertEqual(getattr(parsed, key), expected, f"{row['input']}: {key}")

    def test_table_driven_invalid_returns_none_with_reason(self):
        for text in CASES["protein_invalid"]:
            with self.subTest(hgvs=text):
                parsed, reason = parse_protein_hgvs(text)
                self.assertIsNone(parsed)
                self.assertTrue(reason)

    def test_none_input(self):
        parsed, reason = parse_protein_hgvs(None)
        self.assertIsNone(parsed)
        self.assertIn("no protein HGVS", reason)

    def test_canonical_forms_are_idempotent(self):
        for row in CASES["protein"]:
            parsed, _ = parse_protein_hgvs(row["input"])
            again, _ = parse_protein_hgvs(parsed.three_letter)
            self.assertIsNotNone(again, parsed.three_letter)
            self.assertEqual(again.three_letter, parsed.three_letter)
            self.assertEqual(again.one_letter, parsed.one_letter)
            self.assertEqual(again.kind, parsed.kind)

    def test_nonsense_and_missense_distinguished(self):
        self.assertEqual(parse_protein_hgvs("p.Gln61Ter")[0].kind, "nonsense")
        self.assertEqual(parse_protein_hgvs("p.Gln61Leu")[0].kind, "missense")

    def test_frameshift_without_stop_offset(self):
        parsed, _ = parse_protein_hgvs("p.Arg123fs")
        self.assertIsNone(parsed.frameshift_stop_offset)
        self.assertIsNone(parsed.alt_aa)

    def test_model_is_strict(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ParsedProteinChange(original="x", kind="missense", ref_aa="Asp", position=1, codon_label="D1",
                                one_letter="p.D1N", three_letter="p.Asp1Asn", unexpected=1)


class CodingHgvsTests(unittest.TestCase):
    def test_table_driven_valid(self):
        for row in CASES["coding"]:
            with self.subTest(hgvs=row["input"]):
                parsed, reason = parse_coding_hgvs(row["input"])
                self.assertIsNotNone(parsed, reason)
                self.assertIsInstance(parsed, ParsedCodingChange)
                self.assertEqual(parsed.original, row["input"])
                for key, expected in row.items():
                    if key == "input":
                        continue
                    self.assertEqual(getattr(parsed, key), expected, f"{row['input']}: {key}")

    def test_table_driven_invalid(self):
        for text in CASES["coding_invalid"]:
            with self.subTest(hgvs=text):
                parsed, reason = parse_coding_hgvs(text)
                self.assertIsNone(parsed)
                self.assertTrue(reason)

    def test_default_prefix_is_coding(self):
        parsed, _ = parse_coding_hgvs("c.94G>A")
        self.assertEqual(parsed.prefix, "c")
        self.assertIsNone(parsed.end)
        self.assertIsNone(parsed.end_base)


if __name__ == "__main__":
    unittest.main()
