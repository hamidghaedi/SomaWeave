import unittest
from datetime import date
from pathlib import Path

from somaweave.domain import Case
from somaweave.domain.io import dump_model, load_case
from somaweave.normalization import NormalizedCase, normalize_case
from somaweave.normalization.dates import days_between, parse_partial_date
from somaweave.normalization.genes import load_hgnc_previous_symbols, normalize_gene_symbol

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic_case.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "normalization"


class GeneSymbolTests(unittest.TestCase):
    def test_builtin_aliases(self):
        for raw, expected in [("MLL", "KMT2A"), ("MLL2", "KMT2D"), ("C11orf30", "EMSY"), ("FAM123B", "AMER1"),
                              ("MYCL1", "MYCL"), ("PARK2", "PRKN"), (" mll ", "KMT2A")]:
            with self.subTest(raw=raw):
                g = normalize_gene_symbol(raw)
                self.assertEqual(g.normalized, expected)
                self.assertTrue(g.alias_applied)
                self.assertEqual(g.alias_source, "builtin")
                self.assertEqual(g.original, raw.strip())

    def test_current_symbol_passes_through(self):
        g = normalize_gene_symbol("tp53")
        self.assertEqual(g.normalized, "TP53")
        self.assertFalse(g.alias_applied)
        self.assertEqual(g.original, "tp53")
        self.assertIsNone(normalize_gene_symbol(None))

    def test_hgnc_table_hook(self):
        table = load_hgnc_previous_symbols(FIXTURES / "hgnc_subset.tsv")
        self.assertEqual(table["MLL"], "KMT2A")
        self.assertEqual(table["MLL2"], "KMT2D")
        self.assertNotIn("MLL4", table)  # ambiguous between KMT2B and KMT2D, dropped
        self.assertIn("MLL4", table["__ambiguous__"])
        g = normalize_gene_symbol("MLL2", table)
        self.assertEqual((g.normalized, g.alias_source), ("KMT2D", "hgnc_table"))
        # with aliases included, MLL2 becomes ambiguous and falls back to the built-in table
        table2 = load_hgnc_previous_symbols(FIXTURES / "hgnc_subset.tsv", include_alias_symbols=True)
        self.assertNotIn("MLL2", table2)
        self.assertEqual(normalize_gene_symbol("MLL2", table2).alias_source, "builtin")


class PartialDateTests(unittest.TestCase):
    def test_precisions(self):
        d, _ = parse_partial_date("2024-03-12")
        self.assertEqual((d.precision, d.year, d.month, d.day), ("day", 2024, 3, 12))
        m, _ = parse_partial_date("2024-03")
        self.assertEqual((m.precision, m.day), ("month", None))
        self.assertEqual((m.earliest(), m.latest()), (date(2024, 3, 1), date(2024, 3, 31)))
        y, _ = parse_partial_date("2024")
        self.assertEqual((y.precision, y.month, y.day), ("year", None, None))
        self.assertEqual(y.latest(), date(2024, 12, 31))
        self.assertEqual(y.iso(), "2024")
        self.assertEqual(parse_partial_date(date(2025, 7, 2))[0].precision, "day")

    def test_rejects_ambiguous_or_invalid(self):
        for text in ["03/12/2024", "12 Mar 2024", "2024-13", "2024-02-30", "", "20240312"]:
            with self.subTest(text=text):
                d, reason = parse_partial_date(text)
                self.assertIsNone(d)
                self.assertTrue(reason)
        self.assertIsNone(parse_partial_date(None)[0])

    def test_days_between_precision_aware(self):
        a, _ = parse_partial_date("2025-02-03")
        b, _ = parse_partial_date("2025-06-15")
        iv = days_between(a, b)
        self.assertEqual((iv.days_min, iv.days_max, iv.days_exact, iv.precision), (132, 132, 132, "day"))
        m, _ = parse_partial_date("2025-02")
        iv2 = days_between(m, b)
        self.assertEqual((iv2.days_min, iv2.days_max, iv2.days_exact, iv2.precision), (107, 134, None, "month"))
        y, _ = parse_partial_date("2024")
        iv3 = days_between(y, m)
        self.assertEqual(iv3.precision, "year")
        self.assertIsNone(iv3.days_exact)
        self.assertLess(iv3.days_min, iv3.days_max)
        # reversed order gives negative bounds rather than raising
        self.assertLess(days_between(b, a).days_max, 0)


