import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Activity, ArrowRight, Check, ChevronDown, FileText, Info, Pencil, Printer, RotateCcw, SlidersHorizontal, Waves } from 'lucide-react';
import demoRecord from './demo-record.json';
import './report.css';

type ReportProps = {
  values: Record<string, string>;
  isSample: boolean;
  waveform: Record<string, number[]> | null;
  sampleRate: number;
  onEdit: () => void;
};

const inputNames: Record<string, string> = {
  age: 'Age', sex: 'Sex', bmi: 'Body mass index', systolic_bp: 'Systolic blood pressure',
  diastolic_bp: 'Diastolic blood pressure', resting_hr: 'Resting heart rate', total_cholesterol: 'Total cholesterol',
  hdl: 'HDL cholesterol', ldl: 'LDL cholesterol', triglycerides: 'Triglycerides', glucose: 'Glucose',
  fasting_blood_sugar: 'Fasting glucose', hba1c: 'HbA1c', creatinine: 'Creatinine', egfr: 'Estimated kidney function',
  troponin: 'Troponin', smoking_status: 'Smoking status', packs_per_day: 'Packs per day', alcohol_intake: 'Alcohol per week',
  physical_activity_mins_per_week: 'Activity minutes per week', diet_quality_score: 'Diet quality', sleep_hours: 'Sleep hours',
  stress_level: 'Stress level', family_history_cvd: 'Family history of CVD', diabetes_status: 'Diabetes status',
  hypertension_meds: 'Blood pressure medication', statin_use: 'Statin use',
};

const conditionRows = [
  { code: 'I48', label: 'Atrial fibrillation & flutter', description: 'Irregular heart rhythm diagnosis groups.' },
  { code: 'I50', label: 'Heart failure', description: 'Diagnosis group related to the heart’s pumping or filling function.' },
  { code: 'I25', label: 'Chronic ischemic heart disease', description: 'Diagnosis group associated with reduced blood flow to the heart.' },
  { code: 'I21', label: 'Acute myocardial infarction', description: 'Heart attack diagnosis group. Insufficient reliability for a decision.', abstain: true },
  { code: 'I44', label: 'Conduction block', description: 'Electrical conduction diagnosis groups. Insufficient reliability for a decision.', abstain: true },
];

const scenarioFields = [
  { key: 'systolic_bp', label: 'Systolic blood pressure', unit: 'mmHg', min: 60, max: 260, step: 1 },
  { key: 'physical_activity_mins_per_week', label: 'Weekly physical activity', unit: 'min / week', min: 0, max: 1500, step: 1 },
  { key: 'sleep_hours', label: 'Sleep per night', unit: 'hours', min: 0, max: 24, step: 0.1 },
];

function providedNumber(value: string | undefined) {
  return value !== undefined && value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
}

function ReportMetric({ title, value, unit, note, sample, primary = false }: { title: string; value: string; unit?: string; note: string; sample?: boolean; primary?: boolean }) {
  return <div className={`rpt-metric ${primary ? 'rpt-metric-primary' : ''}`}>
    <div className="rpt-metric-label">{title}</div>
    <div className={`rpt-metric-value ${value === 'Unavailable' ? 'rpt-unavailable' : ''}`}>{value}{unit && <span>{unit}</span>}</div>
    {sample && <span className="rpt-snapshot-label">Recorded synthetic sample</span>}
    <p>{note}</p>
  </div>;
}

