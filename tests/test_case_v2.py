"""Case v2 contracts and scientific regressions, using synthetic observations."""
import json
from pathlib import Path
import unittest

from pydantic import ValidationError
from somaweave.domain import (Alteration, AlterationMeasurement, Case, CopyNumberState, PurityEstimate,
                             PurityFit, ReadSupport, Specimen, VisualReview)
from somaweave.domain.io import load_case
from somaweave.evidence.applicability import applicability_for
from somaweave.technical import assess_alteration
from somaweave.technical.allele_fractions import observed_vaf
from somaweave.technical.expected_vaf import evaluate_scenarios
from somaweave.technical.ffpe import ffpe_assessment
from somaweave.domain import Preservation
from tests.test_evidence_applicability import _rec, _alt

ROOT = Path(__file__).resolve().parents[1]


class CaseV2Tests(unittest.TestCase):
    def test_v1_loads_without_migration_and_default_is_v2(self):
        legacy = load_case(ROOT/'tests/fixtures/domain/case_v1.json')
        self.assertEqual(legacy.schema_version, 'case.v1')
        self.assertIsNone(legacy.alterations[0].exon)
        self.assertEqual(legacy.specimens[0].purity.alternative_fits, [])
        data=json.loads((ROOT/'examples/synthetic_case.json').read_text())
        data['schema_version']='case.v1'
        self.assertEqual(Case.model_validate(data).schema_version,'case.v1')
        data.pop('schema_version')
        self.assertEqual(Case.model_validate(data).schema_version,'case.v2')
        self.assertTrue((ROOT/'schemas/case.v1.schema.json').exists())

    def test_nested_models_forbid_extra_fields(self):
        for cls,kwargs in [(VisualReview,dict(outcome='supported')), (PurityFit,dict(purity=.3,ploidy=2,tool='caller'))]:
            with self.assertRaises(ValidationError):cls(**kwargs,unexpected='x')

    def test_exon_bounds(self):
        for exon,count in [(0,2),(3,2)]:
            with self.assertRaises(ValidationError):_alt('CTNNB1','p.D32N',exon=exon,exon_count=count)

    def test_verified_region_matching_and_unknown_context(self):
        record=_rec('CTNNB1 Exon 3 Mutation','CTNNB1')
        for exon,expected in [(3,(True,True)),(4,(False,False)),(None,(True,False))]:
            with self.subTest(exon=exon):
                app=applicability_for(record,_alt('CTNNB1','p.D32N',exon=exon))
                self.assertEqual((app.applicable,app.variant_matched),expected)

    def test_exon_range_and_compound_requirements(self):
        a=_alt('PIK3CA','p.E545K',exon=10)
        self.assertTrue(applicability_for(_rec('PIK3CA Exon 9-11 Mutation','PIK3CA'),a).variant_matched)
        self.assertFalse(applicability_for(_rec('PIK3CA Exon 21 Mutation AND PIK3CA Exon 10 Mutation','PIK3CA'),a).applicable)
        self.assertTrue(applicability_for(_rec('PIK3CA Exon 21 Mutation OR PIK3CA Exon 10 Mutation','PIK3CA'),a).variant_matched)

    def test_loh_is_reported_without_copy_number_and_never_derived(self):
        spec=Specimen(specimen_id='T',role='tumor',purity=PurityEstimate(pathology_min=.3))
        for call in ['loh','no_loh','not_called']:
            state=CopyNumberState(loh_call=call,loh_source='caller')
            result=evaluate_scenarios(spec,AlterationMeasurement(specimen_id='T',copy_number=state),observed_vaf(ReadSupport(alt_count=90,depth=100)))
            self.assertEqual(result.loh_call,call)
            self.assertEqual(result.loh_source,'caller')
        result=evaluate_scenarios(spec,AlterationMeasurement(specimen_id='T',copy_number=CopyNumberState(caller_reported_loh=True,loh_call='not_called')),observed_vaf(ReadSupport(alt_count=90,depth=100)))
        self.assertEqual(result.loh_call,'not_called');self.assertTrue(result.caller_reported_loh)
        legacy=evaluate_scenarios(spec,AlterationMeasurement(specimen_id='T',copy_number=CopyNumberState(caller_reported_loh=False)),observed_vaf(ReadSupport(alt_count=90,depth=100)))
        self.assertEqual(legacy.loh_call,'no_loh')

    def test_alternative_models_all_enumerated_without_ranking(self):
        fits=[PurityFit(purity=.2,ploidy=2,score=.4,tool='caller',disposition='warn'),PurityFit(purity=.7,ploidy=5,score=.1,tool='caller',disposition='pass')]
        spec=Specimen(specimen_id='T',role='tumor',purity=PurityEstimate(molecular_fit=.3,alternative_fits=fits))
        result=evaluate_scenarios(spec,AlterationMeasurement(specimen_id='T',copy_number=CopyNumberState(total_copy_number=3)),observed_vaf(ReadSupport(alt_count=30,depth=100)))
        alternatives=[p for p in result.purity_evaluations if p.purity_source=='alternative_fit']
        self.assertEqual([(p.fit_index,p.purity,p.fit_disposition,p.fit_ploidy) for p in alternatives],[(0,.2,'warn',2),(1,.7,'pass',5)])
        self.assertTrue(all(p.scenarios for p in alternatives))
        self.assertEqual(spec.purity.molecular_fit,.3)
        self.assertEqual(spec.purity.alternative_fits,fits)
        self.assertTrue(any('without selection' in n for n in result.notes))

    def test_nonexclusive_template_pvalue_is_not_a_major_flag(self):
        a=_alt('GENE','p.A1T')
        for exclusive in [True,False]:
            support=ReadSupport(alt_count=10,depth=50,alt_templates_forward=10,alt_templates_reverse=0,alt_templates_strand_exclusive=exclusive)
            result=ffpe_assessment(a,support,Preservation.FRESH_FROZEN)
            self.assertLess(result.strand.p_value,.05)
            self.assertEqual('strand_imbalance' in result.flags,exclusive)
            self.assertEqual(bool(result.strand.independence_caveat),not exclusive)

    def test_frozen_v1_schema_accepts_original_example(self):
        import jsonschema
        jsonschema.validate(json.loads((ROOT/'tests/fixtures/domain/case_v1.json').read_text()),
                            json.loads((ROOT/'schemas/case.v1.schema.json').read_text()))

    def test_structured_visual_review_is_quoted_on_both_roles(self):
        for role in ['tumor','normal']:
            case=load_case(ROOT/'examples/synthetic_case.json')
            m=case.alterations[0].measurements[0]
            review=VisualReview(outcome='artifact',reviewer_role='research reviewer',note='Observed locally',reviewed_at='2025-08')
            getattr(m,role).visual_review=review
            assessment=assess_alteration(case,case.alterations[0])[0]
            self.assertEqual(assessment.level,'unreliable')
            self.assertIn('review_outcome:artifact',assessment.flags)
            self.assertTrue(any(role+' visual review as reported' in n and 'Observed locally' in n for n in assessment.rationale))

    def test_v2_metadata_preserves_original_values(self):
        case=load_case(ROOT/'examples/synthetic_case.json')
        self.assertEqual(case.schema_version,'case.v2')
        self.assertTrue(case.provenance)
        self.assertTrue(case.specimens[0].storage)
        self.assertTrue(case.treatments[0].modality)
        self.assertTrue(case.alterations[0].region_source)


if __name__=='__main__':unittest.main()
