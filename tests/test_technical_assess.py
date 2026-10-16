import json
import unittest
from pathlib import Path

from somaweave.domain import (
    Alteration, AlterationMeasurement, AlterationType, Assembly, Case, Diagnosis, GenomicPosition,
    Preservation, ReadSupport, Specimen, SpecimenRole,
)
from somaweave.domain.io import load_case
from somaweave.technical import LEVEL_RULES, assess_alteration, assess_measurement, technical_summary

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic_case.json"
FIXTURE = ROOT / "tests" / "fixtures" / "technical" / "synthetic_case_expected.json"


def _case(tumor: ReadSupport, normal=None, preservation=Preservation.FFPE, filters=("PASS",), qc=()) -> Case:
    return Case(
        case_id="C", assembly=Assembly.GRCH38, diagnosis=Diagnosis(name="x"),
        specimens=[Specimen(specimen_id="T1", role=SpecimenRole.TUMOR, preservation=preservation, sequencing_assay="WGS"),
                   Specimen(specimen_id="N1", role=SpecimenRole.NORMAL)],
        alterations=[Alteration(
            alteration_id="A", alteration_type=AlterationType.SNV,
            position=GenomicPosition(assembly=Assembly.GRCH38, chromosome="chr1", position=10, reference="C", alternate="T"),
            measurements=[AlterationMeasurement(specimen_id="T1", tumor=tumor, normal=normal, caller_filters=list(filters), qc_flags=list(qc))],
        )],
    )


CLEAN = ReadSupport(ref_count=60, alt_count=20, depth=80, alt_forward=10, alt_reverse=10, unique_templates_alt=19,
                    mean_mapq=60.0, mean_baseq_alt=35.0)
NORMAL = ReadSupport(ref_count=40, alt_count=0, depth=40)


class SyntheticCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_case(EXAMPLE)
        cls.expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.summary = technical_summary(cls.case)

    def test_levels_and_flags_match_fixture(self):
        for alt in self.case.alterations:
            exp = self.expected["measurements"][alt.alteration_id]
            rel = assess_alteration(self.case, alt)
            self.assertEqual(len(rel), 1)
            self.assertEqual(rel[0].level, exp["level"], alt.alteration_id)
            self.assertEqual(rel[0].flags, exp["flags"], alt.alteration_id)
            self.assertEqual(rel[0].specimen_id, exp["specimen_id"])

    def test_a1_values(self):
        m = self.summary["alterations"][0]["measurements"][0]
        exp = self.expected["measurements"]["A1"]
        self.assertAlmostEqual(m["observed"]["vaf"], exp["vaf"], places=4)
        self.assertEqual(m["observed"]["denominator"], exp["denominator"])
        self.assertAlmostEqual(m["observed"]["ci_lower"], exp["wilson_ci"][0], places=4)
        self.assertAlmostEqual(m["observed"]["ci_upper"], exp["wilson_ci"][1], places=4)
        self.assertEqual(m["ffpe"]["substitution_class"], exp["substitution_class"])
        self.assertAlmostEqual(m["ffpe"]["strand"]["p_value"], exp["strand_p"], places=6)
        counts = {p["purity_source"]: p["compatible_count"] for p in m["scenarios"]["purity_evaluations"]}
        self.assertEqual(counts, exp["compatible_counts"])
        self.assertEqual(m["scenarios"]["copy_number_source"], "caller")
        self.assertIn("NOT inferred from VAF alone", m["scenarios"]["disclaimer"])

    def test_a2_values(self):
        m = self.summary["alterations"][1]["measurements"][0]
        exp = self.expected["measurements"]["A2"]
        self.assertAlmostEqual(m["observed"]["vaf"], exp["vaf"], places=3)
        self.assertAlmostEqual(m["ffpe"]["strand"]["p_value"], exp["strand_p"], places=6)
        self.assertTrue(m["ffpe"]["deamination_context_flagged"])
        self.assertEqual(m["scenarios"]["copy_number_source"], "assumed_diploid")

    def test_chronology_in_summary(self):
        chron = self.summary["treatment_chronology"]["T1"]
        exp = self.expected["chronology"]["T1"][0]
        self.assertEqual(chron[0]["relation"], exp["relation"])
        self.assertEqual(chron[0]["days_start_to_collection"], exp["days_start_to_collection"])
        self.assertEqual(chron[0]["days_end_to_collection"], exp["days_end_to_collection"])

    def test_summary_is_json_serialisable_and_documents_rules(self):
        text = json.dumps(self.summary)
        self.assertIn("level_rules", self.summary)
        self.assertEqual(self.summary["level_rules"], LEVEL_RULES)
        self.assertEqual(self.summary["case_id"], "SYN-0001")
        self.assertGreater(len(text), 1000)

    def test_deterministic(self):
        self.assertEqual(json.dumps(self.summary, sort_keys=True), json.dumps(technical_summary(self.case), sort_keys=True))


class LevelRuleTests(unittest.TestCase):
    def _level(self, case: Case):
        return assess_measurement(case, case.alterations[0], case.alterations[0].measurements[0]).reliability

    def test_high_when_clean(self):
        r = self._level(_case(CLEAN, NORMAL))
        self.assertEqual(r.level, "high")
        self.assertEqual(r.flags, [])

    def test_not_assessable_without_counts(self):
        r = self._level(_case(ReadSupport(reported_vaf=0.3), NORMAL))
        self.assertEqual(r.level, "not_assessable")
        self.assertIn("no_tumor_counts", r.flags)

    def test_unreliable_on_low_alt_or_normal_support(self):
        r = self._level(_case(CLEAN.model_copy(update={"alt_count": 2, "ref_count": 78}), NORMAL))
        self.assertEqual(r.level, "unreliable")
        r = self._level(_case(CLEAN, ReadSupport(alt_count=5, depth=40)))
        self.assertEqual(r.level, "unreliable")
        self.assertIn("normal_alt_support", r.flags)

    def test_low_on_major_flags(self):
        r = self._level(_case(CLEAN.model_copy(update={"mean_mapq": 20.0}), NORMAL))
        self.assertEqual(r.level, "low")
        r = self._level(_case(CLEAN.model_copy(update={"alt_forward": 20, "alt_reverse": 0}), NORMAL))
        self.assertEqual(r.level, "low")
        self.assertIn("strand_imbalance", r.flags)

    def test_moderate_on_minor_flags(self):
        r = self._level(_case(CLEAN, None))
        self.assertEqual(r.level, "moderate")
        self.assertIn("no_matched_normal", r.flags)
        r = self._level(_case(CLEAN, NORMAL, filters=("PASS", "strand_bias")))
        self.assertEqual(r.level, "moderate")
        self.assertIn("caller_filter_not_pass", r.flags)
        r = self._level(_case(CLEAN.model_copy(update={"mean_mapq": None}), NORMAL))
        self.assertEqual(r.level, "moderate")
        self.assertIn("mean_mapq_not_reported", r.flags)
        r = self._level(_case(CLEAN, NORMAL, qc=("orientation_bias",)))
        self.assertEqual(r.level, "moderate")

    def test_only_tumor_specimen_measurements_assessed(self):
        case = _case(CLEAN, NORMAL)
        alt = case.alterations[0].model_copy(update={"measurements": case.alterations[0].measurements
                                                     + [AlterationMeasurement(specimen_id="N1", tumor=CLEAN)]})
        case = case.model_copy(update={"alterations": [alt]})
        self.assertEqual(len(assess_alteration(case, alt)), 1)


if __name__ == "__main__":
    unittest.main()
