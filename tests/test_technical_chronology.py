import unittest
from datetime import date

from somaweave.domain import TreatmentEvent
from somaweave.technical.chronology import treatment_exposure


def _tx(**kw) -> TreatmentEvent:
    base = {"treatment_id": "TX", "name": "agent"}
    base.update(kw)
    return TreatmentEvent(**base)


COLLECT = date(2025, 7, 2)


class ChronologyTests(unittest.TestCase):
    def test_before_specimen(self):
        e = treatment_exposure(_tx(start_date=date(2025, 2, 3), end_date=date(2025, 6, 15)), COLLECT)
        self.assertEqual(e.relation, "before_specimen")
        self.assertEqual(e.days_start_to_collection, 149)
        self.assertEqual(e.days_end_to_collection, 17)

    def test_ongoing_with_end_after_collection(self):
        e = treatment_exposure(_tx(start_date=date(2025, 6, 1), end_date=date(2025, 8, 1)), COLLECT)
        self.assertEqual(e.relation, "ongoing_at_collection")
        self.assertEqual(e.days_end_to_collection, -30)

    def test_ongoing_flag_without_end(self):
        e = treatment_exposure(_tx(start_date=date(2025, 6, 1), ongoing=True), COLLECT)
        self.assertEqual(e.relation, "ongoing_at_collection")
        e2 = treatment_exposure(_tx(start_date=date(2025, 6, 1)), COLLECT)
        self.assertEqual(e2.relation, "unknown_dates")
        self.assertEqual(e2.days_start_to_collection, 31)

    def test_same_day_boundaries(self):
        self.assertEqual(treatment_exposure(_tx(start_date=COLLECT, end_date=COLLECT), COLLECT).relation, "ongoing_at_collection")
        self.assertEqual(treatment_exposure(_tx(start_date=date(2025, 7, 3)), COLLECT).relation, "after_specimen")

    def test_missing_dates_never_guessed(self):
        self.assertEqual(treatment_exposure(_tx(), COLLECT).relation, "unknown_dates")
        self.assertEqual(treatment_exposure(_tx(start_date=date(2025, 1, 1)), None).relation, "unknown_dates")
        e = treatment_exposure(_tx(end_date=date(2025, 1, 1)), COLLECT)
        self.assertEqual(e.relation, "before_specimen")
        self.assertIn("start_date missing", e.note)
        e = treatment_exposure(_tx(end_date=date(2025, 9, 1)), COLLECT)
        self.assertEqual(e.relation, "unknown_dates")


if __name__ == "__main__":
    unittest.main()
