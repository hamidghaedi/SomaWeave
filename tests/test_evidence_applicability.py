"""Regression tests for the alteration-class applicability gate.

Each case mirrors a pattern seen in the real-case evaluation (profiles and
genes only; no patient data).
"""

import unittest
from datetime import datetime, timezone

from somaweave.domain import Alteration, EvidenceCategory, EvidenceRecord, MatchSpecificity
from somaweave.evidence.applicability import applicability_for, classify_profile, one_letter_protein

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rec(desc, gene, vm=MatchSpecificity.GENE, source="civic", cat=EvidenceCategory.DIAGNOSTIC):
    return EvidenceRecord(evidence_id=f"{source}:x:{desc}", source_name=source, source_native_id="x", retrieved_at=NOW,
                          query_tier=MatchSpecificity.GENE, variant_match=vm, gene_symbol=gene, variant_description=desc,
                          evidence_category=cat, assertion="a", source_native_status="accepted")


def _alt(gene, hgvs_p=None, consequence=None, atype="SNV", **kw):
    return Alteration(alteration_id="A", alteration_type=atype, gene_symbol=gene, hgvs_p=hgvs_p, consequence=consequence, **kw)


class ClassifierTests(unittest.TestCase):
    def test_one_letter(self):
        self.assertEqual(one_letter_protein("p.Asp32Asn"), "D32N")
        self.assertEqual(one_letter_protein("p.Thr305AsnfsTer4"), "T305Nfs*4")
        self.assertEqual(one_letter_protein("D32N"), "D32N")
        self.assertIsNone(one_letter_protein("Exon 19 Deletion"))

    def test_profile_classes(self):
        cases = {
            "BCOR::CCNB3 Fusion OR BCOR::MAML3 Fusion": "fusion", "ASPSCR1::TFE3 Fusion": "fusion", "DCC EXPRESSION": "expression",
            "NT5E Overexpression": "expression", "EGFR Amplification": "copy_number", "SETD2 Truncating Mutations": "truncating_class",
            "KMT2C Loss-of-function": "truncating_class", "EGFR Mutation": "gene_wide", "CTNNB1 Activating Mutation": "gene_wide",
            "EGFR Exon 19 Deletion": "region_indel", "CTNNB1 Exon 3 Mutation": "region", "EGFR L858R": "other_variant",
            "EGFR Gain-of-function": "functional_class", "SETD2 Loss": "loss_class", "PIK3CA Activation mutation": "gene_wide",
        }
        for desc, expected in cases.items():
            self.assertEqual(classify_profile(desc, desc.split()[0], "P1033L")[0], expected, desc)
        self.assertEqual(classify_profile("CTNNB1 D32N", "CTNNB1", "D32N")[0], "exact")
        self.assertEqual(classify_profile("CTNNB1 D32Y", "CTNNB1", "D32N")[0], "codon")
        self.assertEqual(classify_profile("EGFR L858R OR EGFR Exon 19 Deletion", "EGFR", "L858R")[0], "exact")


class ApplicabilityTests(unittest.TestCase):
    def test_fusion_profile_not_applicable_to_small_variant(self):
        # MAML3 small variant vs BCOR::MAML3 fusion profile (KQ0283 pattern)
        app = applicability_for(_rec("BCOR::CCNB3 Fusion OR BCOR::MAML3 Fusion", "MAML3"), _alt("MAML3", "p.Arg123Cys", "missense_variant"))
        self.assertFalse(app.applicable)
        self.assertEqual(app.profile_class, "fusion")
        app = applicability_for(_rec("ASPSCR1::TFE3 Fusion", "ASPSCR1"), _alt("ASPSCR1", "p.Pro456Arg", "missense_variant"))
        self.assertFalse(app.applicable)

    def test_expression_profile_not_applicable_to_synonymous_snv(self):
        app = applicability_for(_rec("DCC EXPRESSION", "DCC"), _alt("DCC", "p.Arg815=", "synonymous_variant"))
        self.assertFalse(app.applicable)
        self.assertEqual(app.profile_class, "expression")

    def test_other_specific_variant_not_applicable(self):
        app = applicability_for(_rec("EGFR L858R", "EGFR", cat=EvidenceCategory.PREDICTIVE), _alt("EGFR", "p.Pro1033Leu", "missense_variant"))
        self.assertFalse(app.applicable)
        self.assertEqual(app.profile_class, "other_variant")

    def test_truncating_class_applies_only_to_truncating(self):
        rec = _rec("SETD2 Truncating Mutations", "SETD2", vm=MatchSpecificity.GENE_ALTERATION_CLASS, source="oncokb", cat=EvidenceCategory.ONCOGENIC)
        ok = applicability_for(rec, _alt("SETD2", "p.Thr305AsnfsTer4", "frameshift_variant", atype="insertion"))
        self.assertTrue(ok.applicable and ok.variant_matched)
        no = applicability_for(rec, _alt("SETD2", "p.Arg123Cys", "missense_variant"))
        self.assertFalse(no.applicable)

    def test_gene_wide_and_region_apply_at_gene_level_only(self):
        for desc in ("EGFR Mutation", "CTNNB1 Exon 3 Mutation"):
            app = applicability_for(_rec(desc, desc.split()[0]), _alt(desc.split()[0], "p.Asp32Asn", "missense_variant"))
            self.assertTrue(app.applicable, desc)
            self.assertFalse(app.variant_matched, desc)

    def test_exact_and_codon_always_apply(self):
        app = applicability_for(_rec("CTNNB1 D32N", "CTNNB1", vm=MatchSpecificity.EXACT_VARIANT), _alt("CTNNB1", "p.Asp32Asn"))
        self.assertTrue(app.applicable and app.variant_matched)

    def test_cna_and_fusion_alterations(self):
        cna = Alteration(alteration_id="C", alteration_type="CNA", gene_symbol="EGFR", copy_number_call="amplification")
        self.assertTrue(applicability_for(_rec("EGFR Amplification", "EGFR"), cna).applicable)
        self.assertFalse(applicability_for(_rec("EGFR L858R", "EGFR"), cna).applicable)
        fus = Alteration(alteration_id="F", alteration_type="fusion", gene_symbol="TFE3", fusion_partners=[{"gene_symbol": "ASPSCR1"}, {"gene_symbol": "TFE3"}])
        self.assertTrue(applicability_for(_rec("ASPSCR1::TFE3 Fusion", "TFE3"), fus).applicable)
        self.assertFalse(applicability_for(_rec("TFE3 Overexpression", "TFE3"), fus).applicable)


