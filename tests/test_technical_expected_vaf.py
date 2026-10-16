import unittest

from somaweave.domain import AlterationMeasurement, CopyNumberState, PurityEstimate, ReadSupport, Specimen, SpecimenRole
from somaweave.technical.allele_fractions import observed_vaf
from somaweave.technical.expected_vaf import (
    SCENARIO_DISCLAIMER, compare_scenarios, enumerate_scenarios, evaluate_scenarios, expected_vaf,
)


class ExpectedVafFormulaTests(unittest.TestCase):
    def test_hand_computed_values(self):
        self.assertAlmostEqual(expected_vaf(0.5, 2, 1), 0.25)
        self.assertAlmostEqual(expected_vaf(0.5, 3, 2), 0.4)          # 0.5*2 / (1.5 + 1.0)
        self.assertAlmostEqual(expected_vaf(0.5, 3, 1), 0.2)          # 0.5 / 2.5
        self.assertAlmostEqual(expected_vaf(1.0, 2, 1), 0.5)
        self.assertAlmostEqual(expected_vaf(1.0, 2, 2), 1.0)
        self.assertAlmostEqual(expected_vaf(0.0, 2, 1), 0.0)
        self.assertAlmostEqual(expected_vaf(0.42, 3, 1), 0.42 / (0.42 * 3 + 0.58 * 2))

    def test_subclonal_scales_linearly(self):
        self.assertAlmostEqual(expected_vaf(0.5, 2, 1, cancer_cell_fraction=0.5), 0.125)

    def test_loh_single_copy(self):
        # CN=1 with the variant on the retained copy at purity 0.6: 0.6 / (0.6 + 0.8)
        self.assertAlmostEqual(expected_vaf(0.6, 1, 1), 0.6 / 1.4)

    def test_invalid_arguments(self):
        for args in ((1.2, 2, 1), (0.5, 2, 3), (0.5, -1, 0), (0.5, 2, 1, 2.0, 1.5)):
            with self.assertRaises(ValueError):
                expected_vaf(*args)
        with self.assertRaises(ValueError):
            expected_vaf(1.0, 0, 0)  # homozygous deletion in pure tumour: no DNA


class ScenarioEnumerationTests(unittest.TestCase):
    def test_counts_and_order(self):
        scen = enumerate_scenarios(0.5, 3, ccf_grid=(1.0, 0.5))
        self.assertEqual(len(scen), 6)
        self.assertEqual([(s.multiplicity, s.cancer_cell_fraction) for s in scen],
                         [(1, 1.0), (1, 0.5), (2, 1.0), (2, 0.5), (3, 1.0), (3, 0.5)])
        self.assertEqual(enumerate_scenarios(0.5, 0), [])

    def test_compare_marks_compatibility(self):
        scen = enumerate_scenarios(0.5, 2, ccf_grid=(1.0,))   # expected 0.25 (m=1) and 0.5 (m=2)
        out = compare_scenarios(scen, 0.2, 0.3)
        self.assertEqual([s.compatible for s in out], [True, False])
        none_out = compare_scenarios(scen, None, None)
        self.assertEqual([s.compatible for s in none_out], [None, None])


def _specimen(**purity) -> Specimen:
    return Specimen(specimen_id="T1", role=SpecimenRole.TUMOR, purity=PurityEstimate(**purity) if purity else None)


class EvaluateScenariosTests(unittest.TestCase):
    def test_pathology_and_molecular_evaluated_separately(self):
        spec = _specimen(pathology_min=0.2, pathology_max=0.5, molecular_fit=0.42)
        meas = AlterationMeasurement(specimen_id="T1", tumor=ReadSupport(alt_count=19, depth=80),
                                     copy_number=CopyNumberState(total_copy_number=3.0, caller_reported_loh=False))
        res = evaluate_scenarios(spec, meas, observed_vaf(meas.tumor))
        self.assertEqual([p.purity_source for p in res.purity_evaluations], ["pathology_min", "pathology_max", "molecular_fit"])
        self.assertEqual(res.copy_number_source, "caller")
        self.assertEqual(res.total_copy_number_used, 3)
        self.assertIs(res.caller_reported_loh, False)
        self.assertEqual(res.disclaimer, SCENARIO_DISCLAIMER)
        mol = res.purity_evaluations[2]
        clonal_m1 = next(s for s in mol.scenarios if s.multiplicity == 1 and s.cancer_cell_fraction == 1.0)
        self.assertTrue(clonal_m1.compatible)   # 0.1736 inside [0.1576, 0.3414]
        self.assertGreaterEqual(mol.compatible_count, 1)

    def test_missing_copy_number_is_labelled_assumption(self):
        spec = _specimen(molecular_fit=0.5)
        meas = AlterationMeasurement(specimen_id="T1", tumor=ReadSupport(alt_count=20, depth=80))
        res = evaluate_scenarios(spec, meas, observed_vaf(meas.tumor))
        self.assertEqual(res.copy_number_source, "assumed_diploid")
        self.assertTrue(any("assume total CN=2" in n for n in res.notes))
        res2 = evaluate_scenarios(spec, meas, observed_vaf(meas.tumor), assume_diploid_when_missing=False)
        self.assertEqual(res2.purity_evaluations, [])

    def test_no_purity_no_scenarios(self):
        meas = AlterationMeasurement(specimen_id="T1", tumor=ReadSupport(alt_count=20, depth=80))
        res = evaluate_scenarios(_specimen(), meas, observed_vaf(meas.tumor))
        self.assertEqual(res.purity_evaluations, [])
        self.assertTrue(any("no purity" in n for n in res.notes))

    def test_no_observed_interval_compatibility_is_none(self):
        spec = _specimen(molecular_fit=0.5)
        meas = AlterationMeasurement(specimen_id="T1", tumor=ReadSupport(reported_vaf=0.3))
        res = evaluate_scenarios(spec, meas, observed_vaf(meas.tumor))
        self.assertIsNone(res.purity_evaluations[0].compatible_count)
        self.assertTrue(all(s.compatible is None for s in res.purity_evaluations[0].scenarios))


if __name__ == "__main__":
    unittest.main()
