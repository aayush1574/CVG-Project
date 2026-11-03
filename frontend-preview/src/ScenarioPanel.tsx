import {apiFetch} from './api';
import {useState,useRef,useEffect} from 'react';

type Values = Record<string,string|number|boolean>;
type Result = {cvd_risk_score:number|null, disease_probabilities:Record<string,number>};
type Scenario = {delta_index_points:number;
  before_learned_cohort_10y_risk?:{percent:number}|null;
  after_learned_cohort_10y_risk?:{percent:number}|null;
  scenario_feature_deltas?:Record<string,{changed:boolean;composite_index_points:number|null;cohort_chd_percentage_points:number|null}>};
const controls = [
  ['systolic_bp','Systolic BP',90,200,'mmHg'],
  ['bmi','BMI',18,45,'kg/m²'],
  ['physical_activity_mins_per_week','Activity',0,600,'min/week'],
  ['sleep_hours','Sleep',3,12,'hours'],
  ['ldl','LDL',30,300,'mg/dL'],
] as const;

export default function ScenarioPanel({values,result}:{values:Values,result:Result|null}) {
  const [changes,setChanges]=useState<Values>({});
  const [scenario,setScenario]=useState<Scenario|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const request=useRef<AbortController|null>(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  function reset(){request.current?.abort();setChanges({});setScenario(null);setError('');setBusy(false);}
  async function run() {
    request.current?.abort();const controller=new AbortController();request.current=controller;
    setBusy(true);setError('');
    try {
      const response=await apiFetch('/api/simulate',{method:'POST',signal:controller.signal,headers:{'content-type':'application/json'},
        body:JSON.stringify({clinical:values,changes:Object.fromEntries(Object.entries(changes).filter(([,v])=>v!=='')),disease_probabilities:result?.disease_probabilities??null})});
      const body=await response.json();
      if(!response.ok)throw Error(body.detail||'Simulation failed');
      if(!controller.signal.aborted)setScenario(body);
    } catch(e) {if(!controller.signal.aborted)setError(String(e));} finally {if(request.current===controller)setBusy(false);}
  }
  return <details className="report-card">
    <summary className="cursor-pointer text-lg font-semibold">Explore a lifestyle scenario</summary>
    <p className="mt-2 text-sm text-slate-600">Change a value to see how the research index responds. This is a simulation, not a predicted treatment effect.</p>
    <div className="mt-4 grid gap-3 sm:grid-cols-2">
      <label className="text-sm">Smoking status<select disabled={busy} className="mt-1 w-full rounded-lg border p-2" value={String(changes.smoking_status??values.smoking_status??'')} onChange={e=>{setScenario(null);setChanges({...changes,smoking_status:e.target.value});}}><option value="">Not provided</option><option>never</option><option>former</option><option>current</option></select></label>
      {controls.map(([key,label,min,max,unit])=><label key={key} className="text-sm">{label} · {unit}<input className="mt-1 w-full rounded-lg border p-2" disabled={busy} type="number" min={min} max={max} step="any" value={String(changes[key]??values[key]??'')} onChange={e=>{setScenario(null);setChanges({...changes,[key]:e.target.value===''?'':Number(e.target.value)});}}/></label>)}
    </div>
    <button className="mt-4 rounded-lg bg-teal px-4 py-2 text-sm font-semibold text-white" disabled={busy||Object.keys(changes).length===0} onClick={run}>{busy?'Calculating…':'Simulate changes'}</button>
    <button type="button" className="btn btn-secondary ml-3 print:hidden" onClick={reset}>Reset scenario</button>
    {scenario&&<div role="status" className="mt-4 rounded-xl bg-paper p-3 text-sm"><p>Composite burden index change: <strong>{scenario.delta_index_points>0?'+':''}{scenario.delta_index_points.toFixed(2)} points</strong>.</p>{scenario.before_learned_cohort_10y_risk&&scenario.after_learned_cohort_10y_risk&&<p className="mt-1">Framingham CHD estimate: {scenario.before_learned_cohort_10y_risk.percent}% → {scenario.after_learned_cohort_10y_risk.percent}%.</p>}
      <p className="mt-2 text-xs text-slate-600">Changed inputs, assessed one at a time:</p><ul className="mt-1 space-y-1">{Object.entries(scenario.scenario_feature_deltas||{}).filter(([,item])=>item.changed).map(([key,item])=><li key={key}>{key.replace(/_/g,' ')}: {item.composite_index_points==null?'Unavailable':`${item.composite_index_points>0?'+':''}${item.composite_index_points.toFixed(2)} index points`}; {item.cohort_chd_percentage_points==null?'no cohort estimate':`${item.cohort_chd_percentage_points>0?'+':''}${item.cohort_chd_percentage_points.toFixed(2)} CHD percentage points`}</li>)}</ul><p className="mt-2 text-xs text-slate-600">The cohort did not measure LDL, activity, or sleep; changes to these inputs do not alter its estimate. Scenario deltas are associations in the models, not treatment effects.</p></div>}
    {error&&<p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
  </details>;
}