export function WaveformExplorer({ waveform, sampleRate, processed=false }: Pick<ReportProps, 'waveform' | 'sampleRate'> & {processed?:boolean}) {
  const leads = useMemo(() => Object.entries(waveform || {}).filter(([, points]) => Array.isArray(points) && points.length > 1 && points.every(Number.isFinite)).map(([lead]) => lead), [waveform]);
  const [selectedLead, setSelectedLead] = useState('');
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState(0);
  const lead = leads.includes(selectedLead) ? selectedLead : leads[0] || '';
  const points = waveform?.[lead] || [];
  const visibleCount = Math.max(2, Math.ceil(points.length / zoom));
  const start = Math.min(offset, Math.max(0, points.length - visibleCount));
  const visible = points.slice(start, start + visibleCount);
  const safeRate = Number.isFinite(sampleRate) && sampleRate > 0 ? sampleRate : 500;
  const amplitude = points.reduce((max, value) => Math.max(max, Math.abs(value)), 0) || 1;
  const coordinates = visible.map((value, index) => `${(index / Math.max(1, visible.length - 1)) * 1000},${130 - (value / amplitude) * 105}`).join(' ');
  const marks = [0, 1, 2, 3, 4].map(i => ((start + ((visible.length - 1) * i / 4)) / safeRate).toFixed(2));
  const gridId = useId().replace(/:/g, '');

  return <section className="rpt-section">
    <div className="rpt-section-heading"><div><p className="eyebrow">SIGNAL DETAIL</p><h2>ECG explorer</h2><p>Inspect the supplied waveform, one lead at a time.</p></div><Waves size={26} strokeWidth={1.5} /></div>
    {!leads.length ? <div className="rpt-empty"><Waves size={36} strokeWidth={1.2}/><h3>No waveform to display</h3><p>Add a supported recording and generate an assessment to view the available waveform.</p><span className="rpt-text-label">No patient recording has been inferred.</span></div> : <>
      <div className="rpt-wave-tools"><label>Lead<select aria-label="Lead" value={lead} onChange={e => setSelectedLead(e.target.value)}>{leads.map(item => <option key={item} value={item}>{item}</option>)}</select></label><label>Zoom<select aria-label="Zoom" value={zoom} onChange={e => { setZoom(Number(e.target.value)); setOffset(0); }}><option value={1}>1× · Full signal</option><option value={2}>2×</option><option value={4}>4×</option></select></label><span className="rpt-wave-meta">{points.length.toLocaleString()} samples · {safeRate} Hz</span></div>
      <div className="rpt-wave-chart"><span className="rpt-wave-lead">{lead}</span><svg viewBox="0 0 1000 260" preserveAspectRatio="none" role="img" aria-label={`Uploaded ECG lead ${lead}, from ${marks[0]} to ${marks[4]} seconds. Amplitude is scaled for display; see the unit description below.`}><defs><pattern id={gridId} width="20" height="20" patternUnits="userSpaceOnUse"><path d="M 20 0 L 0 0 0 20" fill="none" stroke="#dbe6df" strokeWidth="0.6"/></pattern></defs><rect width="1000" height="260" fill={`url(#${gridId})`}/><line x1="0" x2="1000" y1="130" y2="130" stroke="#b9cfc3" strokeWidth="1"/><polyline fill="none" stroke="var(--teal, #137d70)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" points={coordinates}/></svg><div className="rpt-wave-axis">{marks.map((mark, index) => <span key={index}>{mark}s</span>)}</div></div>
      {zoom > 1 && <label className="rpt-wave-pan">Position in recording<input type="range" min={0} max={Math.max(0, points.length - visibleCount)} value={start} step={1} onChange={e => setOffset(Number(e.target.value))}/></label>}
      <p className="rpt-caption">Time uses the specified sampling rate. Amplitude is scaled to fit; processed signals use standardized units. This viewer does not interpret the recording.</p>
    </>}
    <p>{processed?'Processed signal overview: standardized amplitude, downsampled to 20 Hz; not a diagnostic tracing.':'Raw uploaded samples; declared millivolt units.'}</p>
  </section>;
}

