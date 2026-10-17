"""Explicit, non-interpreting conversion of reviewed pipeline outputs to case.v2.

Mapping contract:
* Keep every BAM-review allele, including excluded/VUS/held rows, with its exact
  anchored genomic key. Duplicate alleles and ambiguous joins fail closed.
* MAF matching uses gene + VCF position + supplied protein label; raw ref/alt/
  depth are preserved and ALT/depth must agree with the review row. Unmatched
  MAF rows fall back to reported TSV ALT/depth with ref=None, never depth-ALT.
* VCF FILTER is distinct from annotation FILTER. QC columns are decoded JSON
  arrays, never comma-split. No caller/version is inferred from installed tools.
* Template counts, non-exclusive strands, representative-mate medians and local
  clipped-template fractions stay separate from caller read counts. Median NM
  is retained as reported, not relabelled as additional local mismatches.
* PURPLE supplies primary purity/ploidy, overlapping locus CN, explicit LOH if
  present and all supplied alternative models. Raw search grids are not chosen
  or converted to selected alternative modes. No LOH is inferred from minor CN.
* Clinical facts and hypotheses come from explicit input; lab/Picard data only
  supplement methods/specimen measurements. Upstream classifications remain
  quoted annotations, never curated evidence. Case.provenance owns source paths,
  hashes and explicit missing-field decisions. There are no site defaults.
"""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

from somaweave.domain import Case
from .clinical import one, present, read_clinical
from .formats import read_json, table


def number(value,cast=float):
    return cast(value) if present(value) else None


