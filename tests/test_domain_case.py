import json
import unittest
from datetime import date
from pathlib import Path

from somaweave.domain import (
    Alteration, AlterationMeasurement, AlterationType, Assembly, Case, Diagnosis,
    GenomicPosition, Preservation, ReadSupport, Specimen, SpecimenRole, TreatmentEvent,
)
from somaweave.domain.io import CaseValidationError, case_from_dict, dump_model, load_case

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic_case.json"


def minimal_case(**overrides) -> dict:
    data = {
        "case_id": "C1",
        "assembly": "GRCh38",
        "diagnosis": {"name": "Colon adenocarcinoma", "oncotree_code": "COAD"},
        "specimens": [{"specimen_id": "T1", "role": "tumor", "preservation": "FFPE"}],
        "alterations": [],
    }
    data.update(overrides)
    return data


class CaseModelTests(unittest.TestCase):
    def test_example_loads_and_roundtrips(self):
        case = load_case(EXAMPLE)
        self.assertEqual(case.case_id, "SYN-0001")
        self.assertEqual(len(case.alterations), 2)
        self.assertEqual(len(case.tumor_specimens()), 1)
        again = case_from_dict(dump_model(case))
        self.assertEqual(again, case)

    def test_extra_fields_rejected(self):
        with self.assertRaises(CaseValidationError) as ctx:
            case_from_dict(minimal_case(unexpected="x"))
        self.assertIn("unexpected", ctx.exception.pretty())

    def test_unknown_specimen_reference_rejected(self):
        alt = {"alteration_id": "A1", "alteration_type": "SNV", "gene_symbol": "KRAS", "hgvs_p": "p.Gly12Asp",
               "measurements": [{"specimen_id": "NOPE"}]}
        with self.assertRaises(CaseValidationError):
            case_from_dict(minimal_case(alterations=[alt]))

    def test_assembly_mismatch_rejected(self):
        alt = {"alteration_id": "A1", "alteration_type": "SNV", "gene_symbol": "KRAS",
               "position": {"assembly": "GRCh37", "chromosome": "12", "position": 25398284, "reference": "C", "alternate": "T"}}
        with self.assertRaises(CaseValidationError):
            case_from_dict(minimal_case(alterations=[alt]))

    def test_small_variant_needs_identity(self):
        alt = {"alteration_id": "A1", "alteration_type": "SNV", "gene_symbol": "KRAS"}
        with self.assertRaises(CaseValidationError):
            case_from_dict(minimal_case(alterations=[alt]))

    def test_read_support_count_consistency(self):
        with self.assertRaises(ValueError):
            ReadSupport(ref_count=50, alt_count=60, depth=100)
        rs = ReadSupport(ref_count=40, alt_count=10, depth=50)
        self.assertEqual(rs.alt_count, 10)

    def test_treatment_dates_ordered(self):
        with self.assertRaises(ValueError):
            TreatmentEvent(treatment_id="T", name="x", start_date=date(2024, 5, 1), end_date=date(2024, 1, 1))

    def test_purity_estimates_are_separate_fields(self):
        case = load_case(EXAMPLE)
        p = case.specimen("T1").purity
        self.assertIsNotNone(p.pathology_min)
        self.assertIsNotNone(p.molecular_fit)
        self.assertNotEqual(p.pathology_min, p.molecular_fit)

    def test_duplicate_ids_rejected(self):
        data = minimal_case(specimens=[{"specimen_id": "T1", "role": "tumor"}, {"specimen_id": "T1", "role": "normal"}])
        with self.assertRaises(CaseValidationError):
            case_from_dict(data)

    def test_dump_serialises_enums_and_dates(self):
        case = load_case(EXAMPLE)
        d = dump_model(case)
        self.assertEqual(d["assembly"], "GRCh38")
        self.assertEqual(d["specimens"][0]["preservation"], "FFPE")
        self.assertEqual(d["treatments"][0]["start_date"], "2025-02-03")
        json.dumps(d)


if __name__ == "__main__":
    unittest.main()
