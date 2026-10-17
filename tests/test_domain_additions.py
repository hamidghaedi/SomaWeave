import unittest
from datetime import datetime, timezone

from somaweave.domain import (
    Alteration, DiseaseReference, EvidenceCategory, EvidenceRecord, MatchSpecificity, ReadSupport,
)


class ConsequenceClassTests(unittest.TestCase):
    def cls(self, **kw):
        return Alteration(alteration_id="A", alteration_type=kw.pop("alteration_type", "SNV"), gene_symbol="G",
                          hgvs_p=kw.pop("hgvs_p", "p.Ala1Val"), **kw).consequence_class()

    def test_truncating_from_hgvs_and_so(self):
        self.assertEqual(self.cls(hgvs_p="p.Thr305AsnfsTer4"), "truncating")
        self.assertEqual(self.cls(hgvs_p="p.T305Nfs*4"), "truncating")
        self.assertEqual(self.cls(hgvs_p="p.Gln61Ter"), "truncating")
        self.assertEqual(self.cls(hgvs_p="p.Q61*"), "truncating")
        self.assertEqual(self.cls(consequence="stop_gained"), "truncating")

    def test_other_classes(self):
        self.assertEqual(self.cls(consequence="missense_variant"), "missense")
        self.assertEqual(self.cls(hgvs_p="p.Leu123=", consequence="synonymous_variant"), "synonymous")
        self.assertEqual(self.cls(consequence="splice_donor_variant", hgvs_p=None, hgvs_c="c.2769+5G>T"), "splice")
        self.assertEqual(self.cls(hgvs_p="p.Glu746_Ala750del", alteration_type="deletion"), "inframe")
        self.assertIsNone(Alteration(alteration_id="A", alteration_type="CNA", gene_symbol="G", copy_number_call="amplification").consequence_class())


class ReadSupportAdditionsTests(unittest.TestCase):
    def test_new_fields_optional(self):
        rs = ReadSupport(ref_count=10, alt_count=5, median_mapq=60, alt_templates_forward=3, alt_templates_reverse=2, review_outcome="supported")
        self.assertEqual(rs.median_mapq, 60)
        self.assertIsNone(rs.mean_mapq)


class EvidenceConditionsTests(unittest.TestCase):
    def test_conditions_list(self):
        rec = EvidenceRecord(evidence_id="x:1", source_name="clinvar", source_native_id="1",
                             retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                             query_tier=MatchSpecificity.EXACT_VARIANT, variant_match=MatchSpecificity.EXACT_VARIANT,
                             evidence_category=EvidenceCategory.ONCOGENIC, assertion="a",
                             disease=DiseaseReference(name="Adamantinous craniopharyngioma"),
                             conditions=[DiseaseReference(name="Adamantinous craniopharyngioma"),
                                         DiseaseReference(name="Solid pseudopapillary neoplasm of the pancreas", oncotree_code="SPN")])
        self.assertEqual(len(rec.conditions), 2)
        self.assertEqual(rec.conditions[1].oncotree_code, "SPN")


if __name__ == "__main__":
    unittest.main()
