"""Clinical conversion: recorded dates, diagnoses, roles and treatments only.

Workbook donors match exact IDs or a terminal hyphen-delimited case identifier;
multiple matching donors/specimens are errors. Tumour/normal roles come from
Sample Registration, never guessed from a specimen name. Diagnosis names and
OncoTree/hypotheses require a supplied clinical JSON or context; absent names
are explicitly labelled unavailable, never inferred from therapy or variants.
The JSON form accepts canonical clinical case fields, or the released flat
clinical_context form with clinical_rows. Context overrides are explicit and
both source files remain hashed in provenance. Dates keep their recorded precision.
"""
import json
from pathlib import Path

from .formats import read_json, xlsx


def present(value):
    return value not in [None,'','NA','N/A','Not applicable','Unknown']


def one(rows,label,required=True):
    if len(rows)>1 or (required and not rows):raise ValueError(f'Expected one {label}, found {len(rows)}')
    return rows[0] if rows else {}


def context_fields(data):
    if 'diagnosis' in data:return data
    fields={}
    for source,dest in [('primary_cancer','name'),('oncotree_code','oncotree_code'),('histology_code','icd_o_morphology'),('cancer_type_code','icd_o_topography'),('site_of_biopsy','primary_site'),('tumor_grade','grade')]:
        if present(data.get(source)):fields[dest]=data[source]
    return {'diagnosis':fields} if fields else {}


def read_clinical(path,case_id,tumor_id,normal_id,context=None):
    path=Path(path)
    if path.suffix.lower()=='.xlsx':
        result=from_sheets(xlsx(path),case_id,tumor_id,normal_id)
    else:
        data=read_json(path)
        if 'clinical_rows' in data:
            sheets={k:[r.get('record',r) for r in v] for k,v in data['clinical_rows'].items()}
            result=from_sheets(sheets,case_id,tumor_id,normal_id)
            result['diagnosis'].update(context_fields(data).get('diagnosis',{}))
        else:result=data
    if result.get('case_id') not in [None,case_id]:raise ValueError('Clinical case_id does not match the supplied review case')
    if context:
        overlay=context_fields(read_json(context))
        for key,value in overlay.items():
            if key=='diagnosis':result.setdefault(key,{}).update(value)
            elif key in ['case_id','assembly','disease_hypotheses','clinical_events','notes']:result[key]=value
    return result


def from_sheets(sheets,case_id,tumor_id,normal_id):
    def rows(sheet):
        return [r for r in sheets.get(sheet,[]) if str(r.get('submitter_donor_id',''))==case_id or str(r.get('submitter_donor_id','')).endswith('-'+case_id)]
    donors={r['submitter_donor_id'] for name in sheets for r in rows(name) if r.get('submitter_donor_id')}
    if len(donors)!=1:raise ValueError('Clinical donor identity is absent or ambiguous')
    donor=one(rows('Donor'),'donor',False);primary=one(rows('Primary Diagnosis'),'primary diagnosis')
    specimens=[];tumor_source={}
    for role,sample in [('tumor',tumor_id),('normal',normal_id)]:
        regs=[r for r in rows('Sample Registration') if str(r.get('tumour_normal_designation','')).lower() in (['tumour','tumor'] if role=='tumor' else ['normal'])]
        reg=one(regs,role+' registration')
        source=one([r for r in rows('Specimen') if r['submitter_specimen_id']==reg['submitter_specimen_id']],role+' specimen')
        specimen=dict(specimen_id=sample,role=role,anatomical_site=source.get('specimen_anatomic_location'),
                      collection_date=source.get('specimen_collection_date'),storage=source.get('specimen_storage'),
                      notes='Clinical specimen '+source['submitter_specimen_id']+'; sample '+str(reg.get('submitter_sample_id')))
        if role=='tumor':
            tumor_source=source;specimen['is_metastatic_site']='metastatic' in str(reg.get('specimen_type','')).lower()
            raw=source.get('percent_tumour_cells_range')
            if present(raw):
                lo,hi=[float(x.strip())/100 for x in str(raw).replace('%','').split('-')]
                specimen['purity']=dict(pathology_min=lo,pathology_max=hi)
        specimens.append(specimen)
    diagnosis=dict(name='Diagnosis name not supplied',icd_o_morphology=tumor_source.get('tumour_histological_type'),
                   icd_o_topography=primary.get('cancer_type_code'),primary_site=primary.get('primary_site'),
                   diagnosis_date=primary.get('date_of_diagnosis'),confirmed_by_pathology=tumor_source.get('reference_pathology_confirmed_diagnosis')=='Yes')
    for src,key in [(primary,'clinical_stage_group'),(tumor_source,'tumour_grade')]:
        if present(src.get(key)):diagnosis['stage' if key=='clinical_stage_group' else 'grade']=src[key]
    details={r.get('submitter_treatment_id'):r for s in ['Systemic Therapy','Surgery','Radiation'] for r in rows(s)}
    treatments=[]
    for row in rows('Treatment'):
        tid=row['submitter_treatment_id Surgery - SURG Systemic Therapy - SYST Radiation - RADI Other - OTHE'];detail=details.get(tid,{})
        kind=str(row.get('treatment_type','')).lower()
        modality='surgery' if 'surg' in kind else 'radiation' if 'radi' in kind else 'systemic' if 'system' in kind else 'other'
        t=dict(treatment_id=tid,name=detail.get('drug_name') or detail.get('surgery_type') or detail.get('radiation_therapy_type') or row.get('treatment_type','Unspecified treatment'),
               agents=[detail['drug_name']] if detail.get('drug_name') else [],modality=modality,intent=row.get('treatment_intent'),
               start_date=row.get('treatment_start_date (Format YYYY-MM)'),end_date=row.get('treatment_end_date (Format YYYY-MM)'),
               notes=json.dumps(detail,ensure_ascii=False),response_notes='Response and ongoing status not recorded; neither inferred.')
        if present(detail.get('drug_reference_identifier')):
            t['agent_identifiers']={str(detail.get('drug_reference_database')):str(detail['drug_reference_identifier'])}
        treatments.append(t)
    result=dict(case_id=case_id,diagnosis=diagnosis,specimens=specimens,treatments=treatments,
                clinical_events=[dict(event_type='diagnosis',event_date=primary.get('date_of_diagnosis'),site=primary.get('primary_site'),description='Primary diagnosis history as recorded; not an inferred date of a later sampled lesion.')])
    if donor.get('sex_at_birth'):result['sex']=donor['sex_at_birth']
    if present(donor.get('date_of_birth')) and present(primary.get('date_of_diagnosis')):
        by,bm=map(int,str(donor['date_of_birth']).split('-'));dy,dm=map(int,str(primary['date_of_diagnosis']).split('-'))
        if bm!=dm:result['age_at_diagnosis_years']=dy-by-(dm<bm)
    return result
