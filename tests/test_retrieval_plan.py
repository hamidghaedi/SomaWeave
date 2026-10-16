"""Tests for the progressive query planner."""

import unittest
from pathlib import Path

from somaweave.domain import Alteration, AlterationType, Case, Diagnosis, FusionPartner, MatchSpecificity, Specimen, SpecimenRole
from somaweave.domain.io import load_case
from somaweave.retrieval import GENE_PATHWAYS, PlanItem, build_query_plan, protein_change_terms, to_one_letter, to_three_letter

ROOT = Path(__file__).resolve().parents[1]
PLAN_TIERS = [MatchSpecificity.EXACT_VARIANT, MatchSpecificity.CODON, MatchSpecificity.GENE_ALTERATION_CLASS,
              MatchSpecificity.GENE, MatchSpecificity.PATHWAY, MatchSpecificity.DISEASE_ONLY]


def _case(**alt_overrides) -> Case:
    alt = {"alteration_id": "X1", "alteration_type": AlterationType.SNV, "gene_symbol": "KRAS", "hgvs_p": "p.Gly12Asp",
           "hgvs_c": "c.35G>A", "consequence": "missense_variant"}
    alt.update(alt_overrides)
    return Case(case_id="C1", assembly="GRCh38", diagnosis=Diagnosis(name="Colorectal adenocarcinoma", primary_site="colon"),
                specimens=[Specimen(specimen_id="T", role=SpecimenRole.TUMOR)], alterations=[Alteration(**alt)])


class ProteinChangeTermTests(unittest.TestCase):
    def test_three_to_one_letter(self):
        self.assertEqual(to_one_letter("p.Asp32Asn"), "D32N")
        self.assertEqual(to_one_letter("p.(Asp32Asn)"), "D32N")
        self.assertEqual(to_one_letter("p.Arg175His"), "R175H")
        self.assertEqual(to_one_letter("p.Gln61Ter"), "Q61*")
        self.assertEqual(to_one_letter("p.Asp32_Gly34del"), "D32_G34del")
        self.assertEqual(to_one_letter("D32N"), "D32N")

    def test_one_to_three_letter_is_conservative(self):
        self.assertEqual(to_three_letter("D32N"), "Asp32Asn")
        self.assertEqual(to_three_letter("p.D32N"), "Asp32Asn")
        self.assertEqual(to_three_letter("Q61*"), "Gln61Ter")
        self.assertEqual(to_three_letter("E746_A750del"), None)

    def test_terms_and_codon(self):
        t = protein_change_terms("p.Asp32Asn")
        self.assertEqual(t["protein_change"], "D32N")
        self.assertEqual(t["variant_terms"], ["D32N", "p.D32N", "Asp32Asn", "p.Asp32Asn"])
        self.assertEqual(t["codon"], "D32")
        self.assertEqual(t["codon_position"], 32)
        self.assertEqual(t["codon_terms"], ["D32", "Asp32"])
        t = protein_change_terms("p.Glu746_Ala750del")
        self.assertEqual(t["protein_change"], "E746_A750del")
        self.assertNotIn("codon", t)


