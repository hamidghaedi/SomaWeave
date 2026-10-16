import unittest

from somaweave.domain import Alteration, AlterationType, Assembly, GenomicPosition, Preservation, ReadSupport
from somaweave.technical.ffpe import (
    FfpeThresholds, binomial_two_sided_p, ffpe_assessment, strand_imbalance, substitution_class,
)


def _snv(ref="G", alt="A") -> Alteration:
    return Alteration(alteration_id="X", alteration_type=AlterationType.SNV,
                      position=GenomicPosition(assembly=Assembly.GRCH38, chromosome="chr1", position=100, reference=ref, alternate=alt))


class BinomialTestTests(unittest.TestCase):
    def test_exact_values(self):
        self.assertAlmostEqual(binomial_two_sided_p(6, 6), 2 * 0.5 ** 6, places=12)   # 0.03125
        self.assertAlmostEqual(binomial_two_sided_p(0, 6), 0.03125, places=12)
        self.assertAlmostEqual(binomial_two_sided_p(5, 10), 1.0, places=12)
        self.assertAlmostEqual(binomial_two_sided_p(10, 19), 1.0, places=12)
        self.assertEqual(binomial_two_sided_p(0, 0), 1.0)
        # k=1 of 10: 2 * (P(0)+P(1)) = 2 * 11/1024
        self.assertAlmostEqual(binomial_two_sided_p(1, 10), 22 / 1024, places=12)
        with self.assertRaises(ValueError):
            binomial_two_sided_p(3, 2)


class StrandImbalanceTests(unittest.TestCase):
    def test_flagged_six_vs_zero(self):
        s = strand_imbalance(ReadSupport(alt_forward=6, alt_reverse=0))
        self.assertTrue(s.evaluated)
        self.assertTrue(s.flagged)
        self.assertAlmostEqual(s.p_value, 0.03125, places=10)

    def test_not_flagged_below_min_alt(self):
        s = strand_imbalance(ReadSupport(alt_forward=5, alt_reverse=0))   # p = 0.0625 and n < 6
        self.assertFalse(s.flagged)
        s = strand_imbalance(ReadSupport(alt_forward=4, alt_reverse=0), FfpeThresholds(strand_min_alt=4, strand_p_value=0.2))
        self.assertTrue(s.flagged)

    def test_balanced_not_flagged(self):
        s = strand_imbalance(ReadSupport(alt_forward=10, alt_reverse=9))
        self.assertFalse(s.flagged)
        self.assertAlmostEqual(s.p_value, 1.0, places=10)

    def test_missing_counts_not_evaluated(self):
        s = strand_imbalance(ReadSupport(alt_count=10))
        self.assertFalse(s.evaluated)
        self.assertFalse(s.flagged)
        self.assertFalse(strand_imbalance(None).evaluated)


class SubstitutionClassTests(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(substitution_class(_snv("C", "T").position), "C>T")
        self.assertEqual(substitution_class(_snv("g", "a").position), "G>A")
        self.assertIsNone(substitution_class(_snv("GA", "G").position))
        self.assertIsNone(substitution_class(None))


class FfpeAssessmentTests(unittest.TestCase):
    def test_deamination_context_flagged_in_ffpe(self):
        tumor = ReadSupport(ref_count=70, alt_count=6, depth=76, alt_forward=6, alt_reverse=0, unique_templates_alt=3,
                            mean_mapq=58.0, mean_baseq_alt=30.0)
        fa = ffpe_assessment(_snv("G", "A"), tumor, Preservation.FFPE)
        self.assertTrue(fa.is_deamination_class)
        self.assertTrue(fa.deamination_context_flagged)
        self.assertIn("ffpe_c_to_t_context", fa.flags)
        self.assertIn("strand_imbalance", fa.flags)
        self.assertFalse(fa.low_alt_baseq)
        self.assertFalse(fa.low_mapq)

    def test_deamination_not_flagged_for_fresh_frozen(self):
        tumor = ReadSupport(alt_count=6, depth=76, alt_forward=6, alt_reverse=0, unique_templates_alt=2)
        fa = ffpe_assessment(_snv("C", "T"), tumor, Preservation.FRESH_FROZEN)
        self.assertTrue(fa.is_deamination_class)
        self.assertFalse(fa.deamination_context_flagged)
        self.assertNotIn("ffpe_c_to_t_context", fa.flags)
        self.assertIn("strand_imbalance", fa.flags)   # strand test applies regardless of preservation

    def test_high_vaf_good_templates_not_flagged(self):
        tumor = ReadSupport(alt_count=19, depth=80, alt_forward=10, alt_reverse=9, unique_templates_alt=18)
        fa = ffpe_assessment(_snv("G", "A"), tumor, Preservation.FFPE)
        self.assertFalse(fa.deamination_context_flagged)
        self.assertEqual(fa.flags, [])

    def test_low_templates_alone_triggers_context(self):
        tumor = ReadSupport(alt_count=20, depth=80, unique_templates_alt=2)
        fa = ffpe_assessment(_snv("C", "T"), tumor, Preservation.FFPE)
        self.assertTrue(fa.deamination_context_flagged)
        self.assertIn("strand_counts", fa.not_evaluated)

    def test_non_deamination_class_and_quality_flags(self):
        tumor = ReadSupport(alt_count=3, depth=80, mean_mapq=20.0, mean_baseq_alt=15.0)
        fa = ffpe_assessment(_snv("A", "T"), tumor, Preservation.FFPE)
        self.assertFalse(fa.is_deamination_class)
        self.assertEqual(fa.flags, ["low_alt_baseq", "low_mapq"])

    def test_non_snv_has_no_class(self):
        alt = Alteration(alteration_id="D", alteration_type=AlterationType.DELETION, hgvs_c="c.100delA")
        fa = ffpe_assessment(alt, ReadSupport(alt_count=10, depth=50), Preservation.FFPE)
        self.assertIsNone(fa.substitution_class)
        self.assertFalse(fa.deamination_context_flagged)


if __name__ == "__main__":
    unittest.main()
