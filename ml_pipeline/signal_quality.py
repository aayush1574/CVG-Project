"""Conservative technical input gates, not clinical signal-quality certification."""
import numpy as np
from scipy.signal import welch

def assess_signal(signal, sample_rate, names):
    x=np.asarray(signal,dtype=np.float64)
    if x.ndim!=2 or not len(x) or not np.isfinite(x).all():
        raise ValueError('ECG must contain finite samples in named lead columns')
    if not 100<=sample_rate<=2000:
        raise ValueError('Supported ECG sample rates are 100–2000 Hz')
    duration=len(x)/sample_rate
    if duration<9.5:
        raise ValueError('At least 9.5 seconds of digital ECG is required; short strips are not padded into a full recording')
    if duration>300:
        raise ValueError('ECG exceeds the 300-second upload duration limit')
    if np.max(np.abs(x))>50:
        raise ValueError('ECG amplitude exceeds the supported millivolt range; check units and gain')
    spread=np.std(x,axis=0)
    active=spread>1e-5
    if not active.any():
        raise ValueError('ECG is flat or has insufficient signal variation')
    active_names=[str(name).upper() for name,good in zip(names,active) if good]
    allowed=[{'I'}, {'I','II','III','AVR','AVL','AVF'}, {'I','II','III','AVR','AVL','AVF','V1','V2','V3','V4','V5','V6'}]
    if set(active_names) not in allowed:
        raise ValueError('Missing or flat leads do not form a supported 1-, 6-, or 12-lead configuration')
    window=x[:int(10*sample_rate),active]
    f,p=welch(window,fs=sample_rate,nperseg=min(1024,len(window)),axis=0)
    total=p[(f>=.5)&(f<=min(100,sample_rate/2))].sum(axis=0)+1e-12
    high=p[(f>=45)&(f<=min(100,sample_rate/2))].sum(axis=0)/total
    if np.median(high)>.45:
        raise ValueError('ECG is dominated by high-frequency noise; upload a cleaner recording')
    repeated=(np.diff(window,axis=0)==0).mean(axis=0)
    warnings=[]
    if np.max(repeated)>.5:warnings.append('Many repeated samples; possible clipping, quantization, or interrupted signal')
    if np.median(high)>.25:warnings.append('Elevated high-frequency energy')
    if duration>10:warnings.append('Only the first 10 seconds are assessed')
    return {'duration_seconds':round(duration,3),'sample_rate_hz':int(sample_rate),
            'active_leads':active_names,'amplitude_units':'mV (declared by upload contract; not independently verified)',
            'status':'technical_checks_passed_with_warnings' if warnings else 'technical_checks_passed',
            'warnings':warnings,'certification':'Technical checks do not establish clinical signal quality or correct lead placement'}

def preprocess_mimic(signal,sample_rate,lead_names):
    """Match the frozen MIMIC embedding pipeline; PTB uses its own preprocessor."""
    from scipy.signal import iirnotch,butter,filtfilt,medfilt,resample_poly
    from math import gcd
    from .ecg_branch import LEADS
    assess_signal(signal,sample_rate,lead_names)
    names=[str(n).upper() for n in lead_names]
    if set(names)!={n.upper() for n in LEADS}:
        raise ValueError('MIMIC waveform fusion requires all twelve standard leads')
    x=np.asarray(signal,dtype=np.float64)[:,[names.index(n.upper()) for n in LEADS]].T
    if sample_rate!=500:
        divisor=gcd(sample_rate,500);x=resample_poly(x,500//divisor,sample_rate//divisor,axis=1)
    if x.shape[1]<5000:raise ValueError('Full 10-second recording required for MIMIC waveform fusion')
    x=x[:,:5000]
    b,a=iirnotch(50,30,500);x=filtfilt(b,a,x,axis=1)
    b,a=butter(4,[.67,40],btype='bandpass',fs=500);x=filtfilt(b,a,x,axis=1)
    x-=np.stack([medfilt(lead,201) for lead in x])
    return ((x-x.mean())/(x.std()+1e-8)).astype(np.float32)
