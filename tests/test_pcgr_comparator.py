"""Offline comparator contracts; no PCGR process, references or network needed."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from somaweave.domain.io import load_case
from somaweave.domain.alteration import GenomicPosition
from somaweave.comparators.pcgr.vcf import allele_key, export_vcf, read_map, tumor_site
from somaweave.comparators.pcgr.mapping import protein_snv, deletion_interval, cds_to_genomic, complement, select_mane
from somaweave.comparators.pcgr.parser import parse_annotations, read_filters, compare_retention
from somaweave.comparators.pcgr.run import sha256, run

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/comparators/pcgr"


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "input.vcf"
        self.case = load_case(ROOT / "tests/benchmark/01_driver.case.json")
        self.case.alterations[0].position = GenomicPosition(assembly="GRCh38", chromosome="chr7", position=100, reference="A", alternate="T")

    def test_raw_counts_not_templates_and_original_position(self):
        m = self.case.alterations[0].measurements[0]
        m.tumor.unique_templates_alt = 1
        m.tumor.depth = 110
        ledger = export_vcf(self.case, self.out, "synthetic")
        self.assertIn("TVAF=0.3;TDP=110;NVAF=0;NDP=80", self.out.read_text())
        self.assertEqual(ledger[0]["original_position"]["chromosome"], "chr7")
        self.assertEqual(ledger[0]["allele_key"], "7:100:A:T")

    def test_missing_normal_is_not_zero(self):
        self.case.alterations[0].measurements[0].normal = None
        export_vcf(self.case, self.out, "synthetic")
        record = self.out.read_text().splitlines()[-1]
        self.assertNotIn("NVAF=", record)
        self.assertNotIn("NDP=", record)

    def test_filters_and_held_alleles_are_preserved(self):
        m = self.case.alterations[0].measurements[0]
        m.caller_filters = ["LowQual", "NormalSupport"]
        m.qc_flags = ["held"]
        export_vcf(self.case, self.out, "synthetic")
        self.assertIn("LowQual;NormalSupport", self.out.read_text().splitlines()[-1])

    def test_ambiguous_measurements_fail(self):
        self.case.alterations[0].measurements *= 2
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            export_vcf(self.case, self.out, "synthetic")

    def test_missing_coordinates_require_explicit_map(self):
        a = self.case.alterations[0]
        a.position = None
        with self.assertRaisesRegex(ValueError, "no explicit genomic"):
            export_vcf(self.case, self.out, "synthetic")
        mapping = {"A1": {"chrom": "7", "pos": "100", "ref": "A", "alt": "T", "reviewed": "pending_owner"}}
        ledger = export_vcf(self.case, self.out, "synthetic", mapping)
        self.assertEqual(ledger[0]["genomic_map"]["reviewed"], "pending_owner")

    def test_non_small_and_empty_are_not_fake_success(self):
        # Use a freshly validated model with a non-small alteration.
        data = self.case.model_dump(mode="json")
        data["alterations"][0]["alteration_type"] = "CNA"
        from somaweave.domain.case import Case
        self.case = Case.model_validate(data)
        with self.assertRaisesRegex(ValueError, "non-small"):
            export_vcf(self.case, self.out, "synthetic")
        self.case.alterations = []
        with self.assertRaisesRegex(ValueError, "empty"):
            export_vcf(self.case, self.out, "synthetic")

    def test_bad_and_duplicate_alleles_fail(self):
        for args in [("7", 1, "-", "A"), ("7", 0, "A", "C"), ("7", 1, "A", "A")]:
            with self.assertRaises(ValueError):
                allele_key(*args)
        self.case.alterations *= 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            export_vcf(self.case, self.out, "synthetic")

    def test_tissue_lookup_no_hypothesis_substitution(self):
        self.assertEqual(tumor_site("MEL")[0], 24)
        self.assertEqual(tumor_site("unmapped")[0], 0)
        self.assertEqual(tumor_site(None)[0], 0)

    def test_duplicate_map_fails(self):
        p = self.out.with_suffix(".tsv")
        p.write_text("scenario_id\talteration_id\nx\tA1\nx\tA1\n")
        with self.assertRaises(ValueError):
            read_map(p, "x")


class MappingTests(unittest.TestCase):
    def test_mane_selection_uses_gencode_marker(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "xref.tsv.gz"
            with gzip.open(p, "wt") as f:
                f.write("symbol\tgencode_tag\tensembl_transcript_id_full\tmane_select2\nX\tbasic&MANE_Select\tENST1.1\t.\nX\tbasic\tENST2.1\t.\n")
            self.assertEqual(select_mane(p, {"X"})["X"]["ensembl_transcript_id_full"], "ENST1.1")
            with self.assertRaisesRegex(ValueError, "not every"):
                select_mane(p, {"Y"})
            with gzip.open(p, "at") as f:
                f.write("X\tMANE_Select\tENST3.1\t.\n")
            with self.assertRaisesRegex(ValueError, "multiple"):
                select_mane(p, {"X"})

    def model(self, strand=1, cds="GTG"):
        return {"strand": strand, "coding_start": 4, "exons": [{"start": 10, "end": 12}, {"start": 20, "end": 28}],
                "cds": cds, "peptide": "V"}

    def test_forward_and_reverse_cds_mapping(self):
        self.assertEqual(cds_to_genomic(self.model(), 1), 20)
        self.assertEqual(cds_to_genomic(self.model(-1), 1), 25)
        self.assertEqual(cds_to_genomic(self.model(), -3), 9)

    def test_unique_snv_and_reference_residue_check(self):
        self.assertEqual(protein_snv(self.model(), 1, "V", "E"), (21, "T", "A"))
        self.assertEqual(protein_snv(self.model(-1), 1, "V", "E"), (24, "A", "T"))
        with self.assertRaisesRegex(ValueError, "reference residue mismatch"):
            protein_snv(self.model(), 1, "R", "G")

    def test_ambiguous_protein_label_not_guessed(self):
        with self.assertRaisesRegex(ValueError, "not one"):
            protein_snv(self.model(cds="AAA"), 1, "K", "N")

    def test_deletion_and_reverse_complement(self):
        m = self.model(cds="TGGAAG")
        m["peptide"] = "WK"
        self.assertEqual(deletion_interval(m, 1, 2, "W", "K"), (20, 25, "TGGAAG"))
        self.assertEqual(complement("TGGAAG"), "CTTCCA")


class ParserTests(unittest.TestCase):
    def test_readonly_overlap_rejected_before_directory_creation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ("input", "image", "ref", "vep"):
                (root / name).mkdir()
            cfg = {k: str(root / v) for k, v in {"input_vcf": "input", "image": "image", "refdata": "ref", "vep_cache": "vep", "output": "ref/forbidden", "work": "work", "cache": "cache"}.items()}
            cfg.update(sample="synthetic", tumor_site=0)
            p = root / "run.json"; p.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError, "overlaps"):
                run(p)
            self.assertFalse((root / "ref/forbidden").exists())

    def test_native_values_and_duplicate_transcripts_kept(self):
        rows = parse_annotations(FIX / "annotations.tsv")
        self.assertEqual(len(rows["7:100:A:T"]), 2)
        self.assertEqual(rows["7:101:G:A"][0]["ONCOGENICITY"], "VUS")
        self.assertEqual(rows["7:101:G:A"][0]["gnomADe_AF"], "0.05")

    def test_absence_filter_and_technical_unassessed(self):
        rows = parse_annotations(FIX / "annotations.tsv")
        filters = read_filters(FIX / "native_filters.txt")
        ledger = [{"alteration_id": str(i), "allele_key": k} for i, k in enumerate(["7:100:A:T", "7:102:C:T", "7:103:A:G"])]
        result = compare_retention(ledger, rows, filters)
        self.assertTrue(result[0]["retained"])
        self.assertEqual(result[1]["filter_reason"], "LowQual")
        self.assertIn("not exposed", result[2]["filter_reason"])
        self.assertTrue(all(r["technical_axis"] == "not assessed by PCGR" for r in result))

    def test_gzip_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "annotation.tsv.gz"
            with gzip.open(p, "wt") as f:
                f.write((FIX / "annotations.tsv").read_text())
            self.assertEqual(len(parse_annotations(p)), 2)

    def test_wrong_table_and_fuzzy_identity_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.tsv"
            p.write_text("gene\tprotein\nX\tp.V1E\n")
            with self.assertRaises(ValueError):
                parse_annotations(p)
            p.write_text((FIX / "annotations.tsv").read_text().replace("7:g.100A>T", "p.V1E"))
            with self.assertRaisesRegex(ValueError, "identity"):
                parse_annotations(p)

    def test_missing_artifacts_override_false_native_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "input.vcf").write_text("synthetic")
            (root / "image.sif").write_text("synthetic")
            (root / "ref").mkdir(); (root / "vep").mkdir()
            cfg = {k: str(root / v) for k, v in {"input_vcf": "input.vcf", "image": "image.sif", "refdata": "ref", "vep_cache": "vep", "output": "out", "work": "work", "cache": "cache"}.items()}
            cfg.update(sample="synthetic", tumor_site=0)
            config = root / "run.json"; config.write_text(json.dumps(cfg))
            import subprocess
            with patch("somaweave.comparators.pcgr.run.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="apptainer synthetic")):
                self.assertEqual(run(config), 1)
            record = json.loads((root / "out/execution.json").read_text())
            self.assertEqual(record["native_exit_code"], 0)
            self.assertFalse(record["artifacts_complete"])
            self.assertIn("/output/native", record["command"])
            self.assertEqual(record["input_sha256"], sha256(root / "input.vcf"))


if __name__ == "__main__":
    unittest.main()