class NormalizeCaseTests(unittest.TestCase):
    def setUp(self):
        self.case = load_case(EXAMPLE)
        self.norm = normalize_case(self.case)

    def test_original_case_unchanged_and_accessible(self):
        self.assertIsInstance(self.norm, NormalizedCase)
        self.assertIs(self.norm.case, self.case)
        self.assertEqual(dump_model(self.norm.case), dump_model(load_case(EXAMPLE)))
        self.assertEqual(self.norm.assembly, self.case.assembly)

    def test_alterations_parsed(self):
        a1 = self.norm.alteration("A1")
        self.assertEqual(a1.gene.normalized, "CTNNB1")
        self.assertEqual(a1.protein.codon_label, "D32")
        self.assertEqual(a1.protein.one_letter, "p.D32N")
        self.assertEqual(a1.coding.start_base, 94)
        self.assertEqual(a1.coding.alternate, "A")
        a2 = self.norm.alteration("A2")
        self.assertEqual(a2.protein.codon_label, "G719")
        self.assertEqual([f.code for f in a2.flags], [])
        self.assertNotIn("hgvs_c_p_codon_mismatch", [f.code for f in self.norm.flags])

    def test_disease_flags_propagated(self):
        codes = [f.code for f in self.norm.flags if f.subject == "diagnosis"]
        self.assertIn("morphology_oncotree_consistent", codes)
        self.assertIn("hypothesis_unconfirmed", codes)
        self.assertEqual(self.norm.disease.confirmed_oncotree_code, "SPN")

    def test_treatment_and_specimen_chronology(self):
        tx = self.norm.treatments[0]
        self.assertEqual(tx.duration.days_exact, 132)
        timing = {t.specimen_id: t for t in tx.specimen_timing}
        self.assertEqual(set(timing), {"T1"})  # tumour specimens only
        self.assertEqual(timing["T1"].days_from_treatment_end.days_exact, 17)
        self.assertEqual(timing["T1"].days_from_treatment_start.days_exact, 149)

    def test_unparseable_and_alias_flags(self):
        data = self.case.model_dump()
        data["alterations"][0]["hgvs_p"] = "p.Asp32"
        data["alterations"][0]["gene_symbol"] = "MLL"
        data["alterations"][1]["hgvs_c"] = "c.2200G>A"  # codon 734, conflicts with p.Gly719Ser
        norm = normalize_case(Case.model_validate(data))
        a1 = norm.alteration("A1")
        self.assertIsNone(a1.protein)
        self.assertTrue(a1.protein_parse_reason)
        codes1 = [f.code for f in a1.flags]
        self.assertIn("hgvs_p_unparsed", codes1)
        self.assertIn("gene_alias_applied", codes1)
        self.assertEqual(a1.gene.normalized, "KMT2A")
        self.assertEqual(a1.gene.original, "MLL")
        self.assertEqual(norm.case.alterations[0].gene_symbol, "MLL")
        a2 = norm.alteration("A2")
        conflict = [f for f in a2.flags if f.code == "hgvs_c_p_codon_mismatch"]
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0].severity, "conflict")

    def test_ongoing_with_end_date_is_conflict(self):
        data = self.case.model_dump()
        data["treatments"][0]["ongoing"] = True
        norm = normalize_case(Case.model_validate(data))
        self.assertIn("treatment_end_vs_ongoing", [f.code for f in norm.flags])

    def test_serialisable(self):
        payload = dump_model(self.norm)
        self.assertEqual(payload["case"]["case_id"], "SYN-0001")
        self.assertEqual(payload["disease"]["confirmed_oncotree_code"], "SPN")


if __name__ == "__main__":
    unittest.main()
