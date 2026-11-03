"""Fit PTB probability scaling on fold 9 only; never select on fold 10."""
import os
os.environ['OMP_NUM_THREADS']='2'
os.environ['MKL_NUM_THREADS']='2'
os.environ['OPENBLAS_NUM_THREADS']='2'
import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,torch
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score,f1_score
from ml_pipeline.longitudinal_risk_head import ece

torch.set_num_threads(2)
root=Path(r'D:\CVG Project');models=root/'models'
c=np.load(models/'ptbxl_cached_embeddings.npz');ck=torch.load(models/'ptbxl_superclass_head.pt',map_location='cpu',weights_only=False)
head=torch.nn.Sequential(torch.nn.Linear(1026,256),torch.nn.SiLU(),torch.nn.Dropout(.2),torch.nn.Linear(256,5));head.load_state_dict(ck['state_dict']);head.eval()
def logits(ix):
 x=(c['embeddings'][ix]-ck['mean'])/ck['scale'];aux=np.column_stack(((np.nan_to_num(c['age'][ix],nan=ck['age_median'])-55)/20,np.nan_to_num(c['sex'][ix],nan=.5)))
 with torch.inference_mode():return torch.cat([head(b) for b in torch.from_numpy(np.column_stack((x,aux)).astype(np.float32)).split(512)]).numpy()
valid=c['label_valid']&c['processed_mask'];val=np.flatnonzero(valid&(c['strat_fold']==9));test=np.flatnonzero(valid&(c['strat_fold']==10))
patients=pd.read_csv(root/'ptb-xl-1.0.1/ptbxl_database.csv').set_index('ecg_id').loc[c['ecg_id'][val],'patient_id'].to_numpy()
fit,check=next(GroupShuffleSplit(n_splits=1,test_size=.5,random_state=518).split(val,groups=patients))
z=logits(val);y=c['labels_5class'][val];rules=[]
for j in range(5):
 lr=LogisticRegression(C=10).fit(z[fit,j,None],y[fit,j]);slope=float(lr.coef_[0,0]);intercept=float(lr.intercept_[0]);raw=expit(z[check,j]);p=expit(slope*z[check,j]+intercept)
 keep=slope>0 and np.mean((p-y[check,j])**2)<np.mean((raw-y[check,j])**2) and ece(y[check,j],p)<ece(y[check,j],raw)
 rules.append({'method':'sigmoid' if keep else 'none','slope':slope if keep else 1.0,'intercept':intercept if keep else 0.0})
zt=logits(test);yt=c['labels_5class'][test];raw=expit(zt);p=np.column_stack([expit(r['slope']*zt[:,j]+r['intercept']) for j,r in enumerate(rules)])
def metrics(p):return {'macro_auroc':float(np.mean([roc_auc_score(yt[:,j],p[:,j]) for j in range(5)])),'macro_brier':float(np.mean((yt-p)**2)),'macro_ece':float(np.mean([ece(yt[:,j],p[:,j]) for j in range(5)])),'macro_f1_at_0_5':float(f1_score(yt,p>=.5,average='macro'))}
result={'checkpoint_sha256':hashlib.sha256((models/'ptbxl_superclass_head.pt').read_bytes()).hexdigest(),'labels':list(ck['labels']),'rules':rules,'fit_rows':len(fit),'assessment_rows':len(check),'test_rows':len(test),'test_raw':metrics(raw),'test_calibrated':metrics(p),'test_f1_at_mapped_thresholds':float(f1_score(yt,p>=np.asarray([expit(r['intercept']) for r in rules]),average='macro')),'selection':'patient-separated halves of fold 9; positive-slope sigmoid retained only when assessment Brier and ECE both improve'}
(models/'ptbxl_probability_calibration.json').write_text(json.dumps(result,indent=2))
m=json.loads((models/'research_metrics.json').read_text());m['ptbxl_probability_calibration']=result;(models/'research_metrics.json').write_text(json.dumps(m,indent=2))
print(json.dumps(result,indent=2))
