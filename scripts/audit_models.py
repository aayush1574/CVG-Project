import os
os.environ['OMP_NUM_THREADS']='2'
os.environ['MKL_NUM_THREADS']='2'
os.environ['OPENBLAS_NUM_THREADS']='2'
os.environ['CVG_PROJECT_ROOT']=r'D:\CVG Project'
os.environ['CVG_MODELS_DIR']=r'D:\CVG Project\models'
import ast,json
from pathlib import Path
import numpy as np,pandas as pd,torch,joblib
from sklearn.metrics import roc_auc_score,average_precision_score,f1_score,precision_score,recall_score
from app.backend.main import diagnostic_assets,mimic_adapter,ptb_head
from ml_pipeline.mimic_adapter_inference import apply_adapter_calibration
from ml_pipeline.longitudinal_risk_head import ece
torch.set_num_threads(2)
root=Path(r'D:\CVG Project');output={}
def metrics(y,p,labels,cut=.5):
 rows={}
 for j,label in enumerate(labels):
  t=y[:,j];q=p[:,j];d=q>=(cut[j] if np.ndim(cut) else cut)
  rows[label]={'positives':int(t.sum()),'prevalence':float(t.mean()),'auroc':float(roc_auc_score(t,q)),'average_precision':float(average_precision_score(t,q)),'f1':float(f1_score(t,d,zero_division=0)),'precision':float(precision_score(t,d,zero_division=0)),'recall':float(recall_score(t,d,zero_division=0)),'brier':float(np.mean((t-q)**2)),'ece_10bins':ece(t,q)}
 return {'rows':len(y),'macro_auroc':float(np.mean([r['auroc'] for r in rows.values()])),'macro_f1':float(np.mean([r['f1'] for r in rows.values()])),'macro_average_precision':float(np.mean([r['average_precision'] for r in rows.values()])),'per_class':rows}
checkpoint,transform,base,_=diagnostic_assets();model,calibration=mimic_adapter()
c=pd.read_csv(root/'artifacts/clinical-ext-icd-prepared-24k/manifest.csv');meta=json.loads((root/'artifacts/ecgfounder_ext_icd_prepared_24k/metadata.json').read_text());indices=[meta['labels'].index(k) for k in checkpoint['labels']]
y=np.asarray([[float(j in ast.literal_eval(v)) for j in indices] for v in c.targets],np.float32)
records=[{'age':r.age,'sex':'female' if r.gender=='F' else 'male','creatinine':r.creatinine_last,'fasting_blood_sugar':r.glucose_last} for r in c.itertuples()]
tab=transform.transform(records);emb=np.load(root/'artifacts/ecgfounder_ext_icd_features_24k/ecgfounder_features.npy',mmap_mode='r');test=np.flatnonzero(c.split.to_numpy()=='test')
for mode,maskvalue in [('ecg_clinical',1),('clinical_only',0)]:
 outputs=[]
 with torch.inference_mode():
  for batch in np.array_split(test,4):
   mask=torch.full((len(batch),1),float(maskvalue));logits,_=model(torch.from_numpy(np.asarray(emb[batch]).copy())*mask,torch.from_numpy(tab[batch]),mask,torch.ones_like(mask));outputs.append(logits.numpy())
 prob=apply_adapter_calibration(np.concatenate(outputs),calibration['modalities'][mode]);output[mode]=metrics(y[test],prob,checkpoint['labels'],np.asarray(calibration['thresholds'][mode]));output[mode]['macro_f1_at_0_5']=float(f1_score(y[test],prob>=.5,average='macro',zero_division=0));print(mode,output[mode]['macro_auroc'],output[mode]['macro_f1'],flush=True)
data=np.load(root/'models/ptbxl_cached_embeddings.npz');pc,head=ptb_head();ix=np.flatnonzero(data['label_valid']&data['processed_mask']&(data['strat_fold']==10));v=(data['embeddings'][ix]-pc['mean'])/pc['scale'];aux=np.column_stack(((np.nan_to_num(data['age'][ix],nan=pc['age_median'])-55)/20,np.nan_to_num(data['sex'][ix],nan=.5)));x=torch.from_numpy(np.column_stack((v,aux)).astype(np.float32))
with torch.inference_mode():p=torch.cat([head(b).sigmoid() for b in x.split(512)]).numpy()
output['ptbxl']=metrics(data['labels_5class'][ix],p,pc['labels']);output['ptbxl']['cache_finite']=bool(np.isfinite(data['embeddings']).all());output['ptbxl']['excluded_unlabeled_records']=int((~data['label_valid']).sum());output['ptbxl']['age_over_100']=int((data['age']>100).sum());print('ptbxl',output['ptbxl']['macro_auroc'],output['ptbxl']['macro_f1'])
Path('client_test_kit/model_audit.json').write_text(json.dumps(output,indent=2))
for mode,d in output.items():
 print(mode,[(k,round(v['average_precision'],3),round(v['precision'],3),round(v['recall'],3),round(v['f1'],3)) for k,v in d['per_class'].items()])
