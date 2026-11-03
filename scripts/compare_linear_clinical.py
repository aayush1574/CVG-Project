"""Regularized expanded-lab linear baseline, compared on the same validation patients."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['MKL_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import ast,json
from pathlib import Path
import numpy as np,pandas as pd,torch
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from ml_pipeline.research_heads import clinical_matrix,apply_head_calibration
from scripts.train_research_upgrades import score,fit_rule,threshold,save

root=Path(r'D:\CVG Project');data=pd.read_csv(root/'artifacts/clinical-ext-icd-prepared-24k/manifest.csv');meta=json.loads((root/'artifacts/ecgfounder_ext_icd_prepared_24k/metadata.json').read_text());labels=['I48','I50','I25','I21','I44'];ids=[meta['labels'].index(v) for v in labels];y=np.asarray([[int(j in ast.literal_eval(v)) for j in ids] for v in data.targets]);records=[{'age':r.age,'sex':'female' if r.gender=='F' else 'male',**{k:getattr(r,k+'_last') for k in ('creatinine','glucose','potassium','sodium','hemoglobin','wbc')}} for r in data.itertuples()];x=clinical_matrix(records);train=np.flatnonzero(data.split=='train');val=np.flatnonzero(data.split=='val');test=np.flatnonzero(data.split=='test');fit,check=next(GroupShuffleSplit(n_splits=1,test_size=.5,random_state=119).split(val,groups=data.subject_id.to_numpy()[val]));fit=val[fit];check=val[check];best=None
for regularization in (.01,.1,1.):
 models=[];rules=[];cuts=[];validation={}
 for j,label in enumerate(labels):
  model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),LogisticRegression(C=regularization,max_iter=1500))
  model.fit(x[train],y[train,j]);rule=fit_rule(y[fit,j],model.predict_proba(x[fit])[:,1]);p=apply_head_calibration(model.predict_proba(x[check])[:,1],rule);cut=threshold(y[fit,j],apply_head_calibration(model.predict_proba(x[fit])[:,1],rule));models.append(model);rules.append(rule);cuts.append(cut);validation[label]=score(y[check,j],p,cut)
 result={'C':regularization,'models':models,'calibration':rules,'thresholds':cuts,'labels':labels,'validation':validation,'macro_ap':float(np.mean([v['average_precision'] for v in validation.values()])),'macro_auc':float(np.mean([v['auroc'] for v in validation.values()])),'macro_brier':float(np.mean([v['brier'] for v in validation.values()]))}
 print('linear C',regularization,'AP',result['macro_ap'],'AUROC',result['macro_auc'],flush=True)
 if best is None or result['macro_ap']>best['macro_ap']:best=result
metrics=json.loads((root/'models/research_upgrade_metrics.json').read_text());previous=metrics['expanded_clinical'];promote=best['macro_ap']>previous['baseline_validation_macro_ap'] and best['macro_auc']>previous['baseline_validation_macro_auroc']
testing={label:score(y[test,j],apply_head_calibration(best['models'][j].predict_proba(x[test])[:,1],best['calibration'][j]),best['thresholds'][j]) for j,label in enumerate(labels)}
out={'promoted':bool(promote),'selected_C':best['C'],'validation':best['validation'],'test':testing,'validation_macro_auc':best['macro_auc'],'validation_macro_ap':best['macro_ap'],'note':'Candidate selection on validation only; historical test has been inspected previously. No external validation.'};best['metrics']=out
save('expanded_clinical_head.joblib' if promote else 'expanded_linear_candidate.joblib',best);metrics['expanded_linear']=out;(root/'models/research_upgrade_metrics.json').write_text(json.dumps(metrics,indent=2));print('PROMOTED',promote,'test auc',np.mean([v['auroc'] for v in testing.values()]))
