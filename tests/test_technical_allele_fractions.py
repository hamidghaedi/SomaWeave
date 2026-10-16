import unittest

from somaweave.domain import ReadSupport
from somaweave.technical.allele_fractions import (
    binomial_cdf, clopper_pearson_interval, normal_alt_summary, observed_vaf, wilson_interval,
)


class WilsonIntervalTests(unittest.TestCase):
    def test_known_value(self):
        lo, hi = wilson_interval(19, 80)
        self.assertAlmostEqual(lo, 0.15765, places=4)
        self.assertAlmostEqual(hi, 0.34141, places=4)

    def test_bounds_and_edges(self):
        lo, hi = wilson_interval(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0)
        lo, hi = wilson_interval(10, 10)
        self.assertEqual(hi, 1.0)
        with self.assertRaises(ValueError):
            wilson_interval(1, 0)
        with self.assertRaises(ValueError):
            wilson_interval(5, 4)


class ClopperPearsonTests(unittest.TestCase):
    def test_cdf(self):
        self.assertAlmostEqual(binomial_cdf(1, 2, 0.5), 0.75, places=12)
        self.assertEqual(binomial_cdf(5, 5, 0.3), 1.0)

    def test_zero_successes_upper_matches_closed_form(self):
        # upper bound for k=0 is 1 - (alpha/2)^(1/n)
        lo, hi = clopper_pearson_interval(0, 20)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 1 - 0.025 ** (1 / 20), places=8)

    def test_contains_wilson_centre_and_is_wider(self):
        cp = clopper_pearson_interval(19, 80)
        w = wilson_interval(19, 80)
        self.assertLessEqual(cp[0], w[0])
        self.assertGreaterEqual(cp[1], w[1])
        self.assertLess(cp[0], 19 / 80)
        self.assertGreater(cp[1], 19 / 80)


class ObservedVafTests(unittest.TestCase):
    def test_from_counts_with_depth(self):
        obs = observed_vaf(ReadSupport(ref_count=61, alt_count=19, depth=80, reported_vaf=0.2375))
        self.assertEqual(obs.vaf_source, "raw_counts")
        self.assertEqual(obs.denominator_source, "depth")
        self.assertAlmostEqual(obs.vaf, 0.2375)
        self.assertAlmostEqual(obs.reported_vs_observed_delta, 0.0)
        self.assertEqual(obs.ci_method, "wilson")

    def test_ref_plus_alt_denominator(self):
        obs = observed_vaf(ReadSupport(ref_count=30, alt_count=10))
        self.assertEqual(obs.denominator, 40)
        self.assertEqual(obs.denominator_source, "ref_plus_alt")
        self.assertAlmostEqual(obs.vaf, 0.25)

    def test_missing_counts_never_fall_back_to_reported(self):
        obs = observed_vaf(ReadSupport(reported_vaf=0.31))
        self.assertIsNone(obs.vaf)
        self.assertEqual(obs.vaf_source, "none")
        self.assertEqual(obs.reported_vaf, 0.31)
        self.assertIsNone(obs.ci_lower)
        obs2 = observed_vaf(ReadSupport(alt_count=4, reported_vaf=0.1))
        self.assertIsNone(obs2.vaf)
        self.assertEqual(obs2.alt_count, 4)

    def test_none_support(self):
        obs = observed_vaf(None)
        self.assertIsNone(obs.vaf)
        self.assertEqual(obs.vaf_source, "none")

    def test_clopper_pearson_option_and_bad_method(self):
        obs = observed_vaf(ReadSupport(alt_count=6, depth=76), ci_method="clopper_pearson")
        self.assertEqual(obs.ci_method, "clopper_pearson")
        self.assertLess(obs.ci_lower, 6 / 76)
        with self.assertRaises(ValueError):
            observed_vaf(ReadSupport(alt_count=6, depth=76), ci_method="wald")


class NormalSummaryTests(unittest.TestCase):
    def test_summary(self):
        n = normal_alt_summary(ReadSupport(ref_count=40, alt_count=0, depth=40))
        self.assertTrue(n.available)
        self.assertEqual(n.vaf, 0.0)
        self.assertEqual(n.vaf_source, "raw_counts")

    def test_missing(self):
        self.assertFalse(normal_alt_summary(None).available)
        n = normal_alt_summary(ReadSupport(reported_vaf=0.01))
        self.assertTrue(n.available)
        self.assertIsNone(n.vaf)
        self.assertEqual(n.vaf_source, "none")


if __name__ == "__main__":
    unittest.main()