def build_case(*,bam_review,purple,maf,clinical,out,case_id=None,assembly=None,vcf=None,
               clinical_context=None,lab_manifest=None,review_categories=None,picard_tumor=None,
               picard_normal=None,caller=None,caller_provenance=None,alternative_fits=None,purple_disposition=None):
    sources={};decisions=[]
    def source(name,path):
        path=Path(path).resolve()
        sources[name+'.path']=str(path);sources[name+'.sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        return path
    rows=table(source('bam_review',bam_review));mafs=table(source('maf',maf))
    inferred={r.get('case_id') for r in rows if r.get('case_id')}
    if len(inferred)>1 or (case_id and inferred and inferred!={case_id}):raise ValueError('Mixed or mismatched review case IDs')
    case_id=case_id or one(list(inferred),'review case ID')
    if len({r['allele'] for r in rows})!=len(rows):raise ValueError('Duplicate review allele')
    tumor_ids={r['Tumor_Sample_Barcode'] for r in mafs if r.get('Tumor_Sample_Barcode')};normal_ids={r['Matched_Norm_Sample_Barcode'] for r in mafs if r.get('Matched_Norm_Sample_Barcode')}
    data=read_clinical(source('clinical',clinical),case_id,one(list(tumor_ids),'MAF tumour ID',False),one(list(normal_ids),'MAF normal ID',False),source('clinical_context',clinical_context) if clinical_context else None)
    assembly=assembly or data.get('assembly')
    if assembly not in ['GRCh37','GRCh38']:raise ValueError('Assembly must be explicitly supplied in clinical JSON or --assembly')
    tumor=one([s for s in data['specimens'] if s['role']=='tumor'],'clinical tumour specimen');normal=one([s for s in data['specimens'] if s['role']=='normal'],'clinical normal specimen')
    for role,ids,spec in [('tumor',tumor_ids,tumor),('normal',normal_ids,normal)]:
        if ids and ids!={spec['specimen_id']}:raise ValueError(f'{role} clinical/MAF sample mismatch')
    root=Path(purple)
    purity_path=root if root.is_file() else one(list(root.rglob('*.purple.purity.tsv')),'PURPLE primary purity')
    prefix=str(purity_path).removesuffix('.purple.purity.tsv')
    purity=one(table(source('purple_purity',purity_path)),'primary purity row')
    segments=table(source('purple_segments',prefix+'.purple.cnv.somatic.tsv'))
    version_path=Path(purity_path).parent/'purple.version'
    tool='PURPLE'
    if version_path.exists():
        text=source('purple_version',version_path).read_text();match=re.search(r'^version=(.+)$',text,re.M)
        if match:tool+=' '+match.group(1)
    p=tumor.setdefault('purity',{});p.update(molecular_fit=float(purity['purity']),molecular_ploidy=float(purity['ploidy']),molecular_fit_tool=tool)
    tumor['notes']=(tumor.get('notes') or '')+'; native primary fit as reported: '+json.dumps(purity,sort_keys=True)
    if purple_disposition:
        disp=read_json(source('purple_disposition',purple_disposition));p['fit_ambiguous']=bool(disp.get('findings'))
        tumor['notes']+='; source disposition: '+json.dumps(disp.get('findings',[]),sort_keys=True)
    if alternative_fits:
        fits=table(source('alternative_fits',alternative_fits));p['alternative_fits']=[]
        for fit in fits:
            if fit.get('solution','').lower()=='primary':
                if float(fit['purity'])!=p['molecular_fit'] or float(fit['ploidy'])!=p['molecular_ploidy']:raise ValueError('Alternative table primary disagrees with primary PURPLE')
                continue
            p['alternative_fits'].append(dict(purity=float(fit['purity']),ploidy=float(fit['ploidy']),score=number(fit.get('score')),tool=tool,
                 disposition=fit.get('disposition') or '; '.join(f'{k}={fit[k]}' for k in ['solution','status','QCStatus'] if fit.get(k))))
    if lab_manifest:
        lab=table(source('lab_manifest',lab_manifest),',')
        for spec in [tumor,normal]:
            rec=one([r for r in lab if r.get('sample_submitter_id')==spec['specimen_id']],'laboratory sample')
            spec.update(library_kit=rec.get('library_prep_kit') or None,sequencer=rec.get('instrument_model') or None,sequencing_assay='WGS')
            preserv=rec.get('tissue_preservation_method','').lower();kind=rec.get('specimen_type','')
            spec['preservation']='blood' if kind.lower()=='blood' else 'FFPE' if preserv=='ffpe' else 'fresh_frozen' if preserv in ['frozen','fresh frozen'] else 'unknown'
            spec['tissue']=kind or None
            spec['notes']+='; laboratory sample_type_label='+str(rec.get('sample_type_label'))+'; preservation='+str(rec.get('tissue_preservation_method'))
    for role,path,spec in [('tumor',picard_tumor,tumor),('normal',picard_normal,normal)]:
        if path:
            lines=source('picard_'+role,path).read_text().splitlines();index=next(i for i,line in enumerate(lines) if line.startswith('GENOME_TERRITORY\t'))
            metrics=dict(zip(lines[index].split('\t'),lines[index+1].split('\t')));spec['mean_coverage']=float(metrics['MEAN_COVERAGE'])
    if caller_provenance:
        source('caller_provenance',caller_provenance)
    vcfs={}
    if vcf:
        path=source('vcf',vcf);opener=gzip.open if str(path).endswith('.gz') else open
        with opener(path,'rt') as stream:
            for line in stream:
                if line.startswith('#'):continue
                fields=line.rstrip().split('\t')
                for alt in fields[4].split(','):vcfs[f'{fields[0]}:{fields[1]}:{fields[3]}:{alt}']=fields[6].split(';')
    categories={r['allele']:r for r in read_json(source('review_categories',review_categories))} if review_categories else {}
    alterations=[]
    for row in rows:
        key=row['allele'];chrom,pos,ref,alt=key.split(':');pos=int(pos)
        matches=[r for r in mafs if r.get('Hugo_Symbol')==row['gene'] and r.get('vcf_pos',r.get('Start_Position'))==str(pos) and r.get('HGVSp_Short','')==row.get('vep_protein','')]
        if len(matches)>1:raise ValueError('Ambiguous MAF allele join: '+key)
        record=matches[0] if matches else {}
        if not record:decisions.append('No MAF row for '+key+'; caller REF count remains unknown')
        annotation={k+'_as_reported':str(row[k]) for k in ['gene','oncogenicity','oncokb_level','decision','decision_reason','gnomad_af','gnomad_popmax','source_clin_sig','clinvar_germline_classification','review_flags','bam_review_flags','bam_visual_state'] if k in row}
        supports={}
        for role,prefix in [('tumor','t'),('normal','n')]:
            metrics=json.loads(row.get('bam_'+role+'_details') or '{}')
            support=dict(ref_count=number(record.get(prefix+'_ref_count'),int),alt_count=number(record.get(prefix+'_alt_count',row.get(role+'_alt')),int),depth=number(record.get(prefix+'_depth',row.get(role+'_depth')),int),reported_vaf=number(row.get(role+'_vaf_percent')))
            if support['reported_vaf'] is not None:support['reported_vaf']/=100
            for raw,col in [('alt_count','alt'),('depth','depth')]:
                if present(row.get(role+'_'+col)) and support[raw]!=int(row[role+'_'+col]):raise ValueError('MAF/review count mismatch: '+key)
            for dest,src in [('unique_templates_alt','alt_templates'),('unique_templates_ref','ref_templates'),('unique_templates_total','informative_depth'),('alt_templates_forward','alt_forward'),('alt_templates_reverse','alt_reverse'),('median_mapq','alt_median_mapq'),('median_baseq_alt','alt_median_baseq')]:
                support[dest]=metrics.get(src,number(row.get('bam_'+role+'_'+src)))
            support['alt_templates_strand_exclusive']=False if support['alt_templates_forward'] is not None and support['alt_templates_reverse'] is not None else None
            a=support['unique_templates_alt'];support['clipped_fraction_alt']=metrics['alt_local_clip']/a if a and 'alt_local_clip' in metrics else None
            visual=row.get('bam_visual_state') if role=='tumor' else row.get('bam_normal_visual_state')
            if present(visual) and visual!='NOT_REVIEWED':support['visual_review']=dict(outcome=visual,note='Paired-locus review state as recorded' if role=='tumor' else 'Normal visual state as recorded')
            supports[role]=support;annotation[role+'_bam_metrics_as_reported']=json.dumps(metrics,sort_keys=True)
        intervals=[s for s in segments if s['chromosome'].removeprefix('chr')==chrom.removeprefix('chr') and int(s['start'])<=pos<=int(s['end'])]
        if len(intervals)>1:raise ValueError('Overlapping PURPLE segments: '+key)
        cn=None
        if intervals:
            seg=intervals[0];legacy=seg.get('caller_reported_loh')
            if present(legacy):
                if str(legacy).lower() not in ['true','false','1','0']:raise ValueError('Unrecognized explicit LOH Boolean')
                legacy=str(legacy).lower() in ['true','1']
            else:legacy=None
            call=seg.get('loh_call') or ('loh' if legacy else 'no_loh' if legacy is False else 'not_called')
            cn=dict(total_copy_number=number(seg.get('copyNumber')),minor_allele_copy_number=number(seg.get('minorAlleleCopyNumber')),major_allele_copy_number=number(seg.get('majorAlleleCopyNumber')),loh_call=call,loh_source=tool+' segment (no explicit locus call)' if call=='not_called' else tool,source_tool=tool)
            cn['caller_reported_loh']=legacy
            annotation['purple_interval_as_reported']=json.dumps(seg,sort_keys=True)
        flags=json.loads(row.get('bam_review_flags') or '[]')
        if not isinstance(flags,list) or not all(isinstance(f,str) for f in flags):raise ValueError('bam_review_flags must encode a JSON array of strings')
        filters=vcfs.get(key,[])
        if vcf and key not in vcfs:raise ValueError('Review allele absent from supplied VCF: '+key)
        annotation['annotation_filter_as_reported']=record.get('FILTER',row.get('source_filter',''))
        annotation['caller_filter_as_reported']=';'.join(filters)
        if key in categories:
            for field in ['report_category','decision','decision_reason']:annotation[field+'_as_reported']=str(categories[key].get(field,''))
        ex=record.get('EXON') or record.get('Exon_Number');exon=total=None
        if ex and re.fullmatch(r'\d+/\d+',ex):exon,total=map(int,ex.split('/'))
        elif ex:decisions.append('Unstructured exon label retained without inference: '+key+' '+ex)
        alteration=dict(alteration_id=key,alteration_type='SNV' if len(ref)==len(alt)==1 else 'MNV' if len(ref)==len(alt) else 'insertion' if len(ref)<len(alt) else 'deletion',
            gene_symbol=row['gene'],transcript=record.get('Transcript_ID') or None,hgvs_p=(record.get('HGVSp') or row.get('vep_protein') or '').split(':')[-1] or None,hgvs_c=record.get('HGVSc') or None,
            consequence=record.get('Consequence') or None,exon=exon,exon_count=total,region_source=(record.get('Transcript_ID','')+'; supplied MAF EXON') if exon else None,
            position=dict(assembly=assembly,chromosome=chrom,position=pos,reference=ref,alternate=alt),annotations=annotation,
            measurements=[dict(specimen_id=tumor['specimen_id'],tumor=supports['tumor'],normal=supports['normal'],copy_number=cn,caller=caller,caller_filters=filters,qc_flags=flags)])
        alterations.append(alteration)
    fields={k:v for k,v in data.items() if k in Case.model_fields and k not in ['alterations','schema_version']}
    sources.update({'mapping_version':'case-v2/1','decisions':json.dumps(decisions),'measurement_units':'Quality-filtered informative templates; strands non-exclusive; clipped fraction local to source window; median NM not additional mismatches','loh_not_called_semantics':'No explicit per-locus call supplied; not a claim that the entire LOH analysis was unperformed'})
    for module in ['build.py','clinical.py','formats.py']:sources['ingest.'+module+'.sha256']=hashlib.sha256(Path(__file__).with_name(module).read_bytes()).hexdigest()
    fields.update(case_id=case_id,assembly=assembly,alterations=alterations,provenance={**data.get('provenance',{}),**sources})
    case=Case.model_validate(fields);output=Path(out)
    if output.exists():raise ValueError('Refusing to overwrite an existing case file')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:stream.write(case.model_dump_json(indent=2)+'\n')
    return case


def build_manifest(path):
    """Build literal manifest rows in their given order; paths resolve relative to it."""
    path=Path(path).resolve();data=read_json(path);outputs=[]
    path_fields={'bam_review','purple','maf','clinical','out','clinical_context','lab_manifest','vcf','review_categories','picard_tumor','picard_normal','caller_provenance','alternative_fits','purple_disposition'}
    for original in data['cases']:
        row=dict(original)
        for key in path_fields&row.keys():
            if row[key] is not None:row[key]=path.parent/row[key]
        case=build_case(**row);outputs.append(dict(case_id=case.case_id,out=str(row['out']),variants=len(case.alterations)))
    return outputs