class BuildQueryPlanTests(unittest.TestCase):
    def test_six_tiers_in_specificity_order(self):
        case = load_case(ROOT / "examples" / "synthetic_case.json")
        plan = build_query_plan(case, case.alterations[0])
        self.assertEqual([it.tier for it in plan], PLAN_TIERS)
        self.assertTrue(all(isinstance(it, PlanItem) for it in plan))
        self.assertTrue(all(it.alteration_id == "A1" and it.case_id == "SYN-0001" for it in plan))
        self.assertTrue(all(it.providers for it in plan), "synthetic case should populate every tier")

    def test_exact_tier_terms(self):
        case = load_case(ROOT / "examples" / "synthetic_case.json")
        exact = build_query_plan(case, case.alterations[0])[0]
        self.assertEqual(exact.terms["gene"], "CTNNB1")
        self.assertEqual(exact.terms["protein_change"], "D32N")
        self.assertEqual(exact.terms["variant_terms"], ["D32N", "p.D32N", "Asp32Asn", "p.Asp32Asn", "c.94G>A"])
        self.assertEqual(exact.terms["hgvs_p"], "p.Asp32Asn")
        self.assertEqual(exact.terms["disease"], "Solid pseudopapillary neoplasm of the pancreas")
        self.assertEqual(exact.terms["oncotree_code"], "SPN")
        self.assertEqual(exact.terms["disease_hypotheses"], ["Pancreatic acinar cell carcinoma"])
        self.assertIn("clinvar", exact.providers)

    def test_tier_terms_and_providers(self):
        case = load_case(ROOT / "examples" / "synthetic_case.json")
        plan = {it.tier: it for it in build_query_plan(case, case.alterations[0])}
        self.assertEqual(plan[MatchSpecificity.CODON].terms["codon"], "D32")
        self.assertNotIn("clinvar", plan[MatchSpecificity.CODON].providers)
        self.assertEqual(plan[MatchSpecificity.GENE_ALTERATION_CLASS].terms["alteration_class"], "missense")
        self.assertEqual(plan[MatchSpecificity.PATHWAY].terms["pathway"], "WNT")
        self.assertIn("APC", plan[MatchSpecificity.PATHWAY].terms["pathway_genes"])
        self.assertEqual(plan[MatchSpecificity.DISEASE_ONLY].terms["treatments"], ["oxaliplatin", "irinotecan", "leucovorin", "fluorouracil"])
        self.assertEqual(plan[MatchSpecificity.DISEASE_ONLY].providers, ["europepmc"])
        self.assertIn("resistance", plan[MatchSpecificity.DISEASE_ONLY].terms["outcome_terms"])

    def test_unknown_gene_leaves_pathway_tier_empty(self):
        case = _case(gene_symbol="ZZZ9")
        plan = {it.tier: it for it in build_query_plan(case, case.alterations[0])}
        self.assertNotIn("pathway", plan[MatchSpecificity.PATHWAY].terms)
        self.assertEqual(plan[MatchSpecificity.PATHWAY].providers, [])
        self.assertEqual(plan[MatchSpecificity.DISEASE_ONLY].providers, [], "no treatments recorded -> nothing to query")
        self.assertEqual(len(plan), 6)

    def test_known_pathways(self):
        self.assertEqual(GENE_PATHWAYS["KRAS"], "MAPK")
        self.assertEqual(GENE_PATHWAYS["PIK3CA"], GENE_PATHWAYS["PTEN"])
        self.assertEqual(GENE_PATHWAYS["EGFR"], "RTK")
        self.assertNotIn("ZZZ9", GENE_PATHWAYS)

    def test_fusion_and_cna_terms(self):
        case = _case(alteration_type=AlterationType.FUSION, gene_symbol="ALK", hgvs_p=None, hgvs_c=None, consequence=None,
                     fusion_partners=[FusionPartner(gene_symbol="EML4"), FusionPartner(gene_symbol="ALK")])
        plan = {it.tier: it for it in build_query_plan(case, case.alterations[0])}
        self.assertEqual(plan[MatchSpecificity.EXACT_VARIANT].terms["variant_terms"], ["EML4-ALK fusion"])
        self.assertEqual(plan[MatchSpecificity.CODON].providers, [])
        self.assertEqual(plan[MatchSpecificity.GENE_ALTERATION_CLASS].terms["alteration_class"], "fusion")
        case = _case(alteration_type=AlterationType.CNA, gene_symbol="ERBB2", hgvs_p=None, hgvs_c=None, consequence=None, copy_number_call="amplification")
        plan = {it.tier: it for it in build_query_plan(case, case.alterations[0])}
        self.assertEqual(plan[MatchSpecificity.EXACT_VARIANT].terms["variant_terms"], ["ERBB2 amplification"])
        self.assertEqual(plan[MatchSpecificity.GENE_ALTERATION_CLASS].terms["alteration_class"], "amplification")

    def test_plan_is_deterministic(self):
        case = load_case(ROOT / "examples" / "synthetic_case.json")
        a = [it.model_dump() for it in build_query_plan(case, case.alterations[0])]
        b = [it.model_dump() for it in build_query_plan(case, case.alterations[0])]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
