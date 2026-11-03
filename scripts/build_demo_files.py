import ast, json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import wfdb, cv2
from PIL import Image, ImageDraw, ImageFont

out=Path('app/frontend/public/demo_files');out.mkdir(parents=True,exist_ok=True)
root=Path(r'D:\CVG Project\ptb-xl-1.0.1')
db=pd.read_csv(root/'ptbxl_database.csv')
codes=db.scp_codes.map(ast.literal_eval)
statements=pd.read_csv(root/'scp_statements.csv',index_col=0)
mi=set(statements.index[statements.diagnostic_class.eq('MI')])
chosen={
 'mi':db.loc[codes.map(lambda c:any(k in mi and v>=50 for k,v in c.items()))].iloc[0],
 'normal':db.loc[codes.map(lambda c:c.get('NORM',0)>=50 and 'SR' in c)].iloc[0],
 'af':db.loc[codes.map(lambda c:'AFIB' in c)].iloc[0],
}
leads=['I','II','III','aVR','aVL','aVF','V1','V2','V3','V4','V5','V6']
signals={}
for key,row in chosen.items():
 rec=wfdb.rdrecord(str(root/row.filename_hr));lookup={n.upper():i for i,n in enumerate(rec.sig_name)}
 signal=np.column_stack([rec.p_signal[:,lookup[n.upper()]] for n in leads]);signals[key]=signal
 pd.DataFrame(signal,columns=leads).to_csv(out/f'sample_ecg_{key}_500hz.csv',index=False,float_format='%.6f')
values={'total_cholesterol':240,'hdl':40,'ldl':155,'triglycerides':225,'fasting_blood_sugar':120,'hba1c':6.2,'creatinine':1.1,'systolic_bp':145,'diastolic_bp':90}
lines=['DEMO LABORATORY REPORT','Synthetic values for upload testing only','Total cholesterol: 240 mg/dL','HDL: 40 mg/dL','LDL: 155 mg/dL','Triglycerides: 225 mg/dL','Fasting blood sugar: 120 mg/dL','HbA1c: 6.2 %','Creatinine: 1.1 mg/dL','Systolic blood pressure: 145 mmHg','Diastolic blood pressure: 90 mmHg']
content='BT /F1 13 Tf\n'+'\n'.join(f'1 0 0 1 48 {780-i*43} Tm ({line}) Tj' for i,line in enumerate(lines))+'\nET'
objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',f'<< /Length {len(content)} >>\nstream\n{content}\nendstream'.encode()]
payload=b'%PDF-1.4\n';offsets=[0]
for i,obj in enumerate(objects,1):
 offsets.append(len(payload));payload+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
xref=len(payload);payload+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
payload+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
payload+=f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
(out/'sample_lipid_hba1c_report.pdf').write_bytes(payload)
im=Image.new('RGB',(1600,1300),'white');d=ImageDraw.Draw(im);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',38)
for i,line in enumerate(lines):d.text((65,55+i*105),line,font=font,fill=(10,20,30))
im.save(out/'sample_lab_report.png')
image=np.full((900,1600,3),255,np.uint8)
for x in range(0,1600,5):cv2.line(image,(x,0),(x,899),(220,210,250),1)
for y in range(0,900,5):cv2.line(image,(0,y),(1599,y),(220,210,250),1)
panels=[['I','aVR','V1','V4'],['II','aVL','V2','V5'],['III','aVF','V3','V6']]
for r,names in enumerate(panels):
 for c,name in enumerate(names):
  start=c*400+36;stop=(c+1)*400-20;mid=r*300+150
  segment=signals['normal'][:1400,leads.index(name)]
  ys=mid-np.interp(np.linspace(0,len(segment)-1,stop-start),np.arange(len(segment)),segment)*50
  pts=np.column_stack((np.arange(start,stop),np.clip(ys,r*300+40,(r+1)*300-40))).astype(np.int32)
  cv2.polylines(image,[pts],False,(0,0,0),2)
cv2.imwrite(str(out/'sample_scanned_ecg_3x4.png'),image)
manifest={'records':{key:int(row.ecg_id) for key,row in chosen.items()},'sample_rate':500,'report_expected_values':values,'notice':'Real de-identified ECGs paired with illustrative clinical values from a different person. Case labels describe source data, not guaranteed model predictions.'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
with zipfile.ZipFile(out/'cardioscope_demo_files.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in out.iterdir():
  if p.suffix in ('.csv','.png','.pdf','.json'):z.write(p,p.name)
print(json.dumps(manifest))
