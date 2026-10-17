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
            "EGFR Exon 19 Deletion": "region", "CTNNB1 Exon 3 Mutation": "region", "EGFR L858R": "other_variant",
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
