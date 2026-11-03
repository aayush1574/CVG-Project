import type {ReportResult} from './reportFormat';

const rows:[string,string,string][]=[
  ['pulse_pressure','Pulse pressure','mmHg'],
  ['mean_arterial_pressure','Mean arterial pressure','mmHg'],
  ['non_hdl_cholesterol','Non-HDL cholesterol','mg/dL'],
  ['tg_to_hdl_ratio','Triglycerides / HDL ratio',''],
  ['tyg_index','TyG index',''],
  ['egfr_ckd_epi_2021','Estimated kidney function (eGFR)','mL/min/1.73 m²'],
];

export default function ClinicalRatios({result}:{result:ReportResult|null}){
  const ratios=result?.engineered_clinical_ratios;
  return <section className="report-card"><h2 className="text-xl font-semibold">Calculated clinical values</h2><p className="report-help">Calculated directly from entered measurements when available. These are descriptive; most are not inputs to the current MIMIC condition classifier.</p><dl className="mt-4 grid gap-3 sm:grid-cols-2">{rows.map(([key,label,unit])=><div key={key} className="rounded-xl bg-paper p-3"><dt className="text-sm text-slate-600">{label}</dt><dd className="mt-1 font-semibold">{ratios?.[key]==null?'Needs source values':`${Number(ratios[key]).toFixed(key==='tyg_index'?2:1)}${unit?` ${unit}`:''}`}</dd></div>)}</dl></section>;
}
