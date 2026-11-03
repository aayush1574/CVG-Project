import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, ChevronRight, CircleAlert, FileText, FolderUp, HeartPulse, Info, LoaderCircle, PencilLine, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { fields, fieldError, groups, parseClinical, parseWaveform, standardLeads, type Source, type Values } from './data';
import './inputs.css';

type Files = { report: File | null; ecg: File | null; header: File | null };
type Props = {
  values: Values;
  sources: Record<string, Source>;
  onChange: (key: string, value: string, source?: Source) => void;
  files: Files;
  onFiles: (files: Files) => void;
  waveform: Record<string, number[]> | null;
  onWaveform: (waveform: Record<string, number[]> | null) => void;
  sampleRate: number;
  onSampleRate: (n: number) => void;
  onReview: () => void;
  isSample: boolean;
};

const ext = (file: File | null) => file?.name.split('.').pop()?.toLowerCase() || '';
const stem = (file: File | null) => file?.name.replace(/\.[^.]+$/, '') || '';
const reportFormats = ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff', 'csv', 'json'];
const ecgFormats = ['csv', 'npy', 'dat', 'hea', 'png', 'jpg', 'jpeg'];
const fileSize = (file: File) => file.size < 1_000_000 ? `${Math.max(1, Math.round(file.size / 1000))} KB` : `${(file.size / 1_000_000).toFixed(1)} MB`;
// Keep read failures with the local File object when navigating between pages.
const fileReadErrors = new WeakMap<File, string>();

