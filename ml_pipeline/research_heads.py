"""Runtime helpers for versioned rhythm and expanded-lab research heads."""
import numpy as np
from scipy.special import expit,logit

CLINICAL_FIELDS=('age','sex_male','creatinine','glucose','potassium','sodium','hemoglobin','wbc')

def clinical_matrix(records):
    rows=[]
    for r in records:
        values={**r,'sex_male':1 if str(r.get('sex','')).lower()=='male' else 0 if str(r.get('sex','')).lower()=='female' else np.nan}
        if values.get('glucose') in (None,''):values['glucose']=values.get('fasting_blood_sugar')
        row=[]
        for key in CLINICAL_FIELDS:
            try:v=float(values.get(key,np.nan))
            except (ValueError,TypeError):v=np.nan
            row.append(v if np.isfinite(v) else np.nan)
        rows.append(row)
    return np.asarray(rows,np.float64)

def apply_head_calibration(p,rule):
    return expit(rule['slope']*logit(np.clip(p,1e-7,1-1e-7))+rule['intercept'])

def predict_clinical_head(bundle,records):
    x=clinical_matrix(records)
    return np.column_stack([apply_head_calibration(m.predict_proba(x)[:,1],rule)
                           for m,rule in zip(bundle['models'],bundle['calibration'])])

def predict_rhythm(bundle,embedding):
    x=bundle['scaler'].transform(embedding)
    p=bundle['model'].predict_proba(x)[:,1]
    return apply_head_calibration(p,bundle['calibration'])