function ScenarioExplorer({ values }: Pick<ReportProps, 'values'>) {
  const makeBaseline = () => Object.fromEntries(scenarioFields.map(field => [field.key, values[field.key] || '']));
  const [scenario, setScenario] = useState<Record<string, string>>(makeBaseline);
  const [resetMessage, setResetMessage] = useState('');
  useEffect(() => { setScenario(makeBaseline()); setResetMessage(''); }, [values]);
  const hasChanges = scenarioFields.some(({ key }) => scenario[key] !== (values[key] || ''));
  return <section className="rpt-section">
    <div className="rpt-section-heading"><div><p className="eyebrow">WHAT-IF EXPLORER</p><h2>Change a detail. Compare the inputs.</h2><p>Explore a hypothetical scenario while keeping the original assessment intact.</p></div><button className="btn btn-secondary rpt-reset" type="button" onClick={() => { setScenario(makeBaseline()); setResetMessage('Scenario reset to the original inputs.'); }}><RotateCcw size={15}/>Reset</button></div>
    <div className="rpt-scenario-layout"><div className="rpt-scenario-controls">{scenarioFields.map(field => {
      const base = providedNumber(values[field.key]);
      const next = providedNumber(scenario[field.key]);
      const invalid = base !== null && (next === null || next < field.min || next > field.max);
      return <div className="rpt-scenario-field" key={field.key}>
        <label htmlFor={`scenario-${field.key}`}>{field.label}<span>{field.unit}</span></label>
        {base === null ? <p className="rpt-missing-input">Not provided in the original assessment. <span>Add this value in your inputs to explore it.</span></p> : <><div className="rpt-slider-row"><input aria-label={`${field.label} slider`} type="range" min={field.min} max={field.max} step={field.step} value={Math.min(field.max, Math.max(field.min, next ?? base))} onChange={e => { setScenario(previous => ({ ...previous, [field.key]: e.target.value })); setResetMessage(''); }}/><input id={`scenario-${field.key}`} type="number" min={field.min} max={field.max} step={field.step} value={scenario[field.key]} aria-invalid={invalid} aria-describedby={invalid ? `scenario-error-${field.key}` : undefined} onChange={e => { setScenario(previous => ({ ...previous, [field.key]: e.target.value })); setResetMessage(''); }}/></div><div className="rpt-slider-limits"><span>{field.min}</span><span>Original: {base} {field.unit}</span><span>{field.max}</span></div>{invalid && <p id={`scenario-error-${field.key}`} className="rpt-error">Enter a value from {field.min} to {field.max}.</p>}</>}
      </div>;
    })}</div><div className="rpt-scenario-comparison"><div className="rpt-comparison-title"><h3>Input comparison</h3><span className="rpt-text-label">{hasChanges ? 'Scenario edited' : 'Original values'}</span></div><table><thead><tr><th scope="col">Measure</th><th scope="col">Baseline</th><th scope="col">Scenario</th></tr></thead><tbody>{scenarioFields.map(field => <tr key={field.key}><th scope="row">{field.label}<small>{field.unit}</small></th><td>{values[field.key] || '—'}</td><td>{scenario[field.key] || '—'}</td></tr>)}</tbody></table><div className="rpt-scenario-output"><span>Predicted change in risk</span><strong>Unavailable</strong><p>A simulation engine is not connected. Changing these inputs does not recalculate the recorded sample or create a personal estimate.</p></div></div></div>
    <p className="rpt-status" role="status">{resetMessage}</p>
    <div className="rpt-rule-note"><Info size={17}/><p>These comparisons are hypothetical, not a guaranteed treatment effect. Do not change medicines or treatment based on this preview.</p></div>
  </section>;
}

