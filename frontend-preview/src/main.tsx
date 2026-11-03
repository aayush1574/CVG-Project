import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDownToLine, ArrowLeft, ArrowRight, BookOpen, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, ClipboardCheck, FileHeart, FileText, FlaskConical, Heart, Home, Info, Leaf, LockKeyhole, Menu, Pause, Play, Plus, ScanLine, ShieldCheck, Sparkles, Upload, X } from 'lucide-react';
import InputWorkspace from './Inputs';
import ReportView from './ReportView';
import WelcomeExperience from './WelcomeExperience';
import useMotionPreference from './useMotionPreference';
import { fields, groups, fieldError, type Values, type Source } from './data';
import demoRecord from './demo-record.json';
import '@fontsource-variable/manrope';
import '@fontsource/dm-serif-display/latin-400.css';
import './index.css';
import './refinement.css';
import './interaction-polish.css';
import './motion-system.css';

type Page = 'welcome' | 'inputs' | 'review' | 'results' | 'learn';
type Files = {report:File|null;ecg:File|null;header:File|null};
const emptyFiles:Files={report:null,ecg:null,header:null};
const sampleValues=Object.fromEntries(Object.entries(demoRecord.extracted_values).map(([k,v])=>[k,String(v)]));
const steps=[['inputs','Add details'],['review','Review inputs'],['results','View report']] as const;

