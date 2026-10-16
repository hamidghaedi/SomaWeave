import json
import unittest
from pathlib import Path

from somaweave.domain import DiseaseMatch
from somaweave.domain.io import load_case
from somaweave.normalization.disease import (
    BUILTIN_ONCOTREE,
    ICDO_MORPHOLOGY_TO_ONCOTREE,
    build_disease_context,
    disease_match,
    load_oncotree_json,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic_case.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "normalization"


class DiseaseMatchTests(unittest.TestCase):
    def test_match_table(self):
        table = [
            ("SPN", "SPN", DiseaseMatch.SAME),
            ("spn", "Solid Pseudopapillary Neoplasm of the Pancreas", DiseaseMatch.SAME),
            ("SPN", "PANCREAS", DiseaseMatch.PARENT),
            ("PAAD", "Pancreas", DiseaseMatch.PARENT),
            ("LUAD", "NSCLC", DiseaseMatch.PARENT),
            ("LUAD", "LUNG", DiseaseMatch.PARENT),
            ("LUSC", "Non-Small Cell Lung Cancer", DiseaseMatch.PARENT),
            ("COAD", "COADREAD", DiseaseMatch.PARENT),
            ("READ", "BOWEL", DiseaseMatch.PARENT),
            ("BLCA", "BLADDER", DiseaseMatch.PARENT),
            ("SKCM", "MEL", DiseaseMatch.PARENT),
            ("GBM", "GLIOMA", DiseaseMatch.PARENT),
            ("GBM", "All Solid Tumors", DiseaseMatch.PAN_CANCER),
            ("GBM", "pan-cancer", DiseaseMatch.PAN_CANCER),
            ("GBM", "TISSUE", DiseaseMatch.PAN_CANCER),
            ("SPN", "PAAD", DiseaseMatch.RELATED),
            ("LUAD", "LUSC", DiseaseMatch.RELATED),
            ("NSCLC", "LUAD", DiseaseMatch.RELATED),
            ("LUAD", "Colon Adenocarcinoma", DiseaseMatch.DIFFERENT),
            ("SPN", "BLCA", DiseaseMatch.DIFFERENT),
            ("LUAD", "unknown entity", DiseaseMatch.UNKNOWN),
            ("ZZZ", "LUAD", DiseaseMatch.UNKNOWN),
            (None, "LUAD", DiseaseMatch.UNKNOWN),
            ("LUAD", None, DiseaseMatch.UNKNOWN),
            ("LUAD", "", DiseaseMatch.UNKNOWN),
        ]
        for case_code, evidence, expected in table:
            with self.subTest(case=case_code, evidence=evidence):
                self.assertEqual(disease_match(case_code, evidence), expected)

    def test_unresolvable_is_never_different(self):
        self.assertNotEqual(disease_match("LUAD", "some rare entity"), DiseaseMatch.DIFFERENT)

    def test_builtin_table_size_and_root(self):
        self.assertGreaterEqual(len(BUILTIN_ONCOTREE._nodes), 25)
        self.assertEqual(BUILTIN_ONCOTREE.ancestors("LUAD"), ["NSCLC", "LUNG", "TISSUE"])
        self.assertEqual(BUILTIN_ONCOTREE.ancestors("TISSUE"), [])


class OncoTreeLoaderTests(unittest.TestCase):
    def test_load_public_format(self):
        table = load_oncotree_json(FIXTURES / "oncotree_subset.json")
        self.assertIn("UCP", table)
        self.assertEqual(table.ancestors("UCP"), ["PANCREAS", "TISSUE"])
        self.assertEqual(disease_match("UCP", "PANCREAS", table), DiseaseMatch.PARENT)
        self.assertEqual(disease_match("UCP", "LUAD", table), DiseaseMatch.UNKNOWN)
        self.assertEqual(table.resolve("pancreatic adenocarcinoma"), "PAAD")

    def test_rejects_malformed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text(json.dumps({"foo": 1}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_oncotree_json(p)


class DiseaseContextTests(unittest.TestCase):
    def test_synthetic_case_consistent_morphology_and_flagged_hypothesis(self):
        case = load_case(EXAMPLE)
        ctx = build_disease_context(case)
        self.assertEqual(ctx.confirmed_oncotree_code, "SPN")
        self.assertEqual(ctx.icd_o_morphology, "8452/3")
        self.assertEqual(ctx.confirmed_lineage, ["PANCREAS", "TISSUE"])
        codes = [f.code for f in ctx.flags]
        self.assertIn("morphology_oncotree_consistent", codes)
        self.assertNotIn("morphology_oncotree_conflict", codes)
        self.assertFalse(ctx.has_conflicts())
        self.assertEqual(len(ctx.hypotheses), 1)
        hyp = ctx.hypotheses[0]
        self.assertEqual(hyp.oncotree_code, "PAAC")
        self.assertEqual(hyp.relation_to_confirmed, DiseaseMatch.RELATED)
        self.assertIn("hypothesis_unconfirmed", codes)
        # the confirmed diagnosis is untouched
        self.assertEqual(case.diagnosis.oncotree_code, "SPN")
        self.assertEqual(ctx.confirmed_name, case.diagnosis.name)

    def test_morphology_conflict_is_flagged_not_corrected(self):
        case = load_case(EXAMPLE)
        data = case.model_dump()
        data["diagnosis"]["icd_o_morphology"] = "8453/3"
        from somaweave.domain import Case
        conflicted = Case.model_validate(data)
        ctx = build_disease_context(conflicted)
        conflicts = [f for f in ctx.flags if f.code == "morphology_oncotree_conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "conflict")
        self.assertIn("IPMN", conflicts[0].message)
        self.assertTrue(ctx.has_conflicts())
        self.assertEqual(ctx.confirmed_oncotree_code, "SPN")

    def test_morphology_outside_map_is_not_assessed(self):
        case = load_case(EXAMPLE)
        data = case.model_dump()
        data["diagnosis"]["icd_o_morphology"] = "9999/3"
        from somaweave.domain import Case
        ctx = build_disease_context(Case.model_validate(data))
        codes = [f.code for f in ctx.flags]
        self.assertIn("morphology_not_assessed", codes)
        self.assertNotIn("morphology_oncotree_conflict", codes)

    def test_missing_code_flagged(self):
        case = load_case(EXAMPLE)
        data = case.model_dump()
        data["diagnosis"]["oncotree_code"] = None
        from somaweave.domain import Case
        ctx = build_disease_context(Case.model_validate(data))
        self.assertIn("oncotree_code_missing", [f.code for f in ctx.flags])
        self.assertEqual(ctx.hypotheses[0].relation_to_confirmed, DiseaseMatch.UNKNOWN)

    def test_builtin_morphology_map_entries(self):
        self.assertEqual(ICDO_MORPHOLOGY_TO_ONCOTREE["8452/3"], ("SPN",))
        self.assertIn("PAAD", ICDO_MORPHOLOGY_TO_ONCOTREE["8140/3"])
        self.assertIn("LUSC", ICDO_MORPHOLOGY_TO_ONCOTREE["8070/3"])


if __name__ == "__main__":
    unittest.main()
