import React,{useState,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import './index.css';
import {apiFetch} from './api';
import DemoGuide from './DemoGuide';
import ScenarioPanel from './ScenarioPanel';
import ResearchInsights from './ResearchInsights';
import DiagnosticPanels from './DiagnosticPanels';
import HealthReport from './HealthReport';
import ClinicalRatios from './ClinicalRatios';
import EvidenceReport from './EvidenceReport';
import PrintSummary from './PrintSummary';
import {samples,type SampleKey} from './samples';
import type {ReportResult} from './reportFormat';

type Values=Record<string,string|number|boolean>;
type Result=ReportResult&{disease_probabilities:Record<string,number>;waveform:Record<string,number[]>|null};
const defaults:Values={age:52,sex:'female',systolic_bp:125,diastolic_bp:80,bmi:25,smoking_status:'never',packs_per_day:0,alcohol_intake:0,physical_activity_mins_per_week:150,diet_quality_score:5,sleep_hours:7,stress_level:5,family_history_cvd:'no',diabetes_status:'no'};
const fields:[string,string,string,number?,number?][]=[
  ['age','Age','number',18,100],['sex','Sex','select'],['bmi','BMI','number',10,70],['systolic_bp','Systolic blood pressure · mmHg','number',60,260],['diastolic_bp','Diastolic blood pressure · mmHg','number',30,160],
  ['resting_hr','Resting heart rate','number',30,220],['total_cholesterol','Total cholesterol · mg/dL','number',50,500],['hdl','HDL · mg/dL','number',10,200],['ldl','LDL · mg/dL','number',10,400],
  ['triglycerides','Triglycerides · mg/dL','number',10,1000],['glucose','Glucose · mg/dL','number',30,600],['fasting_blood_sugar','Fasting glucose · mg/dL','number',30,600],['hba1c','HbA1c · %','number',3,20],['creatinine','Creatinine · mg/dL','number',0,20],['egfr','eGFR','number',0,150],['troponin','Troponin · report units','number',0,10000],
  ['smoking_status','Smoking','select'],['packs_per_day','Packs per day','number',0,10],['alcohol_intake','Alcohol servings / week','number',0,100],['physical_activity_mins_per_week','Activity · min / week','number',0,1500],['diet_quality_score','Diet quality · 0–10','number',0,10],['sleep_hours','Sleep · hours','number',0,24],['stress_level','Stress · 0–10','number',0,10],
  ['family_history_cvd','Family history of CVD','select'],['diabetes_status','Diabetes','select'],['hypertension_meds','BP medication','select'],['statin_use','Statin use','select']
];
const options:Record<string,string[]>={sex:['female','male','other'],smoking_status:['never','former','current'],family_history_cvd:['no','yes'],diabetes_status:['no','yes'],hypertension_meds:['no','yes'],statin_use:['no','yes']};

function App(){
  const [tab,setTab]=useState<'upload'|'manual'>('upload');
  const [values,setValues]=useState<Values>(defaults);
  const [assessedValues,setAssessedValues]=useState<Values>(defaults);
  const [extractionEvidence,setExtractionEvidence]=useState<{field:string;value:number;canonical_unit?:string;source_text?:string|null;unit_status:string;reference_interval?:{low:number;high:number;unit?:string}|null}[]>([]);
  const [report,setReport]=useState<File|null>(null);
  const [ecg,setEcg]=useState<File|null>(null);
  const [header,setHeader]=useState<File|null>(null);
  const [rate,setRate]=useState('500');
  const [result,setResult]=useState<Result|null>(null);
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');

  const [engineReady,setEngineReady]=useState(false);
  useEffect(()=>{let active=true,running=false;const wake=async()=>{if(running)return;running=true;try{const r=await apiFetch('/api/health');if(active)setEngineReady(r.ok)}catch{if(active)setEngineReady(false)}finally{running=false}};void wake();const timer=setInterval(wake,15000);return()=>{active=false;clearInterval(timer)}},[]);
  function selectEcg(file:File|null){setEcg(file);setHeader(null);setResult(null);if(file&&/\.(csv|npy)$/i.test(file.name))setRate('500')}
  async function parse(file:File){
    setReport(file);setExtractionEvidence([]);setResult(null);setBusy(true);setNotice('');
    try{const form=new FormData();form.append('report',file);const response=await apiFetch('/api/parse-report',{method:'POST',body:form});const body=await response.json();if(!response.ok)throw Error(body.detail||'Report extraction failed');setValues(old=>({...old,...body.values}));setExtractionEvidence(body.provenance?.fields||[]);setNotice(`Extracted ${Object.keys(body.values).length} values from ${body.provenance?.source_filename||file.name}. Measurement dates and source accuracy are unverified. Review values and units before assessment.`)}
    catch(e){setNotice(String(e))}finally{setBusy(false)}
  }
  async function predict(next=values,ecgOverride=ecg,headerOverride=header,rateOverride=rate){
    setBusy(true);setNotice('');
    try{const form=new FormData();form.append('clinical_json',JSON.stringify(Object.fromEntries(Object.entries(next).filter(([,value])=>value!==''))));if(ecgOverride)form.append('ecg',ecgOverride);if(headerOverride)form.append('header',headerOverride);form.append('sample_rate',rateOverride||'500');const response=await apiFetch('/api/predict',{method:'POST',body:form});const body=await response.json();if(!response.ok)throw Error(body.detail||'Assessment failed');setAssessedValues({...next});setResult(body);return true}
    catch(e){setResult(null);setNotice(String(e));return false}finally{setBusy(false)}
  }
  async function loadSample(key:SampleKey){
    setBusy(true);setNotice('');
    try{const sample=samples[key];let next:Values={...sample.values};let labFile:File|null=null;let ecgFile:File|null=null;let headerFile:File|null=null;
      if(sample.lab){const response=await fetch(sample.lab);if(!response.ok)throw Error('Sample lab file unavailable');labFile=new File([await response.blob()],sample.lab.split('/').pop()||'labs.csv',{type:'text/csv'});const form=new FormData();form.append('report',labFile);const parsed=await apiFetch('/api/parse-report',{method:'POST',body:form});const body=await parsed.json();if(!parsed.ok)throw Error(body.detail||'Sample report parsing failed');next={...next,...body.values};}
      if(sample.ecg){const dat=await fetch(sample.ecg+'.dat');const hea=await fetch(sample.ecg+'.hea');if(!dat.ok||!hea.ok)throw Error('Sample ECG unavailable');const stem=sample.ecg.split('/').pop();ecgFile=new File([await dat.blob()],stem+'.dat');headerFile=new File([await hea.blob()],stem+'.hea');}
      if(sample.ecgCsv){const response=await fetch(sample.ecgCsv);if(!response.ok)throw Error('Sample ECG unavailable');ecgFile=new File([await response.blob()],sample.ecgCsv.split('/').pop()||'ecg.csv',{type:'text/csv'});setRate('500')}
      setValues(next);setReport(labFile);setEcg(ecgFile);setHeader(headerFile);setTab('upload');if(!await predict(next,ecgFile,headerFile,'500'))throw Error('Demo assessment failed. Please retry once the engine is ready.');
      setNotice(key==='high'?'Illustrative profile. The public PTB-XL ECG comes from a different de-identified person than the entered values.':'Real de-identified ECG paired with illustrative clinical values from a different person.');
    }catch(error){setNotice(String(error));setResult(null)}finally{setBusy(false)}
  }
  function field([key,label,type,min,max]:typeof fields[number]){
    const value=values[key]??'';
    return <label key={key} className="flex flex-col gap-1.5 text-sm font-medium"><span>{label}</span>{type==='select'?<select className="form-control" value={String(value)} onChange={e=>setValues({...values,[key]:e.target.value})}><option value="">Not provided</option>{options[key].map(option=><option key={option}>{option}</option>)}</select>:<input className="form-control" type="number" min={min} max={max} step="any" value={String(value)} onChange={e=>setValues({...values,[key]:e.target.value===''?'':Number(e.target.value)})}/>}</label>
  }
  return <div className="min-h-screen">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-5"><div><div className="text-2xl font-bold tracking-tight text-teal">◈ CardioScope</div><div className="text-xs uppercase tracking-[.14em] text-slate-500">Cardiovascular research report</div></div><span role="status" className={`rounded-full px-3 py-2 text-xs font-semibold ${engineReady?'bg-emerald-50 text-emerald-800':'bg-amber-50 text-amber-800'}`}>{engineReady?'AI Engine: Ready':'AI Engine: Warming up container...'}</span><label className="text-sm font-semibold text-ink">Try an example <select aria-label="Load sample patient" className="ml-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm" defaultValue="" onChange={e=>{if(e.target.value)void loadSample(e.target.value as SampleKey);e.target.value=''}}><option value="">Choose a profile</option>{Object.entries(samples).map(([key,item])=><option key={key} value={key}>{item.label}</option>)}</select></label></div></header>
    <main className="mx-auto max-w-7xl px-5 py-8 sm:px-6"><div className="mb-7"><p className="mb-1 text-sm font-semibold uppercase tracking-[.14em] text-teal">Research &amp; Educational Simulation Only</p><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">A clearer view of your cardiovascular research scores</h1><p className="mt-2 max-w-3xl text-slate-600">Enter health details or upload a report and ECG. Review condition model scores, the separate 10-year PREVENT estimate, and discussion points in one report.</p></div>
      <DemoGuide busy={busy} load={key=>void loadSample(key)}/>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]"><section className="report-card print:hidden"><h2 className="text-xl font-semibold">Information to assess</h2><div className="mt-4 flex gap-2 rounded-xl bg-paper p-1"><button className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold ${tab==='upload'?'bg-white text-teal shadow':''}`} onClick={()=>setTab('upload')}>Upload files</button><button className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold ${tab==='manual'?'bg-white text-teal shadow':''}`} onClick={()=>setTab('manual')}>Review or enter values</button></div>
        {tab==='upload'?<div className="mt-5 space-y-4"><div className="upload-box" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(e.dataTransfer.files[0])void parse(e.dataTransfer.files[0])}}><h3 className="font-semibold">Medical report</h3><p className="mt-1 text-sm text-slate-600">PDF, image, CSV, or JSON. Review extracted values before assessment.</p><input className="mt-3 max-w-full text-sm" type="file" accept=".pdf,.png,.jpg,.jpeg,.csv,.json" onChange={e=>e.target.files?.[0]&&void parse(e.target.files[0])}/>{report&&<p className="mt-2 break-all text-xs text-slate-600">Selected: {report.name}</p>}</div><div className="upload-box" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();selectEcg(e.dataTransfer.files[0]||null)}}><h3 className="font-semibold">ECG waveform <span className="font-normal text-slate-500">(optional)</span></h3><p className="mt-1 text-sm text-slate-600">12-lead CSV, NPY, WFDB DAT + HEA, or an experimental scanned ECG image.</p><input className="mt-3 max-w-full text-sm" type="file" accept=".csv,.npy,.dat,.hea,.png,.jpg,.jpeg" onChange={e=>selectEcg(e.target.files?.[0]||null)}/>{ecg&&<p className="mt-2 break-all text-xs text-slate-600">Selected: {ecg.name}</p>}<details className="mt-3 text-sm"><summary className="cursor-pointer font-medium">Waveform file options</summary><label className="mt-3 block">WFDB companion file<input className="mt-1 block max-w-full" type="file" accept=".dat,.hea" onChange={e=>setHeader(e.target.files?.[0]||null)}/></label><label className="mt-3 block">CSV / NPY sample rate (Hz)<input className="ml-2 w-24 rounded-lg border px-2 py-1" type="number" value={rate} onChange={e=>setRate(e.target.value)}/></label></details></div><button className="text-sm font-semibold text-teal underline" onClick={()=>setTab('manual')}>Review entered and extracted values</button></div>:<div className="mt-5 grid gap-4 sm:grid-cols-2">{fields.map(field)}</div>}
        {extractionEvidence.length>0&&<details className="mt-4 rounded-xl bg-paper p-3"><summary className="cursor-pointer text-sm font-semibold">Review extracted evidence and units</summary><p className="mt-2 text-xs text-slate-600">Confirm each value against the original report. Measurement dates are unverified.</p>{extractionEvidence.map(item=><div key={item.field} className="mt-3 border-b border-slate-200 pb-2 text-sm"><strong>{item.field.replace(/_/g,' ')}: {item.value} {item.canonical_unit||''}</strong><p className="text-xs text-slate-500">{item.source_text||'Structured value; source line unavailable'} · {item.unit_status}</p>{item.reference_interval&&<p className="text-xs">Report reference: {item.reference_interval.low}–{item.reference_interval.high} {item.reference_interval.unit}; separate from model thresholds.</p>}</div>)}</details>}
        <button disabled={busy} onClick={()=>void predict()} className="mt-6 w-full rounded-xl bg-teal px-5 py-3 font-semibold text-white hover:bg-teal/90">{busy?'Preparing report…':'Generate research report'}</button>{notice&&<p role="status" className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{notice}</p>}</section>
        <section id="clinical-summary" className="space-y-5"><PrintSummary values={assessedValues} result={result}/>{result?<><div className="flex items-center justify-between gap-3 print:hidden"><h2 className="text-xl font-semibold">Your research report</h2><button className="rounded-xl border border-teal px-4 py-2 text-sm font-semibold text-teal hover:bg-teal/5" onClick={()=>window.print()}>Print / save PDF</button></div><HealthReport result={result} values={assessedValues}/><EvidenceReport result={result}/><ClinicalRatios result={result}/><DiagnosticPanels result={result}/>{result.waveform&&<details open className="report-card print:hidden"><summary className="cursor-pointer font-semibold">View uploaded ECG waveform</summary><div className="mt-3 max-h-80 space-y-2 overflow-auto">{Object.entries(result.waveform).map(([lead,points])=><div className="flex items-center gap-3" key={lead}><span className="w-8 text-xs font-semibold">{lead}</span><svg viewBox="0 0 200 40" preserveAspectRatio="none" className="h-10 flex-1 rounded bg-paper"><polyline fill="none" stroke="#087e82" strokeWidth="1" points={points.map((v,i)=>`${i},${20-Math.max(-4,Math.min(4,v))*4}`).join(' ')}/></svg></div>)}</div></details>}<ResearchInsights result={result}/><ScenarioPanel values={assessedValues} result={result}/></>:<div className="report-card text-center"><div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-teal/10 text-2xl text-teal">◈</div><h2 className="mt-4 text-xl font-semibold">Your report will appear here</h2><p className="mt-2 text-sm text-slate-600">Choose an example or enter your details, then generate a research report. You can use health details alone; an ECG is optional.</p></div>}</section></div>
      <p className="mt-8 text-xs text-slate-500">Research &amp; Educational Simulation Only. This interface is not a medical device. Consult a qualified clinician for interpretation and care decisions.</p>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