export default function ReportView({ values, isSample, waveform, sampleRate, onEdit }: ReportProps) {
  const [tab, setTab] = useState(0);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const reportRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const disclosureStates = new Map<HTMLDetailsElement, boolean>();
    const preparePrint = () => {
      reportRef.current?.querySelectorAll('details').forEach(details => {
        if (!disclosureStates.has(details)) disclosureStates.set(details, details.open);
        details.open = true;
      });
    };
    const restoreDisclosures = () => {
      disclosureStates.forEach((wasOpen, details) => { details.open = wasOpen; });
      disclosureStates.clear();
    };
    window.addEventListener('beforeprint', preparePrint);
    window.addEventListener('afterprint', restoreDisclosures);
    return () => {
      window.removeEventListener('beforeprint', preparePrint);
      window.removeEventListener('afterprint', restoreDisclosures);
      restoreDisclosures();
    };
  }, []);
  const tabId = useId().replace(/:/g, '');
  const tabs = [{ name: 'Overview', icon: FileText }, { name: 'ECG explorer', icon: Activity }, { name: 'Explore scenarios', icon: SlidersHorizontal }];
  const knownKeys = Object.keys(inputNames);
  const count = knownKeys.filter(key => values[key] !== undefined && values[key].trim() !== '').length;
  const missingCount = knownKeys.length - count;
  const number = (key: string) => providedNumber(values[key]);
  const sbp = number('systolic_bp'); const dbp = number('diastolic_bp');
  const cholesterol = number('total_cholesterol'); const hdl = number('hdl'); const triglycerides = number('triglycerides');
  const ratios = [
    { label: 'Pulse pressure', value: sbp !== null && dbp !== null ? `${(sbp - dbp).toFixed(0)} mmHg` : null, description: 'Systolic minus diastolic blood pressure.' },
    { label: 'Non-HDL cholesterol', value: cholesterol !== null && hdl !== null ? `${(cholesterol - hdl).toFixed(1)} mg/dL` : null, description: 'Total cholesterol minus HDL cholesterol.' },
    { label: 'Total cholesterol / HDL', value: cholesterol !== null && hdl !== null && hdl > 0 ? `${(cholesterol / hdl).toFixed(2)}` : null, description: 'Total cholesterol divided by HDL cholesterol.' },
    { label: 'Triglycerides / HDL', value: triglycerides !== null && hdl !== null && hdl > 0 ? `${(triglycerides / hdl).toFixed(2)}` : null, description: 'Triglycerides divided by HDL cholesterol.' },
  ];
  return <div className="rpt-root" ref={reportRef}>
    <div className="rpt-page-heading"><div><h2 className="rpt-scope-title">{isSample ? 'Recorded sample' : 'Your entered details'}</h2><p>{isSample ? 'A saved synthetic test run from the existing research app.' : 'Your inputs are ready to review. No personal predictions have been generated.'}</p></div><div className="rpt-heading-actions"><button className="btn btn-secondary" onClick={onEdit}><Pencil size={15}/>Edit inputs</button><button className="btn btn-primary" onClick={() => window.print()}><Printer size={16}/>Print / save PDF</button></div></div>
    <div className={`rpt-report-notice ${isSample ? 'rpt-sample-notice' : ''}`}><Info size={18}/><p><strong>{isSample ? 'Recorded synthetic sample — not a personal assessment.' : 'Personal predictions are unavailable.'}</strong> {isSample ? 'The values below come from a saved test run. They are not recalculated here, and are not results for the person using this preview.' : 'No analysis engine is connected. Your entered information is preserved; no sample values have been substituted.'}</p></div>
    <div className="rpt-tabs" role="tablist" aria-label="Report sections">{tabs.map(({ name, icon: Icon }, index) => <button key={name} ref={element => { tabRefs.current[index] = element; }} role="tab" id={`${tabId}-tab-${index}`} aria-controls={`${tabId}-panel-${index}`} aria-selected={tab === index} tabIndex={tab === index ? 0 : -1} className={tab === index ? 'is-active' : ''} onClick={() => setTab(index)} onKeyDown={event => { let next = index; if (event.key === 'ArrowRight') next = (index + 1) % tabs.length; else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length; else if (event.key === 'Home') next = 0; else if (event.key === 'End') next = tabs.length - 1; else return; event.preventDefault(); setTab(next); tabRefs.current[next]?.focus(); }}><Icon size={17}/>{name}</button>)}</div>
    <div role="tabpanel" id={`${tabId}-panel-0`} aria-labelledby={`${tabId}-tab-0`} hidden={tab !== 0} className="rpt-tab-panel" tabIndex={0}>
      <section className="rpt-section rpt-overview"><div className="rpt-section-heading"><div><p className="eyebrow">RESEARCH SUMMARY</p><h2>Different measures. Different meanings.</h2></div><span className="rpt-text-label">{isSample ? 'Recorded clinical-only run' : 'No analysis performed'}</span></div>
        <div className="rpt-metrics"><ReportMetric title="Illustrative health index" value={isSample ? String(demoRecord.health_score) : 'Unavailable'} unit={isSample ? '/ 100' : undefined} sample={isSample} primary note="Higher means less burden in an illustrative formula. This is not a percent chance of being healthy."/><ReportMetric title="Composite burden index" value="Unavailable" note={isSample ? 'Not retained in this recorded sample. This index is not an event probability.' : 'No model connected. A research burden index is not an event probability.'}/><ReportMetric title="PREVENT · 10-year total CVD" value={isSample ? String(demoRecord.prevent_10y_cvd_percent) : 'Unavailable'} unit={isSample ? '%' : undefined} sample={isSample} note={isSample ? 'Recorded local equation output. Assumed inputs and input-quality metadata were not retained in this snapshot.' : 'Total cardiovascular disease estimate. No local equation calculation is performed in this preview.'}/><ReportMetric title="Framingham cohort · 10-year CHD" value="Unavailable" note="Coronary heart disease is narrower than total CVD. This is a separate cohort model; no output is available here."/></div>
        <div className="rpt-compact-note"><Info size={15}/><span>The health index is an illustrative formula without outcome validation. Neither indices nor condition scores diagnose disease.</span></div>
      </section>
      <section className="rpt-section"><div className="rpt-section-heading"><div><p className="eyebrow">CLINICAL HISTORY & LABORATORY MODEL</p><h2>Clinical condition model scores</h2><p>Scores can overlap and do not add to 100%. They are not a personal chance of developing a condition.</p></div></div>
        <div className="rpt-condition-list">{conditionRows.map(condition => { const probability = isSample && !condition.abstain ? (demoRecord.disease_probabilities as Record<string, number>)[condition.code] * 100 : null; return <div className="rpt-condition" key={condition.code}><div className="rpt-condition-top"><div><h3>{condition.label}<span>{condition.code}</span></h3><p>{condition.description}</p></div><strong className={probability === null ? 'rpt-condition-unavailable' : ''}>{!isSample ? 'Unavailable' : condition.abstain ? 'Inconclusive' : `${probability!.toFixed(1)}%`}</strong></div>{probability !== null && <><div className="rpt-bar" role="img" aria-label={`${condition.label}: recorded synthetic sample model score ${probability.toFixed(1)} percent`}><span style={{ width: `${Math.min(100, probability)}%` }}/></div><span className="rpt-snapshot-label">Recorded synthetic sample · review threshold unavailable in snapshot</span></>}</div>; })}</div>
        <div className="rpt-rule-note"><Info size={17}/><p>Clinical-only condition assessment: these estimates use available health details and labs. ECG waveform fusion is withheld because its training preprocessing has not been reproduced. ECG patterns are assessed separately.</p></div>
      </section>
      <section className="rpt-section"><div className="rpt-section-heading"><div><p className="eyebrow">INPUT CONTEXT</p><h2>What this report includes</h2></div><div className="rpt-input-count"><span><Check size={14}/>{count} provided</span><span>{missingCount} not provided</span></div></div><div className="rpt-input-context"><div><h3>Clinical ratios</h3><p className="rpt-caption">Simple arithmetic from the values you supplied. No missing values are assumed.</p><dl className="rpt-ratios">{ratios.map(ratio => <div key={ratio.label}><dt><details><summary>{ratio.label}<Info size={13}/></summary><p>{ratio.description}</p></details></dt><dd className={!ratio.value ? 'rpt-subtle' : ''}>{ratio.value || 'Unavailable'}</dd></div>)}</dl></div><div><h3>Input quality</h3><p>Completeness describes the available inputs, not confidence in a result.</p><div className="rpt-completeness" role="img" aria-label={`${count} of ${knownKeys.length} input fields provided`}><span style={{ width: `${count / knownKeys.length * 100}%` }}/></div><p className="rpt-caption">{count} of {knownKeys.length} supported fields provided. Optional fields may remain empty.</p><details className="rpt-inline-details"><summary>View missing inputs<ChevronDown size={15}/></summary><p>{knownKeys.filter(key => !values[key]?.trim()).map(key => inputNames[key]).join(', ') || 'All supported fields have a value.'}</p></details><details className="rpt-inline-details"><summary>View values used<ChevronDown size={15}/></summary><dl className="rpt-value-list">{knownKeys.filter(key => values[key]?.trim()).map(key => <div key={key}><dt>{inputNames[key]}</dt><dd>{values[key]}</dd></div>)}</dl></details></div></div></section>
      <details className="rpt-methods"><summary><div><FileText size={18}/><span>Methods & limitations</span></div><ChevronDown size={17}/></summary><div className="rpt-methods-body"><p><strong>Research & Educational Simulation Only.</strong> This interface is not a medical device. Consult a qualified clinician for interpretation and care decisions.</p><p>The sample is a saved clinical-only response from a synthetic report upload test. Its health index, PREVENT output, and clinical scores are preserved from that response. The snapshot does not contain composite burden, Framingham CHD, calibration thresholds, or input-assumption metadata; those outputs remain unavailable.</p><p>The PREVENT-based estimate and the Framingham cohort model predict different outcomes. The original local PREVENT implementation can assume missing inputs; unknown assumptions in a stored snapshot must not be presented as complete input quality.</p><p>Acute MI and conduction-block decisions are inconclusive because of insufficient reliability. Dataset validation metrics are not confidence in an individual result. No personal inference, report OCR, waveform diagnosis, or risk simulation runs in this frontend.</p></div></details>
      <div className="rpt-next-action"><div><h3>Explore a hypothetical change</h3><p>Compare a scenario with the original inputs.</p></div><button className="btn btn-secondary" onClick={() => { setTab(2); tabRefs.current[2]?.focus(); }}>Explore scenarios<ArrowRight size={16}/></button></div>
    </div>
    <div role="tabpanel" id={`${tabId}-panel-1`} aria-labelledby={`${tabId}-tab-1`} hidden={tab !== 1} className="rpt-tab-panel" tabIndex={0}><WaveformExplorer waveform={waveform} sampleRate={sampleRate}/></div>
    <div role="tabpanel" id={`${tabId}-panel-2`} aria-labelledby={`${tabId}-tab-2`} hidden={tab !== 2} className="rpt-tab-panel" tabIndex={0}><ScenarioExplorer values={values}/></div>
    <footer className="rpt-footer">Research & Educational Simulation Only. {isSample ? 'Recorded synthetic sample.' : 'No personal predictions have been generated.'}</footer>
  </div>;
}