export default function InputWorkspace({ values, sources, onChange, files, onFiles, waveform, onWaveform, sampleRate, onSampleRate, onReview, isSample }: Props) {
  const [tab, setTab] = useState<'upload' | 'manual'>('upload');
  const [errors, setErrors] = useState({ report: files.report ? fileReadErrors.get(files.report) || '' : '', ecg: files.ecg ? fileReadErrors.get(files.ecg) || '' : '', header: '' });
  const [reading, setReading] = useState({ report: false, ecg: false });
  const [notice, setNotice] = useState('');
  const [showErrors, setShowErrors] = useState(false);
  const [dragging, setDragging] = useState<'report' | 'ecg' | null>(null);
  const filesRef = useRef(files);
  filesRef.current = files;
  const operations = useRef({ report: 0, ecg: 0 });
  useEffect(() => () => { operations.current.report++; operations.current.ecg++; }, []);
  const reportInput = useRef<HTMLInputElement>(null);
  const ecgInput = useRef<HTMLInputElement>(null);
  const headerInput = useRef<HTMLInputElement>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const filledCount = fields.filter(f => values[f.key] !== undefined && values[f.key] !== '').length;
  const validationErrors = fields.filter(f => fieldError(f, values[f.key], values));
  const ecgExtension = ext(files.ecg);
  const paired = ['dat', 'hea'].includes(ecgExtension);
  const usesRate = ['csv', 'npy'].includes(ecgExtension);
  const pairError = paired && (!files.header ? `Add the matching .${ecgExtension === 'dat' ? 'hea' : 'dat'} companion file.` : stem(files.ecg) !== stem(files.header) ? 'Both WFDB filenames must match before the extension.' : ext(files.header) !== (ecgExtension === 'dat' ? 'hea' : 'dat') ? `The companion must be a .${ecgExtension === 'dat' ? 'hea' : 'dat'} file.` : '') || '';
  const rateError = usesRate && (!Number.isInteger(sampleRate) || sampleRate < 100) ? 'Enter a whole-number sampling rate of at least 100 Hz.' : '';

  function updateFiles(update: Partial<Files>) {
    const next = { ...filesRef.current, ...update };
    filesRef.current = next;
    onFiles(next);
  }

  function checkFile(file: File, allowed: string[]) {
    if (!allowed.includes(ext(file))) return `Unsupported file type. Choose ${allowed.map(x => `.${x}`).join(', ')}.`;
    if (file.size > 10_000_000) return 'This file exceeds 10 MB. Choose a smaller file.';
    if (file.size === 0) return 'This file is empty. Choose a file with data.';
    return '';
  }

  async function selectReport(file: File) {
    const issue = checkFile(file, reportFormats);
    if (issue) { setErrors(e => ({ ...e, report: issue })); return; }
    const operation = ++operations.current.report;
    setErrors(e => ({ ...e, report: '' }));
    setNotice('');
    updateFiles({ report: file });
    if (!['csv', 'json'].includes(ext(file))) {
      setReading(r => ({ ...r, report: false }));
      setNotice('File selected. PDF and image extraction is unavailable in this standalone preview. Enter its values manually.');
      return;
    }
    setReading(r => ({ ...r, report: true }));
    fileReadErrors.set(file, 'Report reading was interrupted. Replace the file to try again.');
    try {
      const parsed = parseClinical(await file.text(), ext(file));
      if (operations.current.report !== operation) return;
      fileReadErrors.delete(file);
      Object.entries(parsed).forEach(([key, value]) => onChange(key, value, 'Extracted'));
      setNotice(`${Object.keys(parsed).length} values read locally from ${file.name}. Review them in Enter details before continuing.`);
    } catch (error) {
      if (operations.current.report === operation) {
        const message = error instanceof Error ? error.message : 'Could not read this report. Try another file or enter values manually.';
        fileReadErrors.set(file, message);
        setErrors(e => ({ ...e, report: message }));
      }
    } finally {
      if (operations.current.report === operation) setReading(r => ({ ...r, report: false }));
    }
  }

  async function selectEcg(file: File) {
    const issue = checkFile(file, ecgFormats);
    if (issue) { setErrors(e => ({ ...e, ecg: issue })); return; }
    const operation = ++operations.current.ecg;
    setErrors(e => ({ ...e, ecg: '', header: '' }));
    updateFiles({ ecg: file, header: null });
    onWaveform(null);
    if (['csv', 'npy'].includes(ext(file))) onSampleRate(500);
    if (ext(file) !== 'csv') { setReading(r => ({ ...r, ecg: false })); return; }
    setReading(r => ({ ...r, ecg: true }));
    fileReadErrors.set(file, 'Waveform reading was interrupted. Replace the file to try again.');
    try {
      const parsed = parseWaveform(await file.text());
      if (operations.current.ecg !== operation) return;
      fileReadErrors.delete(file);
      onWaveform(parsed);
    } catch (error) {
      if (operations.current.ecg === operation) {
        const message = error instanceof Error ? error.message : 'Could not read this waveform. Check the file and try again.';
        fileReadErrors.set(file, message);
        setErrors(e => ({ ...e, ecg: message }));
      }
    } finally {
      if (operations.current.ecg === operation) setReading(r => ({ ...r, ecg: false }));
    }
  }

  function selectHeader(file: File) {
    const issue = checkFile(file, ['dat', 'hea']);
    if (issue) { setErrors(e => ({ ...e, header: issue })); return; }
    setErrors(e => ({ ...e, header: '' }));
    updateFiles({ header: file });
  }

  function removeFile(kind: 'report' | 'ecg') {
    operations.current[kind]++;
    setReading(r => ({ ...r, [kind]: false }));
    setErrors(e => ({ ...e, [kind]: '', ...(kind === 'ecg' ? { header: '' } : {}) }));
    updateFiles(kind === 'ecg' ? { ecg: null, header: null } : { report: null });
    if (kind === 'ecg') onWaveform(null);
    else setNotice('Report removed. Previously imported values are kept so you can review, edit, or clear them.');
  }

  function review() {
    setShowErrors(true);
    if (validationErrors.length) {
      setTab('manual');
      setNotice(`Check ${validationErrors.length} ${validationErrors.length === 1 ? 'field' : 'fields'} before reviewing your inputs.`);
      requestAnimationFrame(() => document.getElementById(`inp-${validationErrors[0].key}`)?.focus());
      return;
    }
    if (pairError || rateError || errors.report || errors.ecg || errors.header) { setTab('upload'); setNotice('Resolve the file message below, or remove the file to continue with your entered details.'); return; }
    onReview();
  }

  function fileRow(file: File, kind: 'report' | 'ecg') {
    return <div className="inp-file-row"><div className="inp-file-icon"><FileText size={20} /></div><div className="inp-file-name"><strong title={file.name}>{file.name}</strong><span>{fileSize(file)} · Kept in this browser tab</span></div><button className="inp-icon-button" type="button" aria-label={`Remove ${kind === 'report' ? 'report' : 'ECG'}`} onClick={() => removeFile(kind)}><Trash2 size={18} /></button></div>;
  }

  return <div className="inp-workspace">
    <div className="inp-topline"><div className="inp-tabs" role="tablist" aria-label="Add health information">{(['upload', 'manual'] as const).map((key, index) => <button key={key} ref={el => { tabs.current[index] = el; }} role="tab" id={`inp-tab-${key}`} aria-selected={tab === key} aria-controls={`inp-panel-${key}`} tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)} onKeyDown={event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 1 : 1 - index; setTab(next ? 'manual' : 'upload'); tabs.current[next]?.focus(); } }}><span>{key === 'upload' ? <Upload size={17} /> : <PencilLine size={17} />}</span>{key === 'upload' ? 'Upload reports' : 'Enter details'}</button>)}</div><span className="inp-entry-count"><span>{filledCount}</span> of {fields.length} fields provided</span></div>

    {notice && <div className="inp-notice" role="status"><Info size={18} /><p>{notice}</p></div>}
    {isSample && <p className="inp-sample-note"><Info size={15} /> Sample profile · Edits are preserved as a separate preview and do not recalculate recorded sample scores.</p>}

    {tab === 'upload' ? <div role="tabpanel" id="inp-panel-upload" aria-labelledby="inp-tab-upload" className="inp-upload-layout">
      <div className="inp-uploads">
        <section className="inp-upload-section" aria-labelledby="inp-report-title">
          <div className="inp-section-heading"><span className="inp-section-number">01</span><div><h2 id="inp-report-title">Laboratory report</h2><p>Bring your existing measurements into view.</p></div><span className="inp-optional">Optional</span></div>
          <div className={`inp-dropzone ${dragging === 'report' ? 'inp-dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging('report'); }} onDragLeave={() => setDragging(null)} onDrop={event => { event.preventDefault(); setDragging(null); if (event.dataTransfer.files.length > 1) setErrors(e => ({ ...e, report: 'Choose one report at a time.' })); else if (event.dataTransfer.files[0]) void selectReport(event.dataTransfer.files[0]); }}>
            <input ref={reportInput} type="file" tabIndex={-1} className="inp-file-input" aria-label="Select laboratory report" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.csv,.json" onChange={event => { if (event.target.files?.[0]) void selectReport(event.target.files[0]); event.target.value = ''; }} />
            {files.report ? fileRow(files.report, 'report') : <><FolderUp size={31} strokeWidth={1.4} /><h3>Drop your report here</h3><p>PDF, image, CSV or JSON · Up to 10 MB</p></>}
            <button type="button" className="btn btn-secondary inp-browse" onClick={() => reportInput.current?.click()}>{files.report ? 'Replace report' : 'Browse files'}<ArrowRight size={16} /></button>
          </div>
          {reading.report && <p className="inp-file-status" role="status"><LoaderCircle size={16} className="inp-spinner" /> Reading report in your browser…</p>}
          {errors.report && <div className="inp-upload-error" role="alert"><p className="inp-error"><CircleAlert size={16} />{errors.report}</p><button type="button" onClick={() => removeFile('report')}>{files.report ? 'Remove report' : 'Dismiss'}</button></div>}
          <p className="inp-format-note">CSV and JSON values can be read locally. PDF and image files can be selected; <button type="button" onClick={() => setTab('manual')}>enter their values manually <ChevronRight size={13} /></button>.</p>
        </section>

        <section className="inp-upload-section" aria-labelledby="inp-ecg-title">
          <div className="inp-section-heading"><span className="inp-section-number">02</span><div><h2 id="inp-ecg-title">ECG waveform</h2><p>Add an electrical recording of the heart.</p></div><span className="inp-optional">Optional</span></div>
          <div className={`inp-dropzone inp-ecg-dropzone ${dragging === 'ecg' ? 'inp-dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging('ecg'); }} onDragLeave={() => setDragging(null)} onDrop={event => { event.preventDefault(); setDragging(null); if (event.dataTransfer.files.length > 1) setErrors(e => ({ ...e, ecg: 'Choose the ECG file first, then add its companion below.' })); else if (event.dataTransfer.files[0]) void selectEcg(event.dataTransfer.files[0]); }}>
            <input ref={ecgInput} type="file" tabIndex={-1} className="inp-file-input" aria-label="Select ECG waveform" accept=".csv,.npy,.dat,.hea,.png,.jpg,.jpeg" onChange={event => { if (event.target.files?.[0]) void selectEcg(event.target.files[0]); event.target.value = ''; }} />
            {files.ecg ? fileRow(files.ecg, 'ecg') : <><HeartPulse size={31} strokeWidth={1.4} /><h3>Drop your ECG file here</h3><p>CSV, NPY, WFDB or image · Up to 10 MB</p></>}
            <button type="button" className="btn btn-secondary inp-browse" onClick={() => ecgInput.current?.click()}>{files.ecg ? 'Replace ECG' : 'Browse files'}<ArrowRight size={16} /></button>
          </div>
          {reading.ecg && <p className="inp-file-status" role="status"><LoaderCircle size={16} className="inp-spinner" /> Reading waveform samples…</p>}
          {errors.ecg && <div className="inp-upload-error" role="alert"><p className="inp-error"><CircleAlert size={16} />{errors.ecg}</p><button type="button" onClick={() => removeFile('ecg')}>{files.ecg ? 'Remove ECG' : 'Dismiss'}</button></div>}
          {waveform && files.ecg && <p className="inp-file-status inp-success" role="status"><Check size={16} /> {Object.keys(waveform).length}-lead waveform loaded · {Object.values(waveform)[0].length.toLocaleString()} samples per lead</p>}
          {paired && <div className="inp-companion"><label htmlFor="inp-companion">WFDB companion file</label><input ref={headerInput} id="inp-companion" className="inp-file-input" type="file" tabIndex={-1} accept={ecgExtension === 'dat' ? '.hea' : '.dat'} onChange={event => { if (event.target.files?.[0]) selectHeader(event.target.files[0]); event.target.value = ''; }} /><div className="inp-companion-controls"><button type="button" className="btn btn-secondary" onClick={() => headerInput.current?.click()}>{files.header ? 'Replace companion' : `Choose .${ecgExtension === 'dat' ? 'hea' : 'dat'} file`}</button>{files.header && <><span title={files.header.name}>{files.header.name}</span><button className="inp-icon-button" type="button" aria-label="Remove companion file" onClick={() => { updateFiles({ header: null }); setErrors(e => ({ ...e, header: '' })); }}><Trash2 size={16} /></button></>}</div>{(pairError || errors.header) && <p className="inp-error" role={showErrors || errors.header ? 'alert' : undefined}><CircleAlert size={16} />{errors.header || pairError}</p>}{!pairError && !errors.header && <p className="inp-file-status inp-success"><Check size={16} /> Matching file pair selected.</p>}</div>}
          {usesRate && <div className="inp-rate"><div><label htmlFor="inp-sample-rate">Sampling rate</label><p>Use the recording’s original rate.</p></div><div className="inp-number-wrap"><input id="inp-sample-rate" type="number" min="100" step="1" value={Number.isNaN(sampleRate) ? '' : sampleRate} aria-invalid={!!rateError} aria-describedby={rateError ? 'inp-rate-error' : undefined} onChange={event => onSampleRate(event.target.value === '' ? NaN : Number(event.target.value))} /><span>Hz</span></div>{rateError && <p className="inp-error" id="inp-rate-error">{rateError}</p>}</div>}
          {files.ecg && ecgExtension !== 'csv' && <p className="inp-format-note">{paired ? 'WFDB decoding' : ecgExtension === 'npy' ? 'NPY decoding' : 'Scanned ECG extraction'} is unavailable in this preview. The file stays local; no waveform or model scores are invented.</p>}
          <details className="inp-file-help"><summary>Supported lead modes <Info size={14} /></summary><div><p><strong>12 leads:</strong> {standardLeads.join(', ')}.</p><p><strong>6 leads:</strong> I, II, III, aVR, aVL, aVF. <strong>1 lead:</strong> I.</p><p>CSV files need named lead columns and numeric samples. NPY arrays use samples × leads. Partial leads and scanned ECGs are experimental research inputs. CSV previews show the supplied signal; this frontend does not interpret it.</p></div></details>
        </section>
      </div>
      <aside className="inp-aside"><div className="inp-aside-mark"><ShieldCheck size={25} strokeWidth={1.5} /></div><h3>Your details.<br />Your pace.</h3><p>Add only what you have. You can complete this journey with health details alone.</p><div className="inp-aside-divider" /><ol><li><span>1</span><div><strong>Add your information</strong><p>Upload a file or enter values.</p></div></li><li><span>2</span><div><strong>Check the details</strong><p>Review and correct every input.</p></div></li><li><span>3</span><div><strong>Explore the report</strong><p>See available information and limitations.</p></div></li></ol><div className="inp-local-note"><ShieldCheck size={16} /><p>Files and entries stay in this tab. Nothing is sent to a server.</p></div></aside>
    </div> : <div role="tabpanel" id="inp-panel-manual" aria-labelledby="inp-tab-manual" className="inp-manual-panel">
      <div className="inp-manual-intro"><div><h2>Your health details</h2><p>All fields are optional. Missing information stays “Not provided.”</p></div><a className="inp-text-link" href="#inp-group-2">Jump to laboratory results <ArrowRight size={15} /></a></div>
      {groups.map((group, index) => <section key={group.name} id={`inp-group-${index}`} className="inp-field-section"><div className="inp-group-heading"><span className="inp-section-number">0{index + 1}</span><div><h3>{group.name}</h3><p>{group.description}</p></div></div><div className="inp-fields">{group.fields.map(field => {
        const value = values[field.key] ?? '';
        const issue = fieldError(field, value, values);
        const source = sources[field.key];
        const descriptionId = field.help || issue ? `inp-help-${field.key}` : undefined;
        const change = (next: string) => onChange(field.key, next, source === 'Extracted' || source === 'Sample' || source === 'Corrected' ? 'Corrected' : 'Entered');
        return <div key={field.key} className={`inp-field ${issue ? 'inp-field-invalid' : ''}`}><label htmlFor={`inp-${field.key}`}><span>{field.label}</span>{source && value !== '' ? <span className={`inp-source inp-source-${source.toLowerCase()}`}>{source}</span> : <span className="inp-optional">Optional</span>}</label>{field.options ? <select id={`inp-${field.key}`} value={value} aria-invalid={!!issue} aria-describedby={descriptionId} onChange={event => change(event.target.value)}><option value="">Not provided</option>{field.options.map(option => <option key={option} value={option}>{option.charAt(0).toUpperCase() + option.slice(1)}</option>)}</select> : <div className="inp-number-wrap"><input id={`inp-${field.key}`} type="number" inputMode="decimal" min={field.min} max={field.max} step="any" value={value} placeholder="Not provided" aria-invalid={!!issue} aria-describedby={descriptionId} onChange={event => change(event.target.value)} />{field.unit && <span>{field.unit}</span>}</div>}{(issue || field.help) && <p id={descriptionId} className={issue ? 'inp-error' : 'inp-field-help'}>{issue || field.help}</p>}</div>;
      })}</div></section>)}
    </div>}

    <div className="inp-footer"><p><ShieldCheck size={16} /><span>Your progress is kept as you move between steps.</span></p><button type="button" className="btn btn-primary" disabled={reading.report || reading.ecg} onClick={review}>Review inputs <ArrowRight size={17} /></button></div>
  </div>;
}


