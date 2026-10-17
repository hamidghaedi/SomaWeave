"""Technical-axis regressions derived from the real-case evaluation (synthetic values)."""

import unittest
from datetime import date

from somaweave.domain import Alteration, Case, ReadSupport, TreatmentEvent
from somaweave.domain.io import load_case
from somaweave.technical import assess_alteration
from somaweave.technical.chronology import event_timing, treatment_exposure
from somaweave.technical.depth_quality import depth_quality_flags
from somaweave.technical.ffpe import strand_imbalance
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _case_with(tumor: dict, normal: dict | None, preservation="FFPE"):
    case = load_case(ROOT / "examples" / "synthetic_case.json")
    data = case.model_dump(mode="json", exclude_none=True)
    data["alterations"] = [a for a in data["alterations"] if a["alteration_id"] == "A1"]
    m = data["alterations"][0]["measurements"][0]
    m["tumor"] = tumor
    if normal is None:
        m.pop("normal", None)
    else:
        m["normal"] = normal
    data["specimens"][0]["preservation"] = preservation
    return Case.model_validate(data)


class NormalTemplateTests(unittest.TestCase):
    def test_normal_alt_templates_override_caller_zero(self):
        # JAK3-like: caller normal ALT 0 but 3 reviewed ALT templates in the normal
        res = depth_quality_flags(ReadSupport(alt_count=12, depth=60, unique_templates_alt=10, mean_mapq=60, mean_baseq_alt=35, alt_forward=6, alt_reverse=6),
                                  ReadSupport(alt_count=0, depth=40, unique_templates_alt=3))
        self.assertIn("normal_template_support", res.flags)
        self.assertNotIn("normal_alt_support", res.flags)
        self.assertTrue(any("templates=3" in s for s in res.substitutions))
        case = _case_with({"alt_count": 12, "depth": 60, "unique_templates_alt": 10, "mean_mapq": 60, "mean_baseq_alt": 35, "alt_forward": 6, "alt_reverse": 6},
                          {"alt_count": 0, "depth": 40, "unique_templates_alt": 3}, preservation="fresh_frozen")
        level = assess_alteration(case, case.alterations[0])[0]
        self.assertEqual(level.level, "unreliable")

    def test_clean_normal_templates_do_not_flag(self):
        res = depth_quality_flags(ReadSupport(alt_count=12, depth=60), ReadSupport(alt_count=0, depth=40, unique_templates_alt=1))
        self.assertNotIn("normal_template_support", res.flags)


class MedianAndTemplateMetricTests(unittest.TestCase):
    def test_median_used_when_mean_absent(self):
        res = depth_quality_flags(ReadSupport(alt_count=12, depth=60, unique_templates_alt=10, median_mapq=30, median_baseq_alt=36), ReadSupport(alt_count=0, depth=40))
        self.assertIn("low_mapq", res.flags)
        self.assertNotIn("mapq", res.not_evaluated)
        self.assertTrue(any("median_mapq" in s for s in res.substitutions))

    def test_template_strands_used_when_read_strands_absent(self):
        si = strand_imbalance(ReadSupport(alt_count=8, depth=60, alt_templates_forward=8, alt_templates_reverse=0))
        self.assertTrue(si.evaluated and si.flagged)
        self.assertEqual(si.source, "templates")

    def test_missing_core_metrics_cap_at_moderate_and_are_named(self):
        case = _case_with({"alt_count": 15, "depth": 60, "unique_templates_alt": 12}, {"alt_count": 0, "depth": 40}, preservation="fresh_frozen")
        rel = assess_alteration(case, case.alterations[0])[0]
        self.assertEqual(rel.level, "moderate")
        self.assertTrue(any("core metrics not reported" in r and "mapq" in r for r in rel.rationale))

    def test_all_core_metrics_measured_gives_high(self):
        case = _case_with({"alt_count": 15, "depth": 60, "unique_templates_alt": 12, "median_mapq": 60, "median_baseq_alt": 36,
                           "alt_templates_forward": 7, "alt_templates_reverse": 8}, {"alt_count": 0, "depth": 40, "unique_templates_alt": 0}, preservation="fresh_frozen")
        rel = assess_alteration(case, case.alterations[0])[0]
        self.assertEqual(rel.level, "high", rel.rationale)

    def test_review_outcome_quoted_and_artifact_is_unreliable(self):
        res = depth_quality_flags(ReadSupport(alt_count=12, depth=60, review_outcome="artifact"), None)
        self.assertIn("review_outcome:artifact", res.flags)
        case = _case_with({"alt_count": 12, "depth": 60, "unique_templates_alt": 10, "mean_mapq": 60, "mean_baseq_alt": 35, "review_outcome": "artifact"},
                          {"alt_count": 0, "depth": 40}, preservation="fresh_frozen")
        self.assertEqual(assess_alteration(case, case.alterations[0])[0].level, "unreliable")


