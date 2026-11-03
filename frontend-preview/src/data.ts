export type Values = Record<string, string>;
export type Source = 'Entered' | 'Extracted' | 'Sample' | 'Corrected';
export type Field = { key: string; label: string; unit?: string; min?: number; max?: number; options?: string[]; help?: string };
export const groups: { name: string; description: string; fields: Field[] }[] = [
  {name:'Personal details',description:'A little context for your research report.',fields:[
    {key:'age',label:'Age',unit:'years',min:18,max:100},{key:'sex',label:'Sex',options:['female','male','other'],help:'The research equations use sex recorded at birth. Unsupported categories remain unavailable.'},
    {key:'bmi',label:'Body mass index',unit:'kg/m²',min:10,max:70,help:'BMI relates weight to height.'},
    {key:'family_history_cvd',label:'Family history of CVD',options:['no','yes']},{key:'diabetes_status',label:'Diabetes',options:['no','yes']},
    {key:'hypertension_meds',label:'Blood pressure medication',options:['no','yes']},{key:'statin_use',label:'Statin use',options:['no','yes']}]},
  {name:'Vital signs',description:'Use your most recent measurements.',fields:[
    {key:'systolic_bp',label:'Systolic blood pressure',unit:'mmHg',min:60,max:260,help:'The upper number in a blood pressure reading.'},
    {key:'diastolic_bp',label:'Diastolic blood pressure',unit:'mmHg',min:30,max:160,help:'The lower number in a blood pressure reading.'},
    {key:'resting_hr',label:'Resting heart rate',unit:'bpm',min:30,max:220}]},
  {name:'Laboratory results',description:'Enter values exactly as shown on your report.',fields:[
    {key:'total_cholesterol',label:'Total cholesterol',unit:'mg/dL',min:50,max:500},{key:'hdl',label:'HDL cholesterol',unit:'mg/dL',min:10,max:200},
    {key:'ldl',label:'LDL cholesterol',unit:'mg/dL',min:10,max:400},{key:'triglycerides',label:'Triglycerides',unit:'mg/dL',min:10,max:1000},
    {key:'glucose',label:'Glucose',unit:'mg/dL',min:30,max:600},{key:'fasting_blood_sugar',label:'Fasting glucose',unit:'mg/dL',min:30,max:600},
    {key:'hba1c',label:'HbA1c',unit:'%',min:3,max:20,help:'A measure of average blood sugar.'},{key:'creatinine',label:'Creatinine',unit:'mg/dL',min:0,max:20},
    {key:'egfr',label:'Estimated kidney function',unit:'mL/min/1.73m²',min:0,max:150},{key:'troponin',label:'Troponin',unit:'report units',min:0,max:10000}]},
  {name:'Lifestyle',description:'Leave anything you are unsure about blank.',fields:[
    {key:'smoking_status',label:'Smoking status',options:['never','former','current']},{key:'packs_per_day',label:'Cigarettes',unit:'packs/day',min:0,max:10},
    {key:'physical_activity_mins_per_week',label:'Physical activity',unit:'min/week',min:0,max:1500},{key:'sleep_hours',label:'Sleep',unit:'hours/night',min:0,max:24},
    {key:'alcohol_intake',label:'Alcohol',unit:'servings/week',min:0,max:100},{key:'diet_quality_score',label:'Diet quality',unit:'0–10',min:0,max:10},
    {key:'stress_level',label:'Stress level',unit:'0–10',min:0,max:10}]}];
export const fields = groups.flatMap(g=>g.fields);
export function fieldError(field:Field,value:string,values:Values):string {
  if(value === '' || value === undefined) return '';
  if(field.options) return field.options.includes(value) ? '' : 'Choose one of the listed options.';
  const n=Number(value);
  if(!Number.isFinite(n)) return 'Enter a valid number.';
  if(field.min!==undefined && n<field.min || field.max!==undefined && n>field.max) return `Enter a value from ${field.min} to ${field.max}.`;
  if(field.key==='diastolic_bp' && values.systolic_bp && n>=Number(values.systolic_bp)) return 'Must be lower than systolic pressure.';
  return '';
}
export const standardLeads=['I','II','III','aVR','aVL','aVF','V1','V2','V3','V4','V5','V6'];
function csvCells(line:string) { return line.split(',').map(v=>v.trim().replace(/^"|"$/g,'')); }
export function parseClinical(text:string,extension:string):Values {
  let record:Record<string,unknown>;
  if(extension==='json') { record=JSON.parse(text); if(!record || Array.isArray(record) || typeof record!=='object') throw Error('Use a JSON object with named clinical fields.'); }
  else { const rows=text.trim().split(/\r?\n/); if(rows.length!==2) throw Error('Use a CSV with a header and exactly one data row.'); const keys=csvCells(rows[0]); const vals=csvCells(rows[1]); if(keys.length!==vals.length) throw Error('CSV headers and values must have the same number of columns.'); record=Object.fromEntries(keys.map((k,i)=>[k,vals[i]])); }
  const output:Values={};
  for(const f of fields) if(record[f.key]!==undefined && record[f.key]!==null && record[f.key]!=='') { if(!['string','number','boolean'].includes(typeof record[f.key])) throw Error(`Check ${f.label}: expected a single value.`); output[f.key]=String(record[f.key]).toLowerCase(); }
  if(!Object.keys(output).length) throw Error('No recognized fields. Use names such as age, systolic_bp, hdl, or glucose.');
  return output;
}
export function parseWaveform(text:string):Record<string,number[]> {
  const rows=text.trim().split(/\r?\n/); const names=csvCells(rows.shift()||'');
  const leads=standardLeads.filter(l=>names.some(n=>n.toLowerCase()===l.toLowerCase()));
  if(![1,6,12].includes(leads.length) || (leads.length===1&&leads[0]!=='I') || (leads.length===6 && !standardLeads.slice(0,6).every(l=>leads.includes(l)))) throw Error('Use a CSV with lead I, all six limb leads, or all 12 standard leads.');
  if(rows.length<2) throw Error('The waveform needs at least two samples.');
  if(rows.length>100000) throw Error('Use a waveform CSV with 100,000 samples or fewer.');
  const result:Record<string,number[]>=Object.fromEntries(leads.map(l=>[l,[]]));
  for(const row of rows) { const cells=csvCells(row); for(const lead of leads) { const cell=cells[names.findIndex(n=>n.toLowerCase()===lead.toLowerCase())]; if(cell===undefined||cell===''||!Number.isFinite(Number(cell))) throw Error(`Check ${lead}: all waveform samples must be numeric.`); result[lead].push(Number(cell)); } }
  return result;
}
