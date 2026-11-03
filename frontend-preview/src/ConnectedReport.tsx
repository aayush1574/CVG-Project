import HealthReport from './HealthReport';
import EvidenceReport from './EvidenceReport';
import ClinicalRatios from './ClinicalRatios';
import DiagnosticPanels from './DiagnosticPanels';
import ResearchInsights from './ResearchInsights';
import ScenarioPanel from './ScenarioPanel';
import PrintSummary from './PrintSummary';
import {WaveformExplorer} from './ReportView';
import type {ReportResult} from './reportFormat';
export type Result=ReportResult & {disease_probabilities:Record<string,number>;waveform:Record<string,number[]>|null;waveform_metadata?:{sample_rate_hz:number;amplitude_units:string}|null};
export type Assessment={values:Record<string,string>;result:Result;waveform:Record<string,number[]>|null;sampleRate:number;fileName:string;sample:boolean;extraction:import('./Inputs').Extraction[]};
export default function ConnectedReport({assessment,onEdit}:{assessment:Assessment;onEdit:()=>void}){
 const {result,values}=assessment;
 const wave=assessment.waveform??(result.waveform?Object.fromEntries(Object.entries(result.waveform).filter(([lead])=>result.lead_mode?.active_leads.includes(lead))):null);
 return <div className="connected-report space-y-5"><div className="flex flex-wrap gap-3 print:hidden"><button className="btn btn-secondary" onClick={onEdit}>Edit inputs</button><button className="btn btn-primary" onClick={()=>window.print()}>Print / save PDF</button></div>
 <p>{assessment.sample?'Synthetic demonstration · ':''}Assessed recording: {assessment.fileName||'No ECG · clinical only'}</p>
 {assessment.extraction.length>0&&<details className="report-card"><summary>Report extraction evidence</summary><p>Source accuracy and dates require review. Edited inputs may differ from the extracted source.</p>{assessment.extraction.map((item,i)=><p key={i}>{item.field}: {item.source_text??'Source text unavailable'} · {item.original_unit??'Unit unverified'} → {item.canonical_unit??'Review units'} {item.unit_status} {item.conversion_factor!=null?`Conversion factor: ${item.conversion_factor}`:''} {item.reference_interval?`Reference interval: ${item.reference_interval.low}–${item.reference_interval.high} ${item.reference_interval.unit??''}`:''}</p>)}</details>}
 <PrintSummary values={values} result={result}/><HealthReport values={values} result={result}/><EvidenceReport result={result}/><ClinicalRatios result={result}/><DiagnosticPanels result={result}/>
 <WaveformExplorer waveform={wave} sampleRate={assessment.waveform?assessment.sampleRate:result.waveform_metadata?.sample_rate_hz??20} processed={!assessment.waveform}/>
 <ResearchInsights result={result}/><ScenarioPanel values={values} result={result}/>
 </div>;
}