class PartialDateChronologyTests(unittest.TestCase):
    def test_month_precision_before_specimen(self):
        t = TreatmentEvent(treatment_id="T", name="x", agents=["x"], start_date="2024-02", end_date="2024-05")
        e = treatment_exposure(t, "2024-09")
        self.assertEqual(e.relation, "before_specimen")
        self.assertIsNone(e.days_end_to_collection)
        self.assertEqual(e.days_end_to_collection_range, ((date(2024, 9, 1) - date(2024, 5, 31)).days, (date(2024, 9, 30) - date(2024, 5, 1)).days))
        self.assertEqual(e.precision, "month")

    def test_same_month_is_undetermined_not_guessed(self):
        t = TreatmentEvent(treatment_id="T", name="x", start_date="2024-02", end_date="2024-05")
        self.assertEqual(treatment_exposure(t, "2024-05").relation, "overlapping_or_undetermined")
        t2 = TreatmentEvent(treatment_id="T", name="x", start_date="2024-02", end_date="2024-08")
        self.assertEqual(treatment_exposure(t2, "2024-05").relation, "ongoing_at_collection")

    def test_full_dates_still_exact(self):
        t = TreatmentEvent(treatment_id="T", name="x", start_date=date(2024, 1, 1), end_date=date(2024, 3, 1))
        e = treatment_exposure(t, date(2024, 3, 11))
        self.assertEqual((e.relation, e.days_end_to_collection), ("before_specimen", 10))

    def test_event_timing(self):
        case = load_case(ROOT / "examples" / "synthetic_case.json")
        ev = event_timing(case, "T1")
        kinds = {e.event_type: e.relation for e in ev}
        self.assertEqual(kinds["metastasis"], "before_specimen")   # 2025-01 vs 2025-07-02
        self.assertEqual(kinds["diagnosis"], "before_specimen")


if __name__ == "__main__":
    unittest.main()


class NormalTemplateDenominatorTests(unittest.TestCase):
    def test_template_fraction_uses_template_denominator_not_read_depth(self):
        # 32 ALT templates vs caller depth 25 would give an impossible 1.28; with 59 total templates the fraction is 0.54
        res = depth_quality_flags(ReadSupport(alt_count=40, depth=120), ReadSupport(alt_count=0, depth=25, unique_templates_alt=32, unique_templates_total=59))
        self.assertIn("normal_template_support", res.flags)
        self.assertAlmostEqual(res.details["normal_alt_template_fraction"], 32 / 59, places=4)
        self.assertTrue(any("of 59 templates" in s for s in res.substitutions))

    def test_template_fraction_absent_when_no_template_denominator(self):
        res = depth_quality_flags(ReadSupport(alt_count=40, depth=120), ReadSupport(alt_count=0, depth=1, unique_templates_alt=36))
        self.assertIn("normal_template_support", res.flags)
        self.assertIsNone(res.details["normal_alt_template_fraction"])
        self.assertTrue(any("denominator not reported" in s for s in res.substitutions))
