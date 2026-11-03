"""Serving safeguards and checkpoint-bound PTB probability calibration."""
import hashlib,json,math
from functools import lru_cache
from pathlib import Path
import numpy as np

@lru_cache(maxsize=4)
def _load(path:str,modified:int,checkpoint_modified:int):
    p=Path(path);checkpoint=p.parent/'ptbxl_superclass_head.pt'
    if not p.is_file():return None
    data=json.loads(p.read_text())
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=data['checkpoint_sha256']:
        return None
    return data

def calibrate_ptb(logits,models):
    path=models/'ptbxl_probability_calibration.json';ck=models/'ptbxl_superclass_head.pt'
    bundle=_load(str(path),path.stat().st_mtime_ns if path.is_file() else 0,ck.stat().st_mtime_ns)
    if bundle is None:return 1/(1+np.exp(-np.clip(logits,-50,50))),None
    p=np.asarray([1/(1+np.exp(-np.clip(rule['slope']*logits[j]+rule['intercept'],-50,50))) for j,rule in enumerate(bundle['rules'])])
    cutoffs=[float(1/(1+np.exp(-r['intercept']))) for r in bundle['rules']]
    return p,{'method':'validation-fitted sigmoid','thresholds':dict(zip(bundle['labels'],cutoffs)),
              'note':'Calibration applies to standard digital 12-lead inputs only; mapped thresholds preserve the original decisions.'}

def validate_clinical(clinical):
    from .clinical_lifestyle_branch import NUMERIC
    for key in NUMERIC+('glucose','potassium','sodium','hemoglobin','wbc'):
        if key not in clinical or clinical[key] in (None,''):continue
        try:value=float(clinical[key])
        except (TypeError,ValueError):raise ValueError(f'{key} must be numeric')
        if not math.isfinite(value):raise ValueError(f'{key} must be finite')
        if value<0:raise ValueError(f'{key} cannot be negative')
        clinical[key]=value
    if clinical.get('age') not in (None,'') and not 18<=float(clinical['age'])<=100:
        raise ValueError('This adult research interface supports ages 18–100')
    if clinical.get('systolic_bp') and clinical.get('diastolic_bp') and clinical['diastolic_bp']>=clinical['systolic_bp']:
        raise ValueError('Diastolic pressure must be lower than systolic pressure')
    return clinical
