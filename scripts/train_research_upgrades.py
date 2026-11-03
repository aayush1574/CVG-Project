"""Two-thread experiments; validation controls promotion, test is reporting only."""
import os
os.environ['OMP_NUM_THREADS']='2';os.environ['MKL_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
import ast,json,hashlib
from pathlib import Path
import joblib,numpy as np,pandas as pd
from scipy.special import logit,expit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score,average_precision_score,precision_recall_curve,precision_score,recall_score,f1_score
from ml_pipeline.research_heads import clinical_matrix,apply_head_calibration
from ml_pipeline.longitudinal_risk_head import ece

ROOT=Path(r'D:\CVG Project');MODELS=ROOT/'models'
try:
 import ctypes
 k=ctypes.windll.kernel32;k.GetCurrentProcess.restype=ctypes.c_void_p;k.SetPriorityClass.argtypes=(ctypes.c_void_p,ctypes.c_uint32);k.SetPriorityClass(k.GetCurrentProcess(),0x4000)
except (AttributeError,OSError):pass

def score(y,p,t=.5):
    return {'auroc':float(roc_auc_score(y,p)),'average_precision':float(average_precision_score(y,p)),
            'brier':float(np.mean((y-p)**2)),'ece':ece(y,p),'precision':float(precision_score(y,p>=t,zero_division=0)),
            'recall':float(recall_score(y,p>=t,zero_division=0)),'f1':float(f1_score(y,p>=t,zero_division=0)),
            'rows':len(y),'positives':int(y.sum())}

def fit_rule(y,p):
    lr=LogisticRegression(C=1).fit(logit(np.clip(p,1e-7,1-1e-7)).reshape(-1,1),y)
    return {'slope':float(lr.coef_[0,0]),'intercept':float(lr.intercept_[0])}

def threshold(y,p):
    pr,re,cut=precision_recall_curve(y,p);f=2*pr[:-1]*re[:-1]/np.maximum(pr[:-1]+re[:-1],1e-10)
    return float(cut[np.argmax(f)])

def save(name,bundle):
    path=MODELS/name;temp=path.with_suffix('.tmp.joblib');joblib.dump(bundle,temp);os.replace(temp,path)

def clinical():
    import torch
    torch.set_num_threads(2)
    from app.backend.main import diagnostic_assets,mimic_adapter
    from ml_pipeline.mimic_adapter_inference import apply_adapter_calibration
    data=pd.read_csv(ROOT/'artifacts/clinical-ext-icd-prepared-24k/manifest.csv')
    meta=json.loads((ROOT/'artifacts/ecgfounder_ext_icd_prepared_24k/metadata.json').read_text());labels=['I48','I50','I25','I21','I44'];ids=[meta['labels'].index(l) for l in labels]
    y=np.asarray([[int(i in ast.literal_eval(v)) for i in ids] for v in data.targets])
    records=[{'age':r.age,'sex':'female' if r.gender=='F' else 'male',**{key:getattr(r,source) for key,source in [('creatinine','creatinine_last'),('glucose','glucose_last'),('potassium','potassium_last'),('sodium','sodium_last'),('hemoglobin','hemoglobin_last'),('wbc','wbc_last')]}} for r in data.itertuples()]
    x=clinical_matrix(records);train=np.flatnonzero(data.split=='train');val=np.flatnonzero(data.split=='val');test=np.flatnonzero(data.split=='test')
    fit,check=next(GroupShuffleSplit(n_splits=1,test_size=.5,random_state=119).split(val,groups=data.subject_id.to_numpy()[val]));fit=val[fit];check=val[check]
    models=[];rules=[];cuts=[];validation={};testing={}
    ck,transform,_,_=diagnostic_assets();base,cal=mimic_adapter();old_records=[{'age':r['age'],'sex':r['sex'],'creatinine':r['creatinine'],'fasting_blood_sugar':r['glucose']} for r in records];tab=transform.transform(old_records)
    def baseline(ix):
        with torch.inference_mode():
            z,_=base(torch.zeros(len(ix),1024),torch.from_numpy(tab[ix]),torch.zeros(len(ix),1),torch.ones(len(ix),1))
        return apply_adapter_calibration(z.numpy(),cal['modalities']['clinical_only'])
    base_p=baseline(check);old=[]
    for j,label in enumerate(labels):
        model=HistGradientBoostingClassifier(max_iter=160,max_leaf_nodes=15,learning_rate=.04,l2_regularization=10,early_stopping=False,random_state=81+j).fit(x[train],y[train,j])
        rule=fit_rule(y[fit,j],model.predict_proba(x[fit])[:,1]);p=apply_head_calibration(model.predict_proba(x[check])[:,1],rule)
        if rule['slope']<=0:rule={'slope':1.,'intercept':0.};p=model.predict_proba(x[check])[:,1]
        cut=threshold(y[fit,j],apply_head_calibration(model.predict_proba(x[fit])[:,1],rule))
        models.append(model);rules.append(rule);cuts.append(cut);validation[label]=score(y[check,j],p,cut)
        old.append(score(y[check,j],base_p[:,j],cal['thresholds']['clinical_only'][j]));print('clinical',label,validation[label],flush=True)
    new_auc=np.mean([v['auroc'] for v in validation.values()]);old_auc=np.mean([v['auroc'] for v in old]);new_ap=np.mean([v['average_precision'] for v in validation.values()]);old_ap=np.mean([v['average_precision'] for v in old])
    promote=bool(new_auc>old_auc and new_ap>old_ap and np.mean([v['brier'] for v in validation.values()])<=np.mean([v['brier'] for v in old]))
    for j,label in enumerate(labels):testing[label]=score(y[test,j],apply_head_calibration(models[j].predict_proba(x[test])[:,1],rules[j]),cuts[j])
    result={'promoted':promote,'validation':validation,'test':testing,'baseline_validation_macro_auroc':float(old_auc),'candidate_validation_macro_auroc':float(new_auc),'baseline_validation_macro_ap':float(old_ap),'candidate_validation_macro_ap':float(new_ap),'source':'pre-ECG measured labs only; no insurance/race/admission-context predictors','test_use':'reporting after validation selection'}
    bundle={'models':models,'calibration':rules,'thresholds':cuts,'labels':labels,'metrics':result}
    save('expanded_clinical_head.joblib' if promote else 'expanded_clinical_candidate.joblib',bundle)
    return result

def rhythm():
    data=pd.read_csv(ROOT/'ptb-xl-1.0.1/ptbxl_database.csv');codes=data.scp_codes.map(ast.literal_eval);statements=pd.read_csv(ROOT/'ptb-xl-1.0.1/scp_statements.csv',index_col=0);rhythm_codes=set(statements.index[statements.rhythm==1]);valid=codes.map(lambda c:bool(set(c)&rhythm_codes)).to_numpy();y=codes.map(lambda c:int('AFIB' in c)).to_numpy()
    c=np.load(MODELS/'ptbxl_cached_embeddings.npz');assert np.array_equal(c['ecg_id'],data.ecg_id.to_numpy());x=c['embeddings'];fold=data.strat_fold.to_numpy();train=np.flatnonzero(valid&(fold<=8));val=np.flatnonzero(valid&(fold==9));test=np.flatnonzero(valid&(fold==10));fit,check=next(GroupShuffleSplit(n_splits=1,test_size=.5,random_state=221).split(val,groups=data.patient_id.to_numpy()[val]));fit=val[fit];check=val[check]
    scaler=StandardScaler().fit(x[train]);model=LogisticRegression(C=.01,max_iter=1000).fit(scaler.transform(x[train]),y[train]);rule=fit_rule(y[fit],model.predict_proba(scaler.transform(x[fit]))[:,1]);p=apply_head_calibration(model.predict_proba(scaler.transform(x[check]))[:,1],rule);cut=threshold(y[fit],apply_head_calibration(model.predict_proba(scaler.transform(x[fit]))[:,1],rule));v=score(y[check],p,cut)
    promote=bool(rule['slope']>0 and v['average_precision']>2*y[check].mean() and v['precision']>=.5 and v['recall']>=.5)
    tp=apply_head_calibration(model.predict_proba(scaler.transform(x[test]))[:,1],rule)
    result={'promoted':promote,'target':'AFIB rhythm annotation versus other annotated rhythms','validation':v,'test':score(y[test],tp,cut),'train_rows':len(train),'calibration_rows':len(fit),'threshold':cut,'scope':'standard digital 12-lead PTB preprocessing; no wearable or scan validation','external_validation':False}
    save('af_rhythm_head.joblib' if promote else 'af_rhythm_candidate.joblib',{'model':model,'scaler':scaler,'calibration':rule,'threshold':cut,'metrics':result})
    print('rhythm',result,flush=True);return result

if __name__=='__main__':
    result={'expanded_clinical':clinical(),'af_rhythm':rhythm()};(MODELS/'research_upgrade_metrics.json').write_text(json.dumps(result,indent=2))
