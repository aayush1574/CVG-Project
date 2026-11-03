"""Evaluate a genuinely independent labeled cohort without fitting any model.

Manifest CSV: record_path, subject_id, sample_rate, age, sex, and optional
clinical_json, AFIB, NORM, MI, STTC, CD, HYP, I48, I50, I25, I21, I44.
Values in outcome columns must be 0/1; blank labels are not assumed negative.
The caller is responsible for adjudication, independence and data permissions.
"""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['MKL_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import argparse,json
from pathlib import Path
import pandas as pd,numpy as np,torch
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
from fastapi.testclient import TestClient
from app.backend.main import app

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--dataset-name',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    torch.set_num_threads(2)
    data=pd.read_csv(args.manifest)
    if not {'record_path','subject_id','sample_rate'}.issubset(data.columns):raise ValueError('Manifest requires record_path, subject_id, sample_rate')
    if data.subject_id.isna().any():raise ValueError('Subject IDs are required for patient-level evaluation')
    client=TestClient(app);results=[]
    for row in data.itertuples():
        record=Path(row.record_path);record=record if record.is_absolute() else args.manifest.parent/record
        clinical=json.loads(row.clinical_json) if hasattr(row,'clinical_json') and isinstance(row.clinical_json,str) else {}
        for key in ('age','sex'):
            value=getattr(row,key,None)
            if value is not None and not pd.isna(value):clinical[key]=value
        files={'ecg':(record.name,record.read_bytes())}
        if record.suffix.lower() in {'.hea','.dat'}:
            other=record.with_suffix('.dat' if record.suffix.lower()=='.hea' else '.hea');files['header']=(other.name,other.read_bytes())
        response=client.post('/api/predict',data={'clinical_json':json.dumps(clinical),'sample_rate':str(int(row.sample_rate))},files=files)
        result={'subject_id':str(row.subject_id),'status':response.status_code,'scores':{},'truth':{}}
        if response.status_code==200:
            body=response.json();scores={**body.get('disease_probabilities',{}),**(body.get('ecg_superclass_probabilities') or {})}
            if body.get('rhythm_assessment'):scores['AFIB']=body['rhythm_assessment']['probability']
            for label,p in scores.items():
                truth=getattr(row,label,None)
                if truth is not None and not pd.isna(truth):
                    if truth not in (0,1):raise ValueError(f'{label} truth must be 0/1 or blank')
                    result['scores'][label]=p;result['truth'][label]=int(truth)
        results.append(result)
    summary={}
    for label in sorted({key for r in results for key in r['truth']}):
        paired=[r for r in results if label in r['scores']];y=np.asarray([r['truth'][label] for r in paired]);p=np.asarray([r['scores'][label] for r in paired])
        summary[label]={'rows':len(y),'positives':int(y.sum()),'auroc':float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None,'average_precision':float(average_precision_score(y,p)) if y.sum() else None,'brier':float(brier_score_loss(y,p))}
    args.output.write_text(json.dumps({'dataset':args.dataset_name,'manifest_rows':len(data),'accepted_rows':sum(r['status']==200 for r in results),'metrics':summary,'records':results,'limitations':'Independence and label adjudication must be established outside this script; no automatic clinical validation claim.'},indent=2))

if __name__=='__main__':main()
