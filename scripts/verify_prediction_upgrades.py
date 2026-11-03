import os
os.environ['OMP_NUM_THREADS']='2';os.environ['MKL_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
os.environ['CVG_MODELS_DIR']=r'D:\CVG Project\models'
os.environ['CVG_PROJECT_ROOT']=r'D:\CVG Project'
import json,zipfile,tempfile,io
from pathlib import Path
import numpy as np,pandas as pd,torch,wfdb,joblib
from sklearn.metrics import roc_auc_score,average_precision_score
from fastapi.testclient import TestClient
from app.backend.main import app,ecg_encoder,mimic_adapter,diagnostic_assets
from ml_pipeline.ecg_branch import load_ecg
from ml_pipeline.signal_quality import preprocess_mimic
from ml_pipeline.research_heads import predict_rhythm
from ml_pipeline.mimic_adapter_inference import apply_adapter_calibration

torch.set_num_threads(2)
root=Path(r'D:\CVG Project');models=root/'models';result={};client=TestClient(app)
frame=pd.read_csv(root/'artifacts/ecgfounder_ext_icd_prepared_24k/manifest.csv');cache=np.load(root/'artifacts/ecgfounder_ext_icd_features_24k/ecgfounder_features.npy',mmap_mode='r');selected=np.concatenate([np.random.default_rng(417).choice(np.flatnonzero(frame.split==split),4,replace=False) for split in ('train','val','test')]);parity=[]
with zipfile.ZipFile(root/'mimic-iv-ecg-diagnostic-electrocardiogram-matched-subset-1.0.zip') as z:
    lookup={name.split('/files/',1)[-1]:name for name in z.namelist() if '/files/' in name}
    for ix in selected:
        row=frame.iloc[ix]
        with tempfile.TemporaryDirectory() as td:
            for ext in ('.hea','.dat'):
                key=row.record.removeprefix('files/')+ext
                Path(td,str(row.study_id)+ext).write_bytes(z.read(lookup[key]))
            try:w=load_ecg(Path(td,str(row.study_id)+'.hea'),processor=preprocess_mimic)
            except ValueError as error:
                result.setdefault('rejected_sampled_records',[]).append({'split':row.split,'reason':str(error)})
                print('sample quality rejection',str(error),flush=True)
                continue
            with torch.inference_mode():_,features=ecg_encoder()(torch.from_numpy(w[None]))
            error=float(abs(features.numpy()[0]-cache[ix]).max());assert error<1e-4,(row.study_id,error)
            parity.append({'split':row.split,'maximum_absolute_difference':error})
            if len(parity)==1:
                v={'age':55,'sex':'male','creatinine':1.0,'glucose':100}
                with open(Path(td,str(row.study_id)+'.hea'),'rb') as h,open(Path(td,str(row.study_id)+'.dat'),'rb') as d:
                    response=client.post('/api/predict',data={'clinical_json':json.dumps(v)},files={'ecg':(str(row.study_id)+'.dat',d),'header':(str(row.study_id)+'.hea',h)})
                assert response.status_code==200,response.text
                body=response.json();assert body['diagnostic_modality']=='ecg_clinical'
                _,transform,_,_=diagnostic_assets();m,cal=mimic_adapter();tab=transform.transform([{'age':55,'sex':'male','creatinine':1.0,'fasting_blood_sugar':100}])
                with torch.inference_mode():logits,_=m(torch.from_numpy(np.asarray(cache[ix:ix+1]).copy()),torch.from_numpy(tab),torch.ones(1,1),torch.ones(1,1))
                expected=apply_adapter_calibration(logits.numpy(),cal['modalities']['ecg_clinical'])[0]
                actual=np.array(list(body['disease_probabilities'].values()));assert abs(actual-expected).max()<1e-4
                result['cached_vs_upload_probability_max_error']=float(abs(actual-expected).max())
        print('parity',len(parity),error,flush=True)
result['mimic_embedding_parity']=parity
for path in ('app/frontend/public/demo_files/sample_ecg_mi_500hz.csv','app/frontend/public/demo_files/sample_ecg_normal_500hz.csv','app/frontend/public/demo_files/sample_ecg_af_500hz.csv','client_test_kit/sample_1lead_smartwatch.csv','client_test_kit/sample_6lead_kardia.csv','app/frontend/public/demo_files/sample_scanned_ecg_3x4.png'):
    with open(path,'rb') as f:resp=client.post('/api/predict',data={'clinical_json':json.dumps({'age':55,'sex':'male','creatinine':1.0,'glucose':100}),'sample_rate':'500'},files={'ecg':(Path(path).name,f)})
    assert resp.status_code==200,resp.text
    d=resp.json();result[Path(path).name]={'status':200,'mode':d['diagnostic_modality'],'rhythm':d['rhythm_assessment'],'quality':d['input_quality']}
    if path.endswith('.png') or 'smartwatch' in path or 'kardia' in path:assert d['rhythm_assessment'] is None and d['diagnostic_modality']=='clinical_only'
for kind,signal in [('flat',np.zeros((5000,12))),('short',np.random.default_rng(1).normal(size=(500,12))),('gain',np.ones((5000,12))*1000),('noise',np.random.default_rng(2).normal(size=(5000,12)))]:
    b=io.BytesIO();np.save(b,signal);resp=client.post('/api/predict',data={'sample_rate':'500'},files={'ecg':('bad.npy',b.getvalue())});assert resp.status_code==422,(kind,resp.text);result['reject_'+kind]=422
rhythm=joblib.load(models/'af_rhythm_head.joblib');c=np.load(models/'ptbxl_cached_embeddings.npz');db=pd.read_csv(root/'ptb-xl-1.0.1/ptbxl_database.csv');codes=db.scp_codes.map(__import__('ast').literal_eval);st=pd.read_csv(root/'ptb-xl-1.0.1/scp_statements.csv',index_col=0);rc=set(st.index[st.rhythm==1]);valid=codes.map(lambda d:bool(set(d)&rc)).to_numpy();ix=np.flatnonzero(valid&(db.strat_fold.to_numpy()==10));y=codes.map(lambda d:int('AFIB' in d)).to_numpy()[ix];p=predict_rhythm(rhythm,c['embeddings'][ix]);groups=db.patient_id.to_numpy()[ix];unique=np.unique(groups);indices={g:np.flatnonzero(groups==g) for g in unique};rng=np.random.default_rng(219);aucs=[];aps=[]
for _ in range(200):
    rows=np.concatenate([indices[g] for g in rng.choice(unique,len(unique),replace=True)])
    if len(np.unique(y[rows]))==2:aucs.append(roc_auc_score(y[rows],p[rows]));aps.append(average_precision_score(y[rows],p[rows]))
result['rhythm_patient_bootstrap_95ci']={'auroc':np.percentile(aucs,[2.5,97.5]).tolist(),'average_precision':np.percentile(aps,[2.5,97.5]).tolist(),'replicates':200}
result['rhythm_subgroups']={}
for label,mask in [('female',db.sex.to_numpy()[ix]==1),('male',db.sex.to_numpy()[ix]==0),('age_under65',db.age.to_numpy()[ix]<65),('age_65plus',db.age.to_numpy()[ix]>=65)]:
    result['rhythm_subgroups'][label]={'rows':int(mask.sum()),'positives':int(y[mask].sum()),'auroc':float(roc_auc_score(y[mask],p[mask])),'average_precision':float(average_precision_score(y[mask],p[mask]))}
Path('client_test_kit/prediction_upgrade_verification.json').write_text(json.dumps(result,indent=2))
print('ALL CHECKS PASSED',result['rhythm_patient_bootstrap_95ci'],flush=True)
