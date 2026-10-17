import unittest
from datetime import date

from somaweave.domain import PartialDate, certainly_before
from somaweave.domain.case import ClinicalEvent, Specimen, TreatmentEvent
from somaweave.domain.io import CaseValidationError, case_from_dict


class PartialDateTests(unittest.TestCase):
    def test_parse_precisions(self):
        self.assertEqual(PartialDate.parse("2024").precision, "year")
        self.assertEqual(PartialDate.parse("2024-02").precision, "month")
        self.assertEqual(PartialDate.parse(date(2024, 2, 10)).precision, "day")

    def test_bounds(self):
        p = PartialDate.parse("2024-02")
        self.assertEqual(p.earliest, date(2024, 2, 1))
        self.assertEqual(p.latest, date(2024, 2, 29))
        self.assertEqual(PartialDate.parse("2023").latest, date(2023, 12, 31))
        self.assertEqual(p.isoformat(), "2024-02")

    def test_invalid_partial_rejected(self):
        with self.assertRaises(ValueError):
            Specimen(specimen_id="T", role="tumor", collection_date="2024-13")
        with self.assertRaises(ValueError):
            Specimen(specimen_id="T", role="tumor", collection_date="Feb 2024")

    def test_fields_accept_full_and_partial(self):
        s = Specimen(specimen_id="T", role="tumor", collection_date="2024-02-10")
        self.assertEqual(s.collection_date, date(2024, 2, 10))
        s2 = Specimen(specimen_id="T", role="tumor", collection_date="2024-02")
        self.assertEqual(s2.collection_date, "2024-02")
        e = ClinicalEvent(event_type="metastasis", event_date="2025")
        self.assertEqual(e.event_date, "2025")

    def test_certainly_before(self):
        self.assertTrue(certainly_before("2024-01", "2024-03"))
        self.assertFalse(certainly_before("2024-05", "2024-03"))
        self.assertIsNone(certainly_before("2024-03", "2024-03"))
        self.assertIsNone(certainly_before(None, "2024-03"))

    def test_treatment_order_only_flagged_when_certain(self):
        TreatmentEvent(treatment_id="T", name="x", start_date="2024-03", end_date="2024-03")  # same month: allowed
        with self.assertRaises(ValueError):
            TreatmentEvent(treatment_id="T", name="x", start_date="2024-05", end_date="2024-03")

    def test_case_roundtrip_with_partial_dates(self):
        data = {"case_id": "C", "assembly": "GRCh38", "diagnosis": {"name": "x", "diagnosis_date": "2023"},
                "specimens": [{"specimen_id": "T1", "role": "tumor", "collection_date": "2024-02"}]}
        case = case_from_dict(data)
        self.assertEqual(case.specimens[0].collection_date, "2024-02")


if __name__ == "__main__":
    unittest.main()
