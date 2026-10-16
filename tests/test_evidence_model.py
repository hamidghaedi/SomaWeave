import unittest
from datetime import datetime, timezone

from somaweave.domain import (
    DiseaseMatch, EvidenceCategory, EvidenceRecord, MatchSpecificity, SourceQuery, SourceQueryResult, SourceStatus,
)


class EvidenceModelTests(unittest.TestCase):
    def test_record_minimal(self):
        rec = EvidenceRecord(
            evidence_id="civic:eid:1", source_name="CIViC", source_native_id="1",
            retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            query_tier=MatchSpecificity.EXACT_VARIANT, variant_match=MatchSpecificity.EXACT_VARIANT,
            evidence_category=EvidenceCategory.PREDICTIVE, assertion="x",
        )
        self.assertEqual(rec.disease_match, DiseaseMatch.UNKNOWN)
        self.assertFalse(rec.is_hypothesis)

    def test_source_status_distinguishes_failure_from_absence(self):
        q = SourceQuery(source_name="CIViC", tier=MatchSpecificity.GENE, query_terms={"gene": "KRAS"})
        failed = SourceQueryResult(query=q, status=SourceStatus.UNAVAILABLE, retrieved_at=datetime.now(timezone.utc))
        empty = SourceQueryResult(query=q, status=SourceStatus.NO_RECORDS, retrieved_at=datetime.now(timezone.utc))
        self.assertNotEqual(failed.status, empty.status)
        self.assertEqual(failed.record_count, 0)

    def test_specificity_order_is_most_to_least_specific(self):
        tiers = list(MatchSpecificity)
        self.assertEqual(tiers[0], MatchSpecificity.EXACT_VARIANT)
        self.assertEqual(tiers[-1], MatchSpecificity.DISEASE_ONLY)


if __name__ == "__main__":
    unittest.main()
