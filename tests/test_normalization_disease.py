import json
import unittest
from pathlib import Path

from somaweave.domain import DiseaseMatch
from somaweave.domain.io import load_case
from somaweave.normalization.disease import (
    BUILTIN_ONCOTREE,
    DISEASE_NAME_SYNONYMS,
    DOID_TO_ONCOTREE,
    ICDO_MORPHOLOGY_TO_ONCOTREE,
    PAN_CANCER_CODE,
    OncoTreeIndex,
    build_disease_context,
    disease_match,
    disease_match_detail,
    find_oncotree_json,
    load_oncotree_json,
    normalize_disease_name,
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



class NameNormalizationTests(unittest.TestCase):
    def test_normalize_disease_name(self):
        self.assertEqual(normalize_disease_name("Acinar Cell Carcinoma of the Pancreas, NOS"), "acinar cell carcinoma pancreas")
        self.assertEqual(normalize_disease_name("Lung Non-small Cell Carcinoma"), "lung non small cell carcinoma")
        self.assertEqual(normalize_disease_name("All Solid Tumours"), "all solid tumor")
        self.assertEqual(normalize_disease_name("CNS/Brain"), "cns brain")
        self.assertEqual(normalize_disease_name("  Melanoma "), "melanoma")

    def test_tables_are_well_formed(self):
        for key, codes in DISEASE_NAME_SYNONYMS.items():
            self.assertEqual(key, normalize_disease_name(key), key)
            self.assertTrue(codes and all(c == c.upper() for c in codes), key)
        self.assertGreaterEqual(len(DISEASE_NAME_SYNONYMS), 30)
        for doid, codes in DOID_TO_ONCOTREE.items():
            self.assertTrue(doid.startswith("DOID:"), doid)
            self.assertTrue(codes, doid)
        self.assertEqual(DOID_TO_ONCOTREE["DOID:162"], (PAN_CANCER_CODE,))


class OncoTreeIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.five = load_oncotree_json(FIXTURES / "oncotree_subset.json")
        cls.idx = load_oncotree_json(FIXTURES / "oncotree_subset_41.json")

    def test_loader_returns_index_with_checksum(self):
        self.assertIsInstance(self.five, OncoTreeIndex)
        self.assertEqual(self.five.node_count, 5)
        self.assertEqual(len(self.five.sha256), 64)
        self.assertIsNone(self.five.version)  # no version stamp in the file name
        self.assertEqual(self.idx.node_count, 41)
        self.assertEqual(self.idx.codes()[:3], ["ADIFG", "ADNOS", "BOWEL"])
        self.assertEqual(self.idx.node("GB").external_references["NCI"], ["C3058"])
        self.assertEqual(self.idx.node("DES").external_references["DOID"], ["DOID:0080366"])
        self.assertEqual(self.idx.node("GB").level, 4)

    def test_builtin_is_an_index(self):
        self.assertIsInstance(BUILTIN_ONCOTREE, OncoTreeIndex)
        self.assertEqual(BUILTIN_ONCOTREE.source, "builtin-subset")
        self.assertEqual(BUILTIN_ONCOTREE.tissue("LUAD"), "LUNG")
        self.assertEqual(BUILTIN_ONCOTREE.tissue("PANCREAS"), "PANCREAS")
        self.assertIsNone(BUILTIN_ONCOTREE.tissue("TISSUE"))

    def test_ancestors_and_tissue_without_root_node(self):
        # the public file has no TISSUE node; level-1 nodes point at it
        self.assertEqual(self.idx.ancestors("GB"), ["ADIFG", "DIFG", "BRAIN", "TISSUE"])
        self.assertEqual(self.idx.ancestors("LUNG"), ["TISSUE"])
        self.assertEqual(self.idx.tissue("GB"), "BRAIN")
        self.assertEqual(self.idx.tissue("LUAD"), "LUNG")
        self.assertEqual(self.idx.tissue("LUNG"), "LUNG")
        self.assertIsNone(self.idx.tissue("NOT_A_CODE"))

    def test_name_resolution_paths(self):
        cases = [
            ("LUAD", None, "LUAD", "code"),
            ("tissue", None, PAN_CANCER_CODE, "code"),
            ("Non-Small Cell Lung Cancer", None, "NSCLC", "name"),
            ("Acinar cell carcinoma of the pancreas, NOS", None, "PAAC", "name"),
            ("Hepatocellular Cancer", None, "HCC", "name"),          # carcinoma/cancer variant
            ("Lung Non-small Cell Carcinoma", None, "NSCLC", "synonym"),
            ("Colorectal Cancer", None, "COADREAD", "synonym"),
            ("Glioblastoma", None, "GB", "synonym"),                 # 2025 code; GBM absent from this file
            ("Pancreatic Cancer", None, "PANCREAS", "synonym"),
            ("Solid Tumor", None, PAN_CANCER_CODE, "pan_cancer"),
            ("All Solid Tumours", None, PAN_CANCER_CODE, "pan_cancer"),
            ("Cancer", None, PAN_CANCER_CODE, "pan_cancer"),
            ("Cancer of Unknown Primary", None, "CUP", "name"),      # not pan-cancer
            ("Embryonal Tumor", None, "EMBT", "name"),
            ("Stomach Cancer", None, None, "unresolved"),
            ("Mixed Germ Cell Tumor", None, None, "name_ambiguous"),
            ("Desmoid Tumor", "DOID:0080366", "DES", "doid"),
            ("Colorectal Cancer", "DOID:9256", "COADREAD", "doid"),
            ("Cancer", "DOID:162", PAN_CANCER_CODE, "doid"),
            (None, "DOID:3068", "GB", "doid"),
            (None, "DOID:99999999", None, "unresolved"),
        ]
        for label, doid, code, path in cases:
            with self.subTest(label=label, doid=doid):
                res = self.idx.resolve_disease(label, doid=doid)
                self.assertEqual((res.code, res.path), (code, path))

    def test_doid_sources(self):
        # file-level externalReferences.DOID beats the built-in bridge
        self.assertEqual(self.idx.resolve_disease("Desmoid Tumor", doid="DOID:0080366").detail, "file cross-reference")
        self.assertEqual(self.idx.resolve_disease("Colorectal Cancer", doid="DOID:9256").detail, "built-in DOID bridge")
        self.assertEqual(self.idx.code_for_doid("doid:9256"), "COADREAD")
        self.assertEqual(self.idx.code_for_doid("DOID_9256"), "COADREAD")
        self.assertIsNone(self.idx.code_for_doid("DOID:1380"))  # UCEC not in this file -> unresolved, not a guess
        self.assertIsNone(self.five.code_for_doid("DOID:9256"))

    def test_ambiguous_name_disambiguated_by_case_tissue(self):
        self.assertEqual(self.idx.codes_for_name("Mixed Germ Cell Tumor"), ["MGCT", "OMGCT"])
        res = self.idx.resolve_disease("Mixed Germ Cell Tumor", case_code="OGCT")
        self.assertEqual((res.code, res.path), ("OMGCT", "name"))
        res = self.idx.resolve_disease("Mixed Germ Cell Tumor", case_code="LUAD")
        self.assertEqual((res.code, res.path), (None, "name_ambiguous"))

    def test_main_type_fallback(self):
        res = self.idx.resolve_disease("Glioma")
        self.assertEqual((res.code, res.path), ("DIFG", "main_type"))
        # a main type sitting exactly on the case code is reported as PARENT, never SAME
        d = disease_match_detail("DIFG", "Glioma", self.idx)
        self.assertEqual((d.match, d.resolution_path), (DiseaseMatch.PARENT, "main_type"))
        self.assertEqual(disease_match("GB", "Glioma", self.idx), DiseaseMatch.PARENT)
        # 'Melanoma' spans skin and eye: the main-type LCA would be the root, so it is not used (name path wins anyway)
        self.assertNotIn("melanoma", self.idx._by_main_type)

    def test_disease_match_detail_relations(self):
        table = [
            ("LUAD", "Lung Non-small Cell Carcinoma", None, DiseaseMatch.PARENT, "synonym"),
            ("LUAD", "Solid Tumor", None, DiseaseMatch.PAN_CANCER, "pan_cancer"),
            ("LUAD", "Lung Cancer", None, DiseaseMatch.PARENT, "synonym"),
            ("LUAD", "LUSC", None, DiseaseMatch.RELATED, "code"),
            ("NSCLC", "Lung Adenocarcinoma", None, DiseaseMatch.RELATED, "name"),
            ("LUAD", "Colorectal Cancer", "DOID:9256", DiseaseMatch.DIFFERENT, "doid"),
            ("SPN", "Pancreatic Cancer", "DOID:1793", DiseaseMatch.PARENT, "doid"),
            ("SPN", "Pancreatic Adenocarcinoma", None, DiseaseMatch.RELATED, "name"),
            ("GB", "Glioblastoma", "DOID:3068", DiseaseMatch.SAME, "doid"),
            ("SKCM", "Uveal Melanoma", None, DiseaseMatch.DIFFERENT, "name"),   # eye vs skin tissue
            ("SKCM", "Melanoma", None, DiseaseMatch.PARENT, "name"),
            ("LUAD", "Mixed Germ Cell Tumor", None, DiseaseMatch.UNKNOWN, "name_ambiguous"),
            ("LUAD", "Juvenile nasopharyngeal angiofibroma", None, DiseaseMatch.UNKNOWN, "unresolved"),
            ("ZZZ", "LUAD", None, DiseaseMatch.UNKNOWN, "code"),
            (None, "LUAD", None, DiseaseMatch.UNKNOWN, "unresolved"),
            ("LUAD", None, None, DiseaseMatch.UNKNOWN, "unresolved"),
        ]
        for case_code, label, doid, match, path in table:
            with self.subTest(case=case_code, label=label, doid=doid):
                d = disease_match_detail(case_code, label, self.idx, doid=doid)
                self.assertEqual((d.match, d.resolution_path), (match, path))
                self.assertEqual(disease_match(case_code, label, self.idx, doid=doid), match)

    def test_unresolved_never_different_in_full_index(self):
        d = disease_match_detail("LUAD", "some rare entity", self.idx)
        self.assertEqual(d.match, DiseaseMatch.UNKNOWN)
        self.assertIsNone(d.evidence_code)

    def test_doid_only_record_resolves_with_builtin_subset(self):
        d = disease_match_detail("SPN", "Colorectal Cancer", doid="DOID:9256")
        self.assertEqual((d.match, d.evidence_code, d.resolution_path), (DiseaseMatch.DIFFERENT, "COADREAD", "doid"))
        d = disease_match_detail("GBM", "Glioblastoma", doid="DOID:3068")  # built-in still uses the pre-2025 code
        self.assertEqual((d.match, d.evidence_code), (DiseaseMatch.SAME, "GBM"))
        d = disease_match_detail("SPN", "Pancreatic Solid Pseudopapillary Carcinoma", doid="DOID:6827")  # Disease Ontology name for SPN
        self.assertEqual((d.match, d.evidence_code, d.resolution_path), (DiseaseMatch.SAME, "SPN", "doid"))
        d = disease_match_detail("SPN", "Pancreatic Solid Pseudopapillary Carcinoma")
        self.assertEqual((d.match, d.resolution_path), (DiseaseMatch.SAME, "synonym"))
        d = disease_match_detail("SPN", "Desmoid Tumor", doid="DOID:0080366")  # DES not in the built-in subset
        self.assertEqual((d.match, d.resolution_path), (DiseaseMatch.UNKNOWN, "unresolved"))

    def test_from_table_wraps_plain_table(self):
        from somaweave.normalization.disease import OncoTreeNode, OncoTreeTable
        plain = OncoTreeTable([OncoTreeNode(code="TISSUE", name="Tissue"), OncoTreeNode(code="LUNG", name="Lung", parent="TISSUE"),
                               OncoTreeNode(code="LUAD", name="Lung Adenocarcinoma", parent="LUNG")], source="plain")
        wrapped = OncoTreeIndex.from_table(plain)
        self.assertEqual(wrapped.source, "plain")
        self.assertEqual(disease_match("LUAD", "Lung Cancer", plain), DiseaseMatch.PARENT)
        self.assertIs(OncoTreeIndex.from_table(wrapped), wrapped)

    def test_disease_context_uses_supplied_index(self):
        case = load_case(EXAMPLE)
        ctx = build_disease_context(case, self.idx)
        self.assertEqual(ctx.oncotree_source, str(FIXTURES / "oncotree_subset_41.json"))
        self.assertEqual(ctx.confirmed_lineage, ["PANCREAS", "TISSUE"])
        self.assertEqual(ctx.hypotheses[0].relation_to_confirmed, DiseaseMatch.RELATED)


class FindOncoTreeJsonTests(unittest.TestCase):
    def test_discovery_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(find_oncotree_json(root))
            (root / "oncotree").mkdir()
            self.assertIsNone(find_oncotree_json(root))
            old = root / "oncotree" / "tumorTypes_oncotree_2021_11_02.json"
            new = root / "oncotree" / "tumorTypes_oncotree_2025_10_03.json"
            old.write_text("[]", encoding="utf-8")
            new.write_text("[]", encoding="utf-8")
            self.assertEqual(find_oncotree_json(root), new)
            plain = root / "oncotree" / "tumorTypes.json"
            plain.write_text("[]", encoding="utf-8")
            self.assertEqual(find_oncotree_json(root), plain)

    def test_version_from_stamped_name(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "tumorTypes_oncotree_2025_10_03.json"
            shutil.copy(FIXTURES / "oncotree_subset_41.json", dst)
            idx = load_oncotree_json(dst)
            self.assertEqual(idx.version, "oncotree_2025_10_03")
            self.assertEqual(idx.path, dst)
            self.assertEqual(idx.source, str(dst))


if __name__ == "__main__":
    unittest.main()
