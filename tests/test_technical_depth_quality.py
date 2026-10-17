import unittest

from somaweave.domain import ReadSupport
from somaweave.technical.depth_quality import QualityThresholds, depth_quality_flags


GOOD = ReadSupport(ref_count=61, alt_count=19, depth=80, unique_templates_alt=18, mean_mapq=60.0, mean_baseq_alt=36.0)
NORMAL = ReadSupport(ref_count=40, alt_count=0, depth=40)


class DepthQualityTests(unittest.TestCase):
    def test_clean_measurement_has_no_flags(self):
        res = depth_quality_flags(GOOD, NORMAL, "WGS")
        self.assertEqual(res.flags, [])
        self.assertEqual(res.not_evaluated, [])
        self.assertEqual(res.thresholds["min_alt_reads"], 5)

    def test_each_threshold_flag(self):
        res = depth_quality_flags(ReadSupport(alt_count=2, depth=20, unique_templates_alt=1, mean_mapq=30.0, mean_baseq_alt=20.0),
                                  ReadSupport(alt_count=3, depth=10), "WGS")
        for f in ("low_tumor_depth", "low_alt_reads", "low_unique_templates", "low_mapq", "low_alt_baseq",
                  "low_normal_depth", "normal_alt_support"):
            self.assertIn(f, res.flags)

    def test_normal_alt_passes_on_either_count_or_vaf(self):
        # 1 alt read passes on count even though VAF is 1/20 = 0.05 > 0.02
        self.assertNotIn("normal_alt_support", depth_quality_flags(GOOD, ReadSupport(alt_count=1, depth=20)).flags)
        # 2 alt reads of 200 = 0.01 passes on VAF
        self.assertNotIn("normal_alt_support", depth_quality_flags(GOOD, ReadSupport(alt_count=2, depth=200)).flags)
        # 2 alt reads of 40 = 0.05 fails both
        self.assertIn("normal_alt_support", depth_quality_flags(GOOD, ReadSupport(alt_count=2, depth=40)).flags)

    def test_missing_metrics_reported_not_passed(self):
        res = depth_quality_flags(ReadSupport(alt_count=10, depth=50), None)
        self.assertIn("no_matched_normal", res.flags)
        self.assertEqual(set(res.not_evaluated), {"unique_templates_alt", "mapq", "alt_baseq"})

    def test_no_tumor_counts(self):
        self.assertIn("no_tumor_counts", depth_quality_flags(None, NORMAL).flags)
        self.assertIn("no_tumor_counts", depth_quality_flags(ReadSupport(reported_vaf=0.3), NORMAL).flags)

    def test_assay_specific_depth_and_custom_thresholds(self):
        tumor = ReadSupport(alt_count=10, depth=40, unique_templates_alt=9, mean_mapq=60.0, mean_baseq_alt=35.0)
        self.assertNotIn("low_tumor_depth", depth_quality_flags(tumor, NORMAL, "WGS").flags)
        strict = QualityThresholds(min_tumor_depth_other=100)
        self.assertIn("low_tumor_depth", depth_quality_flags(tumor, NORMAL, "panel", strict).flags)
        self.assertNotIn("low_tumor_depth", depth_quality_flags(tumor, NORMAL, "WGS", strict).flags)


if __name__ == "__main__":
    unittest.main()
