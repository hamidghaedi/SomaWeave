"""Synthetic multi-source ingestion, no network and no patient rows."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from zipfile import ZipFile

from somaweave.cli import main
from somaweave.ingest import build_case, build_manifest
from somaweave.ingest.clinical import from_sheets
from somaweave.ingest.formats import table, xlsx

FIX=Path(__file__).parent/'fixtures/ingest'


class IngestTests(unittest.TestCase):
    def options(self,root):
        return dict(bam_review=FIX/'review.tsv',purple=FIX,maf=FIX/'variants.maf',clinical=FIX/'clinical.json',out=Path(root)/'case.json',vcf=FIX/'variants.vcf.txt',alternative_fits=FIX/'alternative_fits.tsv')

    def test_all_rows_counts_units_and_quoted_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=build_case(**self.options(tmp))
            self.assertEqual(len(case.alterations),5)
            a=case.alterations[0];m=a.measurements[0]
            self.assertEqual((m.tumor.ref_count,m.tumor.alt_count,m.tumor.depth),(88,12,100))
            self.assertEqual((m.tumor.unique_templates_alt,m.tumor.unique_templates_total),(10,70))
            self.assertAlmostEqual(m.tumor.clipped_fraction_alt,.1)
            self.assertIs(m.tumor.alt_templates_strand_exclusive,False)
            self.assertIsNone(m.tumor.local_mismatch_alt)
            self.assertEqual((a.exon,a.exon_count),(2,8))
            self.assertEqual(m.caller_filters,['PASS'])
            self.assertEqual(a.annotations['annotation_filter_as_reported'],'common_variant')
            self.assertEqual(case.alterations[1].measurements[0].qc_flags,['FLAG_A','FLAG_B'])
            self.assertEqual(case.alterations[1].measurements[0].tumor.visual_review.outcome,'LOCAL_ARTIFACT_SUSPECTED')
            self.assertEqual(m.copy_number.loh_call,'not_called')
            self.assertIsNone(case.alterations[2].measurements[0].tumor.ref_count)
            self.assertIn('No MAF row',case.provenance['decisions'])
            self.assertEqual(case.specimens[0].purity.alternative_fits[0].purity,.2)
            self.assertTrue(case.provenance['maf.sha256'])
            self.assertEqual(case.specimens[0].collection_date,'2024-03')
            with self.assertRaisesRegex(ValueError,'overwrite'):build_case(**self.options(tmp))

    def test_duplicate_alleles_and_bad_qc_fail(self):
        for change in ['duplicate','bad_qc']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                rows=table(FIX/'review.tsv')
                if change=='duplicate':rows.append(dict(rows[0]))
                else:rows[0]['bam_review_flags']='{"flag":"not an array"}'
                path=Path(tmp)/'bad.tsv'
                with path.open('w') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
                opts=self.options(tmp);opts['bam_review']=path
                with self.assertRaises(ValueError):build_case(**opts)
                self.assertFalse(opts['out'].exists())

    def test_ambiguous_maf_and_count_disagreement_fail(self):
        for bad in ['duplicate','count']:
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as tmp:
                rows=table(FIX/'variants.maf')
                if bad=='duplicate':rows.append(dict(rows[0]))
                else:rows[0]['t_alt_count']='13'
                p=Path(tmp)/'bad.maf'
                with p.open('w') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
                opts=self.options(tmp);opts['maf']=p
                with self.assertRaises(ValueError):build_case(**opts)

    def test_cli_and_batch_use_explicit_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            options=self.options(tmp)
            args=['build-case']
            for k,v in options.items():args+=['--'+k.replace('_','-'),str(v)]
            with redirect_stdout(io.StringIO()):self.assertEqual(main(args),0)
            options['out']=Path(tmp)/'batch.json';manifest=Path(tmp)/'manifest.json'
            manifest.write_text(json.dumps({'cases':[{k:str(v) for k,v in options.items()}]}))
            result=build_manifest(manifest);self.assertEqual(result[0]['variants'],5)
            with redirect_stderr(io.StringIO()):self.assertEqual(main(['build-case','--maf','missing']),1)

    def test_xlsx_reads_sparse_cells_and_inline_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tiny.xlsx'
            with ZipFile(path,'w') as z:
                z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Donor" r:id="rId1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>submitter_donor_id</t></is></c><c r="C1" t="inlineStr"><is><t>year</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>SYN-BUILD-1</t></is></c><c r="C2"><v>2024</v></c></row></sheetData></worksheet>')
            self.assertEqual(xlsx(path)['Donor'],[{'submitter_donor_id':'SYN-BUILD-1','year':2024}])

    def test_workbook_roles_never_come_from_specimen_names(self):
        donor='SYN-BUILD-1'
        sheets={'Primary Diagnosis':[dict(submitter_donor_id=donor,date_of_diagnosis='2024-01')],
                'Sample Registration':[dict(submitter_donor_id=donor,submitter_specimen_id='unlabelled-A',tumour_normal_designation='Tumour'),dict(submitter_donor_id=donor,submitter_specimen_id='unlabelled-B',tumour_normal_designation='Normal')],
                'Specimen':[dict(submitter_donor_id=donor,submitter_specimen_id='unlabelled-A',percent_tumour_cells_range='20-50%',specimen_collection_date='2024-03'),dict(submitter_donor_id=donor,submitter_specimen_id='unlabelled-B',specimen_collection_date='2024-02')]}
        case=from_sheets(sheets,donor,'T','N')
        self.assertEqual(case['specimens'][0]['purity'],{'pathology_min':.2,'pathology_max':.5})
        self.assertIsNone(case['diagnosis'].get('oncotree_code'))
        self.assertEqual(case['specimens'][1]['collection_date'],'2024-02')


if __name__=='__main__':unittest.main()
