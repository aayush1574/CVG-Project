import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Activity, ArrowDown, ArrowRight, Check, ChevronDown, ChevronLeft, ChevronRight, ClipboardCheck, Expand, Heart, Leaf, Pause, Play, ShieldCheck, Sparkles, Upload, X } from 'lucide-react';
import ContourField, { type ContourFieldHandle } from './ContourField';
import useWorkflowInteraction from './useWorkflowInteraction';
import useScrollMotion from './useScrollMotion';
import type { MotionPreference } from './useMotionPreference';
import './welcome-motion.css';

type Props = { demos: ReactNode; motion: MotionPreference; hasDetails: boolean; onStart: () => void; onSample: () => void; onLearn: () => void };
type Scene = 'motion' | 'care' | 'calm';
const chapters = [
  { title:'Bring your details', eyebrow:'01 / ADD WHAT YOU KNOW', heading:'Start with the pieces you have.', body:'A report, an ECG, or a few details entered by hand. You don’t need to have everything to get started.', icon:Upload, action:'Add your details', labels:['Health details','Lab measurements','Optional ECG'] },
  { title:'Make it yours', eyebrow:'02 / REVIEW WITH CARE', heading:'Every detail deserves a second look.', body:'See where each value came from, make a correction, and leave anything unknown as “Not provided.”', icon:ClipboardCheck, action:'Explore the sample review', labels:['See the source','Correct a value','Keep missing values visible'] },
  { title:'Explore the picture', eyebrow:'03 / UNDERSTAND THE CONTEXT', heading:'More understanding. Less guesswork.', body:'Explore clearly separated research measures, their limitations, and what the available information can tell you.', icon:Activity, action:'See a sample report journey', labels:['Research indices','Separate model outputs','Clear limitations'] },
];
const perspectives = [
  { key:'movement', name:'Movement', image:'/images/movement.jpg', alt:'People spending time outdoors in a green park', eyebrow:'THE EVERYDAY DETAILS', heading:'There’s a life behind every number.', text:'Activity is one part of the lifestyle information you can add. Start with what you know about a usual week.', detail:'Optional input · Minutes of activity per week', icon:Leaf },
  { key:'rest', name:'Rest & recovery', image:'/images/calm.jpg', alt:'A calm outdoor scene in soft natural light', eyebrow:'ROOM FOR THE WHOLE PICTURE', heading:'Make room for the quieter details.', text:'Sleep and perceived stress can sit alongside your measurements. You can leave either one blank.', detail:'Optional inputs · Sleep and stress', icon:Heart },
  { key:'conversation', name:'Conversation', image:'/images/care.jpg', alt:'A doctor reviewing information with a patient', eyebrow:'INFORMATION WITH PERSPECTIVE', heading:'A starting point for a conversation.', text:'Keep your details together, explore the context, and save a report to discuss with a qualified clinician.', detail:'Research & education · Not a diagnosis', icon:ClipboardCheck },
];

function useInView<T extends HTMLElement>(ref:RefObject<T>, margin='120px') {
  const [visible,setVisible]=useState(false);
  useEffect(()=>{const element=ref.current;if(!element)return;const observer=new IntersectionObserver(([entry])=>setVisible(entry.isIntersecting),{rootMargin:margin});observer.observe(element);return()=>observer.disconnect();},[ref,margin]);
  return visible;
}

function AmbientVideo({src,poster,enabled,className,onPlayback}:{src:string;poster:string;enabled:boolean;className?:string;onPlayback?:(playing:boolean)=>void}) {
  const ref=useRef<HTMLVideoElement>(null);
  const visible=useInView(ref,'0px');
  const [load,setLoad]=useState(false);
  const [failed,setFailed]=useState(false);
  const [hasFrame,setHasFrame]=useState(false);
  useEffect(()=>{if(enabled&&visible)setLoad(true);},[enabled,visible]);
  useEffect(()=>{
    const video=ref.current;if(!video||!load||failed)return;
    const sync=()=>{if(enabled&&visible&&!document.hidden){void video.play().catch(()=>{onPlayback?.(false);});}else video.pause();};
    sync();document.addEventListener('visibilitychange',sync);return()=>{document.removeEventListener('visibilitychange',sync);video.pause();};
  },[enabled,visible,load,failed]);
  return <div className={`wm-ambient ${className||''} ${hasFrame&&!failed?'has-frame':''}`}>
    <img src={poster} alt="" aria-hidden="true" className="wm-video-poster"/>
    <video ref={ref} src={load&&!failed?src:undefined} poster={poster} muted loop playsInline preload="none" aria-hidden="true" tabIndex={-1} onPlaying={()=>{setHasFrame(true);onPlayback?.(true);}} onPause={()=>onPlayback?.(false)} onError={()=>{setFailed(true);onPlayback?.(false);}}/>
  </div>;
}

