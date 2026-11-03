"""Deterministic explanations tied to supplied measurements and model scope."""
from datetime import datetime,timezone
import math

UNITS={'systolic_bp':'mmHg','diastolic_bp':'mmHg','total_cholesterol':'mg/dL','hdl':'mg/dL',
       'ldl':'mg/dL','triglycerides':'mg/dL','glucose':'mg/dL','fasting_blood_sugar':'mg/dL',
       'creatinine':'mg/dL','hba1c':'%','potassium':'mmol/L','sodium':'mmol/L',
       'hemoglobin':'g/dL','wbc':'10^9/L'}

def build_evidence_report(clinical,modality,input_quality,rhythm,conditions):
    measurements=[]
    for key,unit in UNITS.items():
        if clinical.get(key) in (None,''):continue
        try:value=float(clinical[key])
        except (ValueError,TypeError):continue
        if math.isfinite(value):measurements.append({'field':key,'value':value,'unit':unit,
                                                    'source':'supplied input; original measurement and date require confirmation'})
    missing=[key for key in ('age','sex','creatinine') if clinical.get(key) in (None,'')]
    if clinical.get('glucose') in (None,'') and clinical.get('fasting_blood_sugar') in (None,''):missing.append('glucose')
    summary=[{'title':'Assessment scope','text':'ICD outputs estimate linked diagnosis groups; ECG pattern and AF rhythm scores describe separate annotation targets.'},
             {'title':'Inputs assessed','text':('Digital ECG plus clinical inputs with dedicated model preprocessing.' if modality=='ecg_clinical' else 'Clinical-only ICD estimates; waveform results, when present, are separate.')},
             {'title':'Missing trained inputs','text':', '.join(missing) if missing else 'Core demographic and lab inputs supplied; measurement dates and source accuracy still require review.'},
             {'title':'Diagnostic limits','text':'Acute MI and conduction-block decisions remain inconclusive. A low score cannot exclude disease. A high health index is not clinical reassurance.'}]
    if input_quality:summary.append({'title':'Signal checks','text':input_quality['status']+'. '+(' '.join(input_quality['warnings']) or 'Duration, variation and amplitude checks passed. Correct lead placement and units are not independently verified.')})
    if rhythm:summary.append({'title':'AF rhythm research result','text':f"AF annotation score {rhythm['probability']*100:.1f}%; review marker {rhythm['threshold']*100:.1f}%. This is a separate digital 12-lead rhythm model, not confirmation of AF."})
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'summary':summary,'measurements':measurements,
            'missing_trained_inputs':missing,'explanation_method':'Reviewed deterministic templates; no generated diagnosis or invented measurements',
            'discussion_prompt':'Review the original ECG, measurement dates, units, symptoms and history with a clinician. These outputs alone do not determine diagnosis or medication.'}