function App(){
  const motion = useMotionPreference();
  const [page,setPage]=useState<Page>('welcome');
  const [values,setValues]=useState<Values>({});
  const [sources,setSources]=useState<Record<string,Source>>({});
  const [files,setFiles]=useState<Files>(emptyFiles);
  const [waveform,setWaveform]=useState<Record<string,number[]>|null>(null);
  const [sampleRate,setSampleRate]=useState(500);
  const [sampleMode,setSampleMode]=useState(false);
  const [hasReport,setHasReport]=useState(false);
  const [mobileMenu,setMobileMenu]=useState(false);
  const [dialog,setDialog]=useState<'sample'|'new'|'help'|null>(null);
  const [reviewFilter,setReviewFilter]=useState<'provided'|'all'>('provided');
  const [notice,setNotice]=useState('');
  const mainRef=useRef<HTMLElement>(null);
  const dialogRef=useRef<HTMLDialogElement>(null);
  const prevFocus=useRef<HTMLElement|null>(null);
  const provided=fields.filter(f=>values[f.key]!==undefined&&values[f.key]!=='');
  const valid=fields.every(f=>!fieldError(f,values[f.key],values));
  const exactSample=sampleMode&&Object.keys(values).filter(k=>values[k]!=='').length===Object.keys(sampleValues).length&&Object.entries(sampleValues).every(([k,v])=>values[k]===v);

  function go(next:Page){setPage(next);setMobileMenu(false);setNotice('');window.scrollTo({top:0,behavior:'instant'});}
  useEffect(()=>{mainRef.current?.focus({preventScroll:true});},[page]);
  useEffect(()=>{if(dialog){prevFocus.current=document.activeElement as HTMLElement;dialogRef.current?.showModal();}else{dialogRef.current?.close();prevFocus.current?.focus();}},[dialog]);
  function change(key:string,value:string,source:Source='Entered'){setValues(old=>({...old,[key]:value}));setSources(old=>({...old,[key]:source}));setHasReport(false);}
  function clear(){setValues({});setSources({});setFiles(emptyFiles);setWaveform(null);setSampleRate(500);setSampleMode(false);setHasReport(false);setDialog(null);go('inputs');}
  function requestNew(){if(provided.length||files.report||files.ecg)setDialog('new');else clear();}
  function loadSample(){setValues({...sampleValues});setSources(Object.fromEntries(Object.keys(sampleValues).map(k=>[k,'Sample'])));setFiles(emptyFiles);setWaveform(null);setSampleMode(true);setHasReport(false);setDialog(null);go('review');}
  function openReport(){if(!valid){setNotice('Correct the highlighted values before opening your report.');return;}setHasReport(true);go('results');}
  function downloadInputs(){const blob=new Blob([JSON.stringify(Object.fromEntries(Object.entries(values).filter(([,v])=>v!=='')),null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=sampleMode?'cardioscope-sample-inputs.json':'cardioscope-inputs.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  const currentStep=steps.findIndex(([p])=>p===page);
  const sectionName={welcome:'Overview',inputs:'Add details',review:'Review inputs',results:'Research report',learn:'Understanding your report'}[page];
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    {mobileMenu&&<button className="nav-scrim" aria-label="Close navigation" onClick={()=>setMobileMenu(false)}/>}
    <aside className={`sidebar ${mobileMenu?'is-open':''}`} aria-label="Main navigation">
      <button className="brand" onClick={()=>go('welcome')} aria-label="CardioScope home"><span className="brand-symbol"><Activity size={25}/></span><span>CardioScope<small>HEART HEALTH, IN FOCUS</small></span></button>
      <div className="sidebar-section-label">WORKSPACE</div>
      <nav>
        <button className={`nav-item ${page==='welcome'?'active':''}`} aria-current={page==='welcome'?'page':undefined} onClick={()=>go('welcome')}><Home size={18}/>Overview<span className="nav-dot"/></button>
        <button className={`nav-item ${page==='inputs'||page==='review'?'active':''}`} aria-current={page==='inputs'||page==='review'?'page':undefined} onClick={()=>go('inputs')}><FileHeart size={18}/>Assessment{provided.length>0&&<span className="nav-count">{provided.length}</span>}</button>
        <button className={`nav-item ${page==='results'?'active':''}`} aria-current={page==='results'?'page':undefined} onClick={()=>{if(hasReport)go('results');else{go('inputs');setNotice('Add or review your details to open a report, or try the recorded sample from Overview.');}}}><FileText size={18}/>Research report</button>
      </nav>
      <div className="sidebar-section-label second">RESOURCES</div>
      <nav><button className={`nav-item ${page==='learn'?'active':''}`} aria-current={page==='learn'?'page':undefined} onClick={()=>go('learn')}><BookOpen size={18}/>How it works</button><button className="nav-item" onClick={()=>setDialog('help')}><CircleHelp size={18}/>Help &amp; guidance</button></nav>
      <div className="sidebar-bottom">
        <div className="research-note"><span className="research-icon"><FlaskConical size={19}/></span><strong>Made for exploration</strong><p>A research perspective.<br/>A more informed conversation.</p><button onClick={()=>go('learn')}>About this workspace <ArrowRight size={14}/></button></div>
        <div className="local-mode"><span className="status-dot"/><div>Local preview<small>Your information stays here</small></div><LockKeyhole size={15}/></div>
      </div>
    </aside>

    <div className="app-body">
      <header className="topbar"><div className="breadcrumb"><button className="mobile-toggle icon-button" aria-label="Open navigation" aria-expanded={mobileMenu} onClick={()=>setMobileMenu(true)}><Menu size={21}/></button><span>Workspace</span><ChevronRight size={14}/><strong>{sectionName}</strong></div><div className="topbar-right"><button className="app-motion-control" onClick={motion.toggle} disabled={motion.reduced||motion.saveData} aria-label={motion.reduced?'System reduced motion enabled':motion.saveData?'Data saving enabled for animations':motion.paused?'Enable animations':'Pause animations'} aria-pressed={!motion.enabled} title={motion.reduced?'Follows your system reduced-motion setting':motion.saveData?'Follows your data-saving preference':motion.enabled?'Pause animations throughout the preview':'Enable animations throughout the preview'}>{motion.enabled?<Pause size={13}/>:<Play size={13}/>}<span>{motion.reduced?'Reduced motion':motion.saveData?'Data saver':motion.paused?'Motion off':'Motion on'}</span></button><span className="engine-status"><span className="status-dot"/>Preview ready<span className="engine-extra"> · Engine disconnected</span></span><button className="icon-button help-button" aria-label="Help and guidance" onClick={()=>setDialog('help')}><CircleHelp size={19}/></button></div></header>

      <main id="main-content" className={`main-content page-${page}`} ref={mainRef} tabIndex={-1}>
        {page==='welcome'&&<WelcomeExperience motion={motion} hasDetails={Boolean(provided.length||files.report||files.ecg)} onStart={()=>provided.length||files.report||files.ecg?go('inputs'):requestNew()} onSample={()=>setDialog('sample')} onLearn={()=>go('learn')}/>}

        {(page==='inputs'||page==='review'||page==='results')&&<div className="assessment-shell page-enter" key={page}><div className="assessment-heading"><div><div className="eyebrow">{sampleMode?'RECORDED SYNTHETIC SAMPLE':'YOUR WORKSPACE'}</div><h1>{page==='inputs'?'Start with what you know.':page==='review'?'A moment to make sure.':'Your research report.'}</h1><p>{page==='inputs'?'Add your details at your pace. Leave anything you don’t know blank.':page==='review'?'Check the details below. Every value should tell the right story.':'Your inputs, research estimates, and their limitations in one place.'}</p></div><button className="btn btn-secondary btn-small" onClick={requestNew}><Plus size={16}/>New assessment</button></div>
          <nav className="stepper" aria-label="Assessment steps">{steps.map(([target,label],index)=><button key={target} className={`step ${index===currentStep?'current':''} ${index<currentStep?'complete':''}`} aria-current={index===currentStep?'step':undefined} disabled={(target==='results'&&!hasReport)||(target==='review'&&page==='inputs')} onClick={()=>go(target)}><span className="step-number">{index<currentStep?<Check size={15}/>:index+1}</span><span>{label}</span>{index<steps.length-1&&<span className="step-line"/>}</button>)}</nav>
          {sampleMode&&<div className="sample-banner"><FlaskConical size={18}/><span><strong>{exactSample?'Sample demonstration':'Edited sample'}</strong> · {exactSample?'Recorded synthetic inputs and outputs. This is not a personal assessment.':'Recorded outputs no longer match these inputs and will be unavailable.'}</span><button onClick={clear}>Use my own details <ArrowRight size={14}/></button></div>}
          {notice&&<div className="notice" role="status"><Info size={18}/>{notice}</div>}
          {page==='inputs'&&<InputWorkspace values={values} sources={sources} onChange={change} files={files} onFiles={next=>{setFiles(next);setHasReport(false);}} waveform={waveform} onWaveform={next=>{setWaveform(next);setHasReport(false);}} sampleRate={sampleRate} onSampleRate={next=>{setSampleRate(next);setHasReport(false);}} onReview={()=>go('review')} isSample={sampleMode}/>}
          {page==='review'&&<div className="review-layout"><div className="review-main"><div className="review-toolbar"><div><h2>Details for your report</h2><p>{provided.length} provided · {fields.length-provided.length} not provided · No assumed values</p></div><div className="segmented" aria-label="Filter review values"><button aria-pressed={reviewFilter==='provided'} className={reviewFilter==='provided'?'selected':''} onClick={()=>setReviewFilter('provided')}>Provided</button><button aria-pressed={reviewFilter==='all'} className={reviewFilter==='all'?'selected':''} onClick={()=>setReviewFilter('all')}>All fields</button></div></div>
            {provided.length===0&&reviewFilter==='provided'?<div className="empty-state"><ClipboardCheck size={35}/><h3>No details added yet</h3><p>You can enter a few values, upload a structured report, or explore the recorded sample.</p><div><button className="btn btn-primary" onClick={()=>go('inputs')}>Add details <ArrowRight size={16}/></button><button className="text-button" onClick={()=>setDialog('sample')}>Try a sample</button></div></div>:groups.map(group=>{const visible=group.fields.filter(f=>reviewFilter==='all'||values[f.key]);return visible.length>0&&<section className="review-group" key={group.name}><h3>{group.name}</h3><div className="review-table">{visible.map(f=><div className="review-row" key={f.key}><label htmlFor={`review-${f.key}`}>{f.label}{f.unit&&<small>{f.unit}</small>}</label><div>{f.options?<select id={`review-${f.key}`} value={values[f.key]||''} onChange={e=>change(f.key,e.target.value,sources[f.key]==='Extracted'||sources[f.key]==='Sample'||sources[f.key]==='Corrected'?'Corrected':'Entered')}><option value="">Not provided</option>{f.options.map(o=><option key={o} value={o}>{o[0].toUpperCase()+o.slice(1)}</option>)}</select>:<input id={`review-${f.key}`} type="number" step="any" min={f.min} max={f.max} placeholder="Not provided" value={values[f.key]||''} aria-invalid={!!fieldError(f,values[f.key],values)} aria-describedby={fieldError(f,values[f.key],values)?`review-error-${f.key}`:undefined} onChange={e=>change(f.key,e.target.value,sources[f.key]==='Extracted'||sources[f.key]==='Sample'||sources[f.key]==='Corrected'?'Corrected':'Entered')}/>} {fieldError(f,values[f.key],values)&&<small id={`review-error-${f.key}`} className="field-error">{fieldError(f,values[f.key],values)}</small>}</div><span className={`source-label source-${values[f.key]?(sources[f.key]||'Entered').toLowerCase():'missing'}`}>{values[f.key]?sources[f.key]||'Entered':'Missing'}</span></div>)}</div></section>})}
            <div className="review-actions"><button className="text-button" onClick={()=>go('inputs')}><ArrowLeft size={16}/>Back to details</button><button className="btn btn-primary" onClick={openReport} disabled={!valid}>View {exactSample?'sample ':''}report <ArrowRight size={17}/></button></div></div>
            <aside className="review-aside"><div className="eyebrow">AT A GLANCE</div><h3>Ready for a closer look?</h3><ul><li><CheckCheck size={17}/><span>{provided.length} values provided</span></li><li><FileText size={17}/><span>{files.report?files.report.name:'No report attached'}</span></li><li><Activity size={17}/><span>{files.ecg?files.ecg.name:'No ECG · clinical details only'}</span></li><li><ShieldCheck size={17}/><span>No values silently assumed</span></li></ul><div className="review-context"><Info size={18}/><p>{exactSample?'The sample report displays recorded outputs. Input assumptions were not included in the original snapshot.':'Your information is stored in this tab only. Personal model results are unavailable in this disconnected preview.'}</p></div><button className="text-button" onClick={downloadInputs} disabled={!provided.length}><ArrowDownToLine size={15}/>Save input details</button></aside></div>}
          {page==='results'&&<ReportView values={values} isSample={exactSample} waveform={waveform} sampleRate={sampleRate} onEdit={()=>go('inputs')}/>}
        </div>}

        {page==='learn'&&<section className="learn-page page-enter"><div className="eyebrow">A LITTLE CONTEXT</div><h1>Understand what<br/>you’re looking at.</h1><p className="learn-intro">Clear distinctions make research information more useful.</p><div className="learn-list">{[{icon:Heart,title:'Indices are a research summary',text:'The health and composite burden indices combine selected signals into a score out of 100. They are illustrative formulae, not probabilities of disease.'},{icon:Activity,title:'Different estimates answer different questions',text:'PREVENT estimates 10-year total cardiovascular disease (CVD). The Framingham cohort model estimates 10-year coronary heart disease (CHD), a narrower outcome. They are shown separately.'},{icon:ScanLine,title:'ECG patterns stand on their own',text:'Waveform-pattern scores are separate from clinical condition model scores. ECG-plus-clinical condition fusion is withheld. Partial-lead and scanned ECG analysis are experimental.'},{icon:ShieldCheck,title:'Uncertainty stays visible',text:'Missing information is never filled with sample values. Unavailable and Inconclusive results remain visible. Acute myocardial infarction and conduction-block decisions are inconclusive because reliability is insufficient.'},{icon:LockKeyhole,title:'A local place to explore',text:'This standalone preview does not contact any health service or model. Structured CSV and JSON reports are read in your browser. Files and details are kept only in memory and cleared when you refresh.'}].map(item=><article key={item.title}><item.icon size={25}/><div><h2>{item.title}</h2><p>{item.text}</p></div></article>)}</div><div className="learn-bottom"><p>Research &amp; Educational Simulation Only.<br/>This interface is not a medical device.</p><button className="btn btn-primary" onClick={()=>go('welcome')}>Back to workspace <ArrowRight size={17}/></button></div></section>}

        <footer className="site-footer"><span><Activity size={14}/> CARDIOSCOPE</span><p>Research &amp; Educational Simulation Only</p><span>Built with care. Read with context.</span></footer>
      </main>
    </div>

    <dialog className="app-dialog" ref={dialogRef} onCancel={e=>{e.preventDefault();setDialog(null);}} onClick={e=>{if(e.target===e.currentTarget)setDialog(null);}}><div className="dialog-content"><button className="dialog-close icon-button" aria-label="Close dialog" onClick={()=>setDialog(null)}><X size={21}/></button>{dialog==='sample'?<><span className="dialog-icon"><FlaskConical size={26}/></span><div className="eyebrow">EXPLORE WITH AN EXAMPLE</div><h2>Meet the sample profile.</h2><p>A recorded synthetic demonstration from the existing research application. It includes seven inputs and available historical model outputs.</p><div className="sample-profile"><span>46<small>years old</small></span><span>116 / 72<small>blood pressure · mmHg</small></span><span>58<small>heart rate · bpm</small></span></div><div className="notice"><Info size={18}/><span>This replaces the details in your workspace. Sample information is labeled throughout and is never a personal assessment.</span></div><button className="btn btn-primary full-width" onClick={loadSample}>Explore sample <ArrowRight size={17}/></button></>:dialog==='new'?<><span className="dialog-icon"><Plus size={26}/></span><h2>Start with a clean slate?</h2><p>This clears the current details and attached files from this local workspace.</p><div className="dialog-actions"><button className="btn btn-secondary" onClick={()=>setDialog(null)}>Keep my details</button><button className="btn btn-primary" onClick={clear}>Start fresh <ArrowRight size={16}/></button></div></>:dialog==='help'?<><span className="dialog-icon"><CircleHelp size={26}/></span><h2>A few helpful details.</h2><details open><summary>What can I do in this preview?</summary><p>Enter details, import a single-record CSV or JSON, review values, explore a recorded sample, view numeric ECG CSV data, and print a report.</p></details><details><summary>Why are model results unavailable?</summary><p>This is a separate frontend with no connected engine. It cannot analyze personal health details, extract text from PDFs or images, or calculate scenario outcomes.</p></details><details><summary>Where is my information saved?</summary><p>Only in this browser tab’s memory. No details or files are uploaded, and refreshing clears them. Use “Save input details” on the review screen to keep a local copy.</p></details><details><summary>How should I format a report?</summary><p>Use a JSON object or a CSV with one header row and one data row. Field names include age, sex, systolic_bp, diastolic_bp, total_cholesterol, hdl, glucose, and creatinine. Maximum file size: 10 MB.</p></details><button className="btn btn-primary full-width" onClick={()=>{setDialog(null);go('learn');}}>Understand the approach <ArrowRight size={16}/></button></>:null}</div></dialog>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);



