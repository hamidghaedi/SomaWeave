"""Condition-term hierarchy for registry queries (diagnosis -> OncoTree node -> lineage -> basket)."""

import unittest

from somaweave.normalization.disease import BUILTIN_ONCOTREE, OncoTreeNode, OncoTreeTable, condition_hierarchy
from somaweave.domain.io import load_case
from somaweave.retrieval.plan import build_query_plan
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConditionHierarchyTests(unittest.TestCase):
    def test_breast_idc_levels(self):
        levels = condition_hierarchy("Breast carcinoma", "IDC", BUILTIN_ONCOTREE)
        self.assertEqual(levels, [
            {"level": "diagnosis", "term": "Breast carcinoma"},
            {"level": "oncotree", "term": "Breast Invasive Ductal Carcinoma"},
            {"level": "lineage", "term": "Invasive Breast Carcinoma"},
            {"level": "basket", "term": "Solid Tumor"},
        ])

    def test_tissue_level_node_skipped_and_duplicates_removed(self):
        levels = condition_hierarchy("Pancreatic Adenocarcinoma", "PAAD", BUILTIN_ONCOTREE)
        self.assertEqual([l["level"] for l in levels], ["diagnosis", "basket"])  # name equals node name; "Pancreas" tissue skipped

    def test_no_code_gives_diagnosis_and_solid_basket(self):
        self.assertEqual(condition_hierarchy("Omental tumour", None, BUILTIN_ONCOTREE),
                         [{"level": "diagnosis", "term": "Omental tumour"}, {"level": "basket", "term": "Solid Tumor"}])
        self.assertEqual(condition_hierarchy("X", "NOPE", BUILTIN_ONCOTREE)[-1]["term"], "Solid Tumor")

    def test_heme_basket(self):
        table = OncoTreeTable([OncoTreeNode(code="TISSUE", name="Tissue"), OncoTreeNode(code="LYMPH", name="Lymphoid", parent="TISSUE"),
                               OncoTreeNode(code="DLBCL", name="Diffuse Large B-Cell Lymphoma", parent="LYMPH")], source="test")
        levels = condition_hierarchy("DLBCL", "DLBCL", table)
        self.assertEqual(levels[-1], {"level": "basket", "term": "Hematologic Malignancy"})
        self.assertNotIn("Lymphoid", [l["term"] for l in levels])

    def test_planner_merges_extra_terms_into_every_tier(self):
        case = load_case(ROOT / "examples" / "synthetic_case.json")
        extra = {"condition_hierarchy": condition_hierarchy(case.diagnosis.name, case.diagnosis.oncotree_code, BUILTIN_ONCOTREE)}
        plan = build_query_plan(case, case.alterations[0], extra_terms=extra)
        self.assertTrue(all(it.terms.get("condition_hierarchy") == extra["condition_hierarchy"] for it in plan))
        self.assertTrue(all("disease" in it.terms for it in plan))


if __name__ == "__main__":
    unittest.main()
