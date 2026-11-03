"""Local API regression checks; does not fit or modify models."""
import io,json,os
from pathlib import Path
import numpy as np,requests
BASE=os.environ.get('CVG_TEST_URL','http://127.0.0.1:8000')
ROOT=Path(__file__).resolve().parents[1]
values={'age':55,'sex':'male','creatinine':1.0,'glucose':100,'systolic_bp':130,'diastolic_bp':80,'total_cholesterol':210,'hdl':45}
checks=[]
def predict(name,files=None):
    r=requests.post(BASE+'/api/predict',data={'clinical_json':json.dumps(values),'sample_rate':'500'},files=files,timeout=120)
    assert r.status_code==200,(name,r.status_code,r.text[:300])
    d=r.json();assert d['clinical_icd_conditions']['I21']['flag'] is None
    assert d['clinical_icd_conditions']['I44']['flag'] is None
    checks.append(name);print(name,'passed',flush=True);return d
predict('clinical-only')
for label,path in [('mi','app/frontend/public/demo_files/sample_ecg_mi_500hz.csv'),('normal','app/frontend/public/demo_files/sample_ecg_normal_500hz.csv'),('af','app/frontend/public/demo_files/sample_ecg_af_500hz.csv'),('one','client_test_kit/sample_1lead_smartwatch.csv'),('six','client_test_kit/sample_6lead_kardia.csv'),('scan','app/frontend/public/demo_files/sample_scanned_ecg_3x4.png')]:
    p=ROOT/path
    d=predict(label,{'ecg':(p.name,p.read_bytes())})
    assert d['diagnostic_modality']==('ecg_clinical' if label in ('mi','normal','af') else 'clinical_only')
    assert bool(d['rhythm_assessment'])==(label in ('mi','normal','af'))
p=ROOT/'app/frontend/public/samples/00063_hr'
predict('WFDB',{'ecg':('00063_hr.dat',p.with_suffix('.dat').read_bytes()),'header':('00063_hr.hea',p.with_suffix('.hea').read_bytes())})
array=np.genfromtxt(ROOT/'app/frontend/public/demo_files/sample_ecg_normal_500hz.csv',delimiter=',',skip_header=1)
buf=io.BytesIO();np.save(buf,array);predict('NPY',{'ecg':('normal.npy',buf.getvalue())})
for name in ['sample_lipid_hba1c_report.pdf','sample_lab_report.png']:
    p=ROOT/'app/frontend/public/demo_files'/name
    r=requests.post(BASE+'/api/parse-report',files={'report':(name,p.read_bytes())},timeout=120);assert r.status_code==200,r.text
    expected=json.loads((p.parent/'manifest.json').read_text())['report_expected_values']
    assert all(r.json()['values'][k]==v for k,v in expected.items());assert r.json()['provenance']['fields'];checks.append(name)
for name,x in [('flat',np.zeros((5000,12))),('short',array[:100]),('nonfinite',np.full((5000,12),np.nan))]:
    buf=io.BytesIO();np.save(buf,x)
    r=requests.post(BASE+'/api/predict',data={'sample_rate':'500'},files={'ecg':('invalid.npy',buf.getvalue())},timeout=60);assert r.status_code==422,(name,r.text);checks.append('reject '+name)
r=requests.post(BASE+'/api/simulate',json={'clinical':values,'changes':{'systolic_bp':120}},timeout=60);assert r.status_code==200 and 'delta_index_points' in r.json();checks.append('simulation')
print(json.dumps({'passed':checks},indent=2))
