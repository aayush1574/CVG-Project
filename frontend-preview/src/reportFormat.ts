export type Condition = {name:string; probability:number; threshold:number; flag:boolean|null; decision_score:number; assessment?:string; reliability_note?:string};
export type Superclass = {name:string; probability:number; threshold?:number};
export type ReportResult = {
  health_score:number|null; cvd_risk_score:number|null; risk_tier?:string|null;
  prevent_10y_cvd_percent:number|null;
  prevent_quality?:{confidence:string; imputed_fields:string[]; clamped_fields?:string[]; complete?:boolean}|null;
  components?:Record<string,number|null>;
  prevent_10y_risk?:number|null;
  learned_cohort_10y_risk?:number|null;
  learned_cohort_10y_quality?:{outcome:string;input_quality:string;missing_fields:string[]}|null;
  multimodal_diagnostic_index?:number|null;
  engineered_clinical_ratios?:Record<string,number|null>;
  lead_mode?:{mode:string;active_leads:string[];lead_mask:number[]}|null;
  lead_mode_confidence?:{level:string;held_out_macro_auroc:number|null;held_out_records:number|null;note:string}|null;
  clinical_icd_conditions?:Record<string,Condition>;
  ecg_superclasses?:Record<string,Superclass>|null;
  diagnostic_modality?:string;
  modality_warning?:string|null;
  feature_attribution?:{feature:string; score_points_vs_reference:number; direction:string}[];
  action_plan?:{topic:string; observation:string; suggestion:string}[];
  limitations?:string;
  reliability?:Record<string,string>;
  ecg_probability_calibration?:{method:string;thresholds:Record<string,number>;note:string}|null;
  input_quality?:{status:string;warnings:string[];duration_seconds:number;sample_rate_hz:number}|null;
  rhythm_assessment?:{probability:number;threshold:number;above_review_marker:boolean;test_metrics:{precision:number;recall:number;auroc:number}}|null;
  evidence_report?:{generated_at:string;summary:{title:string;text:string}[];measurements:{field:string;value:number;unit:string;source:string}[];discussion_prompt:string};
};
export const conditionNotes:Record<string,string>={
  I48:'Atrial fibrillation and flutter are irregular heart rhythm diagnosis groups.',
  I50:'Heart failure is a diagnosis group related to the heart’s pumping or filling function.',
  I25:'Chronic ischemic heart disease is a diagnosis group associated with reduced blood flow to the heart.',
  I21:'Acute myocardial infarction is the diagnosis group for a heart attack.',
  I44:'Atrioventricular and left bundle branch block are electrical conduction diagnosis groups.',
};
export const ecgNotes:Record<string,string>={
  NORM:'A waveform pattern labeled normal in the PTB-XL research data.',
  MI:'A waveform pattern associated with myocardial infarction labels.',
  STTC:'A waveform pattern with ST segment or T wave changes.',
  CD:'A waveform pattern with conduction disturbance labels.',
  HYP:'A waveform pattern with hypertrophy labels.',
};
export const fieldLabels:Record<string,string>={
  age:'Age',sex:'Sex',bmi:'Body mass index',systolic_bp:'Systolic blood pressure',diastolic_bp:'Diastolic blood pressure',
  resting_hr:'Resting heart rate',total_cholesterol:'Total cholesterol',hdl:'HDL cholesterol',ldl:'LDL cholesterol',
  triglycerides:'Triglycerides',glucose:'Glucose',fasting_blood_sugar:'Fasting glucose',hba1c:'HbA1c',
  creatinine:'Creatinine',egfr:'Estimated kidney function',troponin:'Troponin',smoking_status:'Smoking status',
  packs_per_day:'Packs per day',alcohol_intake:'Alcohol per week',physical_activity_mins_per_week:'Activity minutes per week',
  diet_quality_score:'Diet quality',sleep_hours:'Sleep hours',stress_level:'Stress level',family_history_cvd:'Family history of cardiovascular disease',
  diabetes_status:'Diabetes status',hypertension_meds:'Blood pressure medication',statin_use:'Statin use',
  sex_male:'Sex',current_smoker:'Smoking status',bp_meds:'Blood pressure medication',
  pulse_pressure:'Pulse pressure',mean_arterial_pressure:'Mean arterial pressure',
  non_hdl_cholesterol:'Non-HDL cholesterol',tg_to_hdl_ratio:'Triglycerides / HDL ratio',
  chol_to_hdl_ratio:'Total cholesterol / HDL ratio',tyg_index:'TyG index',
  egfr_ckd_epi_2021:'Estimated kidney function',age_x_systolic_bp:'Age × systolic BP',
  bmi_x_hba1c:'BMI × HbA1c',
};
export const friendlyField=(key:string)=>fieldLabels[key]||key.replace(/_/g,' ');
export const percent=(value:number)=>`${(value*100).toFixed(1)}%`;
export const score=(value:number|null|undefined)=>value==null?'Unavailable':`${Number(value).toFixed(1)} / 100`;
