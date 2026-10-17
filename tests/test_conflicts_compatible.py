"""Compatible codon conflicts retain gene, class, drug and disease boundaries."""

import unittest

from somaweave.domain import EvidenceCategory
from somaweave.evidence.reconcile import detect_conflicts
from test_evidence_reconcile import _rec


class CompatibleConflictsTests(unittest.TestCase):
    def records(self):
        a = _rec("civic:eid:1", drugs=("drugA",)).model_copy(update={"gene_symbol": "PIK3CA", "variant_description": "PIK3CA E545K"})
        b = _rec("civic:eid:2", drugs=("drugA",), status="accepted; significance=RESISTANCE", disease="Colorectal Cancer").model_copy(
            update={"gene_symbol": "PIK3CA", "variant_description": "PIK3CA p.Glu545Gly"})
        return a, b

    def conflicts(self, a, b):
        return detect_conflicts([a, b], {a.evidence_id: "SENSITIVITYRESPONSE", b.evidence_id: "RESISTANCE"})

    def test_same_class_codon_different_disease_flagged(self):
        result = self.conflicts(*self.records())
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].same_disease)
        self.assertIn("substitutions not assumed equivalent", result[0].description)

    def test_format_equivalent_same_disease_and_no_duplicate(self):
        a, b = self.records()
        b = b.model_copy(update={"variant_description": "PIK3CA p.Glu545Lys", "disease": a.disease})
        result = self.conflicts(a, b)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].same_disease)
        self.assertEqual(len(result[0].evidence_ids), 2)

    def test_boundaries(self):
        a, b = self.records()
        for changes in ({"gene_symbol": "EGFR"}, {"variant_description": "PIK3CA H1047R"},
                        {"variant_description": "PIK3CA Amplification"},
                        {"variant_description": "PIK3CA E545G AND EGFR L858R"},
                        {"variant_description": "PIK3CA Exon 9 Mutation"},
                        {"drugs": ["drugB"]}, {"evidence_category": EvidenceCategory.PROGNOSTIC}):
            self.assertEqual(self.conflicts(a, b.model_copy(update=changes)), [], changes)