if __name__ == "__main__":
    unittest.main()


class EvalRound3RegressionTests(unittest.TestCase):
    """Patterns from the second real-case evaluation (profiles only, no patient data)."""

    def test_compound_and_profile_requires_every_component(self):
        # PIK3CA E545K AND FGFR3 S249C AND FGFR3 N540K must not be attributed to isolated PIK3CA E545K
        rec = _rec("PIK3CA E545K AND FGFR3 S249C AND FGFR3 N540K", "PIK3CA", vm=MatchSpecificity.CODON, cat=EvidenceCategory.PREDICTIVE)
        pik = _alt("PIK3CA", "p.Glu545Lys", "missense_variant")
        app = applicability_for(rec, pik, [pik])
        self.assertFalse(app.applicable)
        self.assertIn("FGFR3 N540K", app.reason)
        # satisfied when the case carries the FGFR3 alterations too
        f1 = Alteration(alteration_id="B", alteration_type="SNV", gene_symbol="FGFR3", hgvs_p="p.Ser249Cys", consequence="missense_variant")
        f2 = Alteration(alteration_id="C", alteration_type="SNV", gene_symbol="FGFR3", hgvs_p="p.Asn540Lys", consequence="missense_variant")
        app2 = applicability_for(rec, pik, [pik, f1, f2])
        self.assertTrue(app2.applicable and app2.variant_matched)

    def test_exon_indel_profiles_do_not_apply_to_snv(self):
        egfr = _alt("EGFR", "p.Pro1033Leu", "missense_variant")
        for desc in ("EGFR Exon 19 Deletion", "EGFR Exon 20 Insertion", "EGFR L858R OR EGFR Exon 19 Deletion"):
            app = applicability_for(_rec(desc, "EGFR", cat=EvidenceCategory.PREDICTIVE), egfr)
            self.assertFalse(app.applicable, desc)
        # but an exon-deletion profile is gene-level context for a deletion
        dele = _alt("EGFR", "p.Glu746_Ala750del", "inframe_deletion", atype="deletion")
        app = applicability_for(_rec("EGFR Exon 19 Deletion", "EGFR"), dele)
        self.assertTrue(app.applicable and not app.variant_matched)

    def test_gain_of_function_is_functional_context_not_copy_gain(self):
        app = applicability_for(_rec("EGFR Gain-of-function", "EGFR", cat=EvidenceCategory.FUNCTIONAL), _alt("EGFR", "p.Pro1033Leu", "missense_variant"))
        self.assertEqual(app.profile_class, "functional_class")
        self.assertTrue(app.applicable and not app.variant_matched)

    def test_bare_loss_applies_only_to_truncating(self):
        rec = _rec("KMT2C Loss", "KMT2C", cat=EvidenceCategory.PREDICTIVE)
        splice5 = Alteration(alteration_id="A", alteration_type="SNV", gene_symbol="KMT2C", hgvs_c="c.2769+5G>T", consequence="splice_region_variant,intron_variant")
        self.assertFalse(applicability_for(rec, splice5).applicable)
        trunc = _alt("KMT2C", "p.Arg100Ter", "stop_gained")
        self.assertTrue(applicability_for(rec, trunc).applicable)
        cna_loss = Alteration(alteration_id="D", alteration_type="CNA", gene_symbol="KMT2C", copy_number_call="deep_deletion")
        self.assertTrue(applicability_for(rec, cna_loss).applicable)

    def test_splice_region_with_missense_is_not_splice_class(self):
        a = Alteration(alteration_id="A", alteration_type="SNV", gene_symbol="FANK1", hgvs_p="p.Thr64Met", consequence="missense_variant,splice_region_variant")
        self.assertEqual(a.consequence_class(), "missense")
        b = Alteration(alteration_id="B", alteration_type="SNV", gene_symbol="X", hgvs_c="c.100+2T>C", consequence="splice_donor_variant")
        self.assertEqual(b.consequence_class(), "splice")
