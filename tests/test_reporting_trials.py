"""Trial subsection of the Markdown report: listed only for (likely) oncogenic findings; counts otherwise."""

import unittest
from datetime import datetime, timezone

from somaweave.domain import DiseaseReference, EvidenceCategory, EvidenceRecord, MatchSpecificity
from somaweave.domain.assessment import (ActionabilityAssessment, AnalyticalReliability, CaseRelevance, FindingAssessment,
                                         OncogenicityAssessment)
from somaweave.evidence.reconcile import EvidenceSet
from somaweave.reporting.render_markdown import _trials_block

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def trial(nct, level="basket: Solid Tumor"):
    return EvidenceRecord(evidence_id=f"tooluniverse:clinicaltrials:{nct}", source_name="tooluniverse", source_native_id=nct,
                          retrieved_at=NOW, query_tier=MatchSpecificity.GENE, variant_match=MatchSpecificity.GENE, gene_symbol="EGFR",
                          evidence_category=EvidenceCategory.TRIAL, assertion="x", source_native_status="RECRUITING",
                          source_native_level="PHASE2", source_native_rating=level, drugs=["DrugX"],
                          conditions=[DiseaseReference(name="Non-Small Cell Lung Cancer")], is_hypothesis=True)


def finding(classification):
    return FindingAssessment(alteration_id="A1", analytical=AnalyticalReliability(level="high"),
                             oncogenicity=OncogenicityAssessment(classification=classification),
                             actionability=ActionabilityAssessment(tier="IV", level="not_assessed"), relevance=CaseRelevance(level="low"))


class TrialBlockTests(unittest.TestCase):
    def setUp(self):
        self.es = EvidenceSet(case_id="C", alteration_id="A1", records=[trial("NCT1"), trial("NCT2")])

    def test_listed_for_likely_oncogenic(self):
        text = _trials_block(self.es, finding("likely_oncogenic"))
        self.assertIn("NCT1 (RECRUITING PHASE2; matched at basket: Solid Tumor): DrugX", text)
        self.assertIn("Non-Small Cell Lung Cancer", text)

    def test_counted_not_listed_for_vus_and_benign(self):
        for cls in ("uncertain_significance", "likely_benign", "benign", "not_assessed"):
            text = _trials_block(self.es, finding(cls))
            self.assertIn("2 registry match(es) retrieved on the gene symbol but not listed", text, cls)
            self.assertNotIn("NCT1", text)
            self.assertIn("evidence JSON", text)

    def test_none_and_not_queried(self):
        self.assertEqual(_trials_block(EvidenceSet(case_id="C", alteration_id="A1", records=[]), finding("oncogenic")), "- not queried")


if __name__ == "__main__":
    unittest.main()