export default function WelcomeExperience({demos,motion,hasDetails,onStart,onSample,onLearn}:Props){
  const { enabled: motionEnabled, paused, reduced, saveData } = motion;
  const [scene,setScene]=useState<Scene>('motion');
  const [playing,setPlaying]=useState(false);
  const [perspective,setPerspective]=useState(0);
  const [guide,setGuide]=useState(false);
  const [expandedPhoto,setExpandedPhoto]=useState(false);
  const rootRef=useRef<HTMLDivElement>(null);
  const workflowRef=useRef<HTMLElement>(null);
  const contourRef=useRef<ContourFieldHandle>(null);
  const workflow=useWorkflowInteraction(workflowRef, contourRef, motionEnabled);
  const chapter=workflow.state.selected;
  const setChapter=workflow.select;
  const photoDialog=useRef<HTMLDialogElement>(null);
  const photoTrigger=useRef<HTMLButtonElement>(null);
  const chapterRefs=useRef<(HTMLButtonElement|null)[]>([]);
  const perspectiveRefs=useRef<(HTMLButtonElement|null)[]>([]);
  useScrollMotion(rootRef, motionEnabled);
  const active=chapters[chapter];
  const photo=perspectives[perspective];
  useEffect(()=>{
    const elements=rootRef.current?.querySelectorAll('.wm-reveal');
    const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('wm-revealed');observer.unobserve(entry.target);}}),{threshold:.1});
    elements?.forEach(el=>observer.observe(el));return()=>observer.disconnect();
  },[]);
  useEffect(()=>{if(expandedPhoto)photoDialog.current?.showModal();else{photoDialog.current?.close();}},[expandedPhoto]);
  function closePhoto(){setExpandedPhoto(false);photoTrigger.current?.focus();}
  function moveTab(event:React.KeyboardEvent,index:number,select:(i:number)=>void,refs:React.MutableRefObject<(HTMLButtonElement|null)[]>){let next=index;if(event.key==='ArrowRight')next=(index+1)%3;else if(event.key==='ArrowLeft')next=(index+2)%3;else if(event.key==='Home')next=0;else if(event.key==='End')next=2;else return;event.preventDefault();select(next);refs.current[next]?.focus();}

  return <div className={`welcome wm-welcome ${motionEnabled?'wm-motion-on':'wm-motion-off'}`} ref={rootRef} data-motion={motionEnabled?'on':'off'}>
    <div className="wm-scroll-track" aria-hidden="true"><div/></div>
    <section className="welcome-hero wm-hero" aria-labelledby="welcome-title">
      <div className="hero-photo wm-hero-media">
        <div className={`wm-scene ${scene==='motion'?'is-active':''}`} aria-hidden={scene!=='motion'}><AmbientVideo src="/media/wellbeing.mp4" poster="/media/wellbeing-poster.jpg" enabled={motionEnabled&&scene==='motion'} onPlayback={setPlaying}/></div>
        <img className={`wm-scene wm-still ${scene==='care'?'is-active':''}`} src="/images/care.jpg" alt="" aria-hidden="true"/>
        <img className={`wm-scene wm-still ${scene==='calm'?'is-active':''}`} src="/images/calm.jpg" alt="" aria-hidden="true"/>
      </div>
      <div className="wm-hero-shade"/>
      <div className="wm-hero-top"><span><span className="wm-live-dot"/>{scene==='motion'?(playing?'A MOMENT IN MOTION':'A MOMENT OUTDOORS'):scene==='care'?'A MOMENT OF CONNECTION':'A MOMENT OF CALM'}</span><button className="wm-motion-control" disabled={reduced||saveData} onClick={motion.toggle} aria-label={reduced?'Reduced motion enabled':saveData?'Data saving enabled':paused?'Play motion':'Pause motion'} aria-pressed={paused}>{reduced||saveData||paused?<Play size={13}/>:<Pause size={13}/>}<span>{reduced?'Reduced motion':saveData?'Data saver':paused?'Play motion':'Pause motion'}</span></button></div>
      <div className="hero-copy wm-hero-copy"><div className="eyebrow"><span className="tiny-line"/> YOUR HEALTH. A LITTLE MORE CLARITY.</div><h1 id="welcome-title" aria-label="CardioScope. Your heart, in focus."><b className="wm-brand-word" aria-hidden="true">CardioScope</b><span className="wm-tagline" aria-hidden="true"><i className="wm-line-mask"><em className="wm-kinetic-line">Your heart,</em></i><i className="wm-line-mask"><em className="wm-kinetic-line">in focus.</em></i></span></h1><p>Bring your health details together.<br/>Make space for a clearer perspective.</p><div className="hero-actions"><button className="btn btn-primary" onClick={onStart}>{hasDetails?'Continue assessment':'Start assessment'}<ArrowRight size={17}/></button><button className="text-button" onClick={onSample}><span className="wm-sample-play"><Play size={12} fill="currentColor"/></span>Try a sample</button></div><div className="hero-footnote"><ShieldCheck size={15}/><span>Research &amp; education. Always with context.</span></div></div>
      <div className="wm-hero-bottom"><div className="wm-scene-choices" role="group" aria-label="Background scene">{([{key:'motion',name:'In motion',sub:'01'},{key:'care',name:'In conversation',sub:'02'},{key:'calm',name:'At ease',sub:'03'}] as const).map(item=><button key={item.key} onClick={()=>setScene(item.key)} aria-pressed={scene===item.key}><span>{item.sub}</span>{item.name}<i/></button>)}</div><button className="wm-discover" onClick={()=>workflowRef.current?.scrollIntoView({behavior:motionEnabled?'smooth':'instant',block:'start'})}>Explore the experience<ArrowDown size={17}/></button></div>
    </section>

    <section className="wm-workflow wm-reveal" ref={workflowRef} {...workflow.bindings} data-interaction-state={workflow.state.phase} aria-labelledby="wm-workflow-title"><div className="wm-contour-frame"><ContourField ref={contourRef} enabled={motionEnabled} chapter={chapter} phase={workflow.state.phase} onSettled={workflow.settled}/></div><div className="wm-section-header"><div><p className="eyebrow">MADE SIMPLE, STEP BY STEP</p><h2 id="wm-workflow-title"><span className="wm-heading-word">From details</span>{' '}<span className="wm-heading-word">to understanding.</span></h2></div><span className="wm-section-aside">CLICK A STEP. TAKE A CLOSER LOOK.</span></div>
      <div className="wm-chapter-tabs" style={{'--selected-index':chapter} as React.CSSProperties} role="tablist" aria-label="Explore the assessment process">{chapters.map((item,i)=><button key={item.title} ref={el=>{chapterRefs.current[i]=el;}} role="tab" id={`wm-chapter-${i}`} aria-controls={`wm-stage-${i}`} aria-selected={chapter===i} tabIndex={chapter===i?0:-1} onClick={()=>setChapter(i)} onKeyDown={e=>moveTab(e,i,setChapter,chapterRefs)}><span className="wm-chapter-number">0{i+1}</span><item.icon size={18}/><span>{item.title}</span><ArrowRight className="wm-tab-arrow" size={16}/></button>)}<i className="wm-tab-rail" aria-hidden="true"/></div>
      <div className="wm-workflow-body">
        <div className="wm-chapter-panel" role="tabpanel" id={`wm-stage-${chapter}`} aria-labelledby={`wm-chapter-${chapter}`} key={chapter}>
          <div className="wm-chapter-copy"><p className="eyebrow">{active.eyebrow}</p><h3>{active.heading}</h3><p className="wm-chapter-description">{active.body}</p></div>
          <div className="wm-chapter-details"><ul>{active.labels.map((label,i)=><li key={label} style={{'--item':i} as React.CSSProperties}><span><Check size={12}/></span>{label}</li>)}</ul><button className="text-button" onClick={chapter===0?onStart:onSample}>{active.action}<ArrowRight size={16}/></button></div>
        </div>
      </div>
    </section>

    <section className="wm-perspectives wm-reveal" aria-labelledby="wm-perspectives-title"><div className="wm-section-header"><div><p className="eyebrow">MORE THAN MEASUREMENTS</p><h2 id="wm-perspectives-title"><span className="wm-heading-word">A fuller picture</span>{' '}<span className="wm-heading-word">of you.</span></h2></div><div className="wm-perspective-tabs" role="tablist" aria-label="Explore everyday context">{perspectives.map((item,i)=><button key={item.key} ref={el=>{perspectiveRefs.current[i]=el;}} id={`wm-context-tab-${i}`} aria-controls={`wm-context-panel-${i}`} role="tab" aria-selected={perspective===i} tabIndex={perspective===i?0:-1} onClick={()=>setPerspective(i)} onKeyDown={e=>moveTab(e,i,setPerspective,perspectiveRefs)}>{item.name}</button>)}</div></div>
      <div className="wm-perspective-feature" role="tabpanel" id={`wm-context-panel-${perspective}`} aria-labelledby={`wm-context-tab-${perspective}`}><div className="wm-perspective-image"><img key={photo.image} src={photo.image} alt={photo.alt} loading="lazy" width="1200" height="800"/><div className="wm-image-corner"><span>0{perspective+1} / EVERYDAY PERSPECTIVES</span><button ref={photoTrigger} onClick={()=>setExpandedPhoto(true)} aria-label={`Enlarge ${photo.name.toLowerCase()} photograph`}><Expand size={16}/></button></div></div><div className="wm-perspective-copy" key={photo.key}><photo.icon size={25} strokeWidth={1.3}/><p className="eyebrow">{photo.eyebrow}</p><h3>{photo.heading}</h3><p>{photo.text}</p><small>{photo.detail}</small><button className="text-button" onClick={perspective===2?onLearn:onStart}>{perspective===2?'Understand the approach':'Add your details'}<ArrowRight size={16}/></button><div className="wm-photo-pagination"><button aria-label="Previous perspective" onClick={()=>setPerspective((perspective+2)%3)}><ChevronLeft size={18}/></button><span>0{perspective+1}<i>/</i>03</span><button aria-label="Next perspective" onClick={()=>setPerspective((perspective+1)%3)}><ChevronRight size={18}/></button></div></div></div>
    </section>

    {demos}
    <section className={`demo-guide wm-demo wm-reveal ${guide?'expanded':''}`}><button className="guide-toggle" aria-expanded={guide} aria-controls="demo-guide-content" onClick={()=>setGuide(!guide)}><span className="guide-icon"><Sparkles size={20}/></span><span><strong>Take a look around first.</strong><small>Interactive Demo Guide · No personal details needed</small></span><span className="guide-action">Explore the guide<ChevronDown size={17}/></span></button>{guide&&<div id="demo-guide-content" className="guide-content"><div><span>01</span><h3>Meet the sample</h3><p>A synthetic profile with seven recorded inputs. Nothing here belongs to you.</p></div><div><span>02</span><h3>Open the report</h3><p>Explore recorded research outputs. Missing results stay unavailable.</p></div><div><span>03</span><h3>Try the controls</h3><p>Review values, explore inputs, and save a printable report.</p></div><button className="btn btn-primary" onClick={onSample}>Open sample<ArrowRight size={16}/></button></div>}</section>
    <section className="context-strip wm-context"><div className="context-line-art" aria-hidden="true"><Heart size={38} strokeWidth={1.1}/></div><div><h3>Your health is more than a number.</h3><p>These research tools help you explore information. They don’t diagnose a condition or replace a conversation with your clinician.</p></div><button className="text-button" onClick={onLearn}>Understand the approach<ArrowRight size={16}/></button></section>
    <dialog ref={photoDialog} className="wm-lightbox" aria-label={`${photo.name} photograph`} onCancel={e=>{e.preventDefault();closePhoto();}} onClick={e=>{if(e.target===e.currentTarget)closePhoto();}}><button className="wm-lightbox-close" aria-label="Close photograph" onClick={closePhoto}><X size={22}/></button><figure><img src={photo.image} alt={photo.alt}/><figcaption>{photo.name}<span>Everyday perspectives · CardioScope</span></figcaption></figure></dialog>
  </div>;
}
