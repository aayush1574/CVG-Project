"""Production smoke tests using public ECG samples and illustrative clinical data."""
import io,json
from pathlib import Path
import requests,numpy as np

base='https://cardioscope-research.pages.dev';v={'age':55,'sex':'male','creatinine':1.0,'glucose':100,'systolic_bp':130,'diastolic_bp':80,'total_cholesterol':210,'hdl':45};result={}
for label,name in [('mi','app/frontend/public/demo_files/sample_ecg_mi_500hz.csv'),('normal','app/frontend/public/demo_files/sample_ecg_normal_500hz.csv'),('af','app/frontend/public/demo_files/sample_ecg_af_500hz.csv'),('one_lead','client_test_kit/sample_1lead_smartwatch.csv'),('six_lead','client_test_kit/sample_6lead_kardia.csv'),('scan','app/frontend/public/demo_files/sample_scanned_ecg_3x4.png')]:
    p=Path(name)
    with p.open('rb') as f:r=requests.post(base+'/api/predict',data={'clinical_json':json.dumps(v),'sample_rate':'500'},files={'ecg':(p.name,f)},timeout=120)
    assert r.status_code==200,(label,r.status_code,r.text[:300]);d=r.json()
    expected='ecg_clinical' if label in ('mi','normal','af') else 'clinical_only'
    assert d['diagnostic_modality']==expected and d.get('evidence_report'),(label,d['diagnostic_modality'])
    assert bool(d['rhythm_assessment'])==(label in ('mi','normal','af'))
    assert d['clinical_icd_conditions']['I21']['flag'] is None
    result[label]={'status':200,'mode':d['diagnostic_modality'],'signal_status':(d.get('input_quality') or {}).get('status'),
                   'af_probability':d['rhythm_assessment']['probability'] if d['rhythm_assessment'] else None,
                   'evidence_sections':len(d['evidence_report']['summary'])}
    print(label,result[label],flush=True)
r=requests.post(base+'/api/predict',data={'clinical_json':json.dumps(v)},timeout=60);assert r.status_code==200 and r.json()['diagnostic_modality']=='clinical_only';result['clinical_only']=200
expected=json.loads(Path('app/frontend/public/demo_files/manifest.json').read_text())['report_expected_values']
for name in ('sample_lipid_hba1c_report.pdf','sample_lab_report.png'):
    p=Path('app/frontend/public/demo_files')/name
    with p.open('rb') as f:r=requests.post(base+'/api/parse-report',files={'report':(p.name,f)},timeout=120)
    assert r.status_code==200;rj=r.json();assert all(rj['values'][key]==value for key,value in expected.items());assert rj['provenance']['fields'][0]['source_text'];result[name]={'status':200,'exact_fields':9,'source_evidence':True};print(name,'passed',flush=True)
r=requests.post(base+'/api/simulate',json={'clinical':v,'changes':{'systolic_bp':120}},timeout=60);assert r.status_code==200;result['simulate']=200
b=io.BytesIO();np.save(b,np.zeros((5000,12)));r=requests.post(base+'/api/predict',data={'sample_rate':'500'},files={'ecg':('flat.npy',b.getvalue())},timeout=60);assert r.status_code==422;result['flat_rejection']=422
result['page']=requests.get(base,timeout=30).status_code;result['health']=requests.get(base+'/api/health',timeout=30).status_code
Path('client_test_kit/prediction_upgrade_live_results.json').write_text(json.dumps(result,indent=2))
print('ALL LIVE CHECKS PASSED',flush=True)
