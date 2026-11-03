"""Research-only API. Untrained or unsupported outputs are represented as null."""
from __future__ import annotations
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ml_pipeline.ecg_branch import LEADS, load_ecg, load_official_founder, digitize_ecg_image, detect_lead_mode
from ml_pipeline.report_parser import parse_report
from ml_pipeline.research_score import calculate_research_score, attribute_score, action_plan
from ml_pipeline.calibration import apply_calibration, load_calibration
from ml_pipeline.mimic_adapter_inference import FusionWithAdapter, apply_adapter_calibration
from ml_pipeline.longitudinal_risk_head import predict_risk
from ml_pipeline.lead_dropout_adapter import LeadAdapter
from ml_pipeline.clinical_lifestyle_branch import engineer_record, ENGINEERED
from ml_pipeline.reliability import calibrate_ptb, validate_clinical
from ml_pipeline.signal_quality import assess_signal, preprocess_mimic
from ml_pipeline.research_heads import predict_rhythm
from ml_pipeline.evidence_report import build_evidence_report

ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(os.getenv("CVG_PROJECT_ROOT", str(ROOT if (ROOT / "models").is_dir() else ROOT.parent)))
MODELS = Path(os.getenv("CVG_MODELS_DIR", str(PROJECT_ROOT / "models")))
ICD_NAMES = {"I48": "Atrial Fibrillation & Flutter", "I50": "Heart Failure",
             "I25": "Chronic Ischemic Heart Disease (CAD)", "I21": "Acute Myocardial Infarction",
             "I44": "Atrioventricular & Left Bundle-Branch Block"}
PTB_NAMES = {"NORM": "Normal ECG", "MI": "Myocardial Infarction",
             "STTC": "ST/T-Wave Change", "CD": "Conduction Disturbance",
             "HYP": "Myocardial Hypertrophy"}
app = FastAPI(title="Cardiovascular research assessment API", version="0.1.0")
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

@lru_cache(maxsize=2)
def rhythm_head(modified):
    path=MODELS/'af_rhythm_head.joblib'
    return joblib.load(path) if path.is_file() else None


@lru_cache(maxsize=1)
def diagnostic_assets():
    import torch
    from ml_pipeline.fusion_model import FusionModel
    checkpoint = torch.load(MODELS / "best_multimodal_cvd.pt", map_location="cpu", weights_only=False)
    transform = joblib.load(MODELS / "clinical_transform.joblib")
    model = FusionModel(checkpoint["ecg_dim"], checkpoint["tab_dim"], len(checkpoint["labels"]), checkpoint["risk_head"])
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    calibration_path = MODELS / "modality_calibration.json"
    calibration = load_calibration(calibration_path, MODELS / "best_multimodal_cvd.pt") if calibration_path.is_file() else None
    return checkpoint, transform, model, calibration


@lru_cache(maxsize=1)
def ecg_encoder():
    source = MODELS / "12_lead_ECGFounder.pth"
    if not source.is_file():
        source = PROJECT_ROOT / "pretrained/ECGFounder/12_lead_ECGFounder.pth"
    if not source.is_file():
        raise FileNotFoundError("ECGFounder checkpoint is unavailable")
    return load_official_founder(source, ROOT / "ml_pipeline/vendor/ECGFounder")


@lru_cache(maxsize=2)
def _ptb_head_cached(modified_ns: int):
    import torch
    path = MODELS / "ptbxl_superclass_head.pt"
    if not path.is_file():
        return None
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    model = torch.nn.Sequential(torch.nn.Linear(checkpoint.get("input_dim", 1024), 256), torch.nn.SiLU(),
                                torch.nn.Dropout(.2), torch.nn.Linear(256, len(checkpoint["labels"])))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return checkpoint, model


def ptb_head():
    path = MODELS / "ptbxl_superclass_head.pt"
    return _ptb_head_cached(path.stat().st_mtime_ns if path.is_file() else 0)


@lru_cache(maxsize=2)
def _lead_adapter_cached(modified_ns: int):
    import torch
    path = MODELS / "lead_dropout_adapter.pt"
    if not path.is_file():
        return None
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    model = LeadAdapter()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return checkpoint, model


def lead_adapter():
    path = MODELS / "lead_dropout_adapter.pt"
    return _lead_adapter_cached(path.stat().st_mtime_ns if path.is_file() else 0)


@lru_cache(maxsize=2)
def _mimic_adapter_cached(modified_ns: int, calibration_modified_ns: int):
    import torch
    path = MODELS / "mimic_projection_adapter.pt"
    calibration_path = MODELS / "mimic_adapter_calibration.json"
    if not path.is_file() or not calibration_path.is_file():
        return None
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    calibration = json.loads(calibration_path.read_text())
    base_checkpoint, _, base, _ = diagnostic_assets()
    if tuple(checkpoint["labels"]) != tuple(base_checkpoint["labels"]):
        return None
    wrapped = FusionWithAdapter(base, base_checkpoint["ecg_dim"], base_checkpoint["tab_dim"], len(checkpoint["labels"]))
    wrapped.adapter.load_state_dict(checkpoint["state_dict"])
    wrapped.eval()
    return wrapped, calibration


def mimic_adapter():
    path = MODELS / "mimic_projection_adapter.pt"
    calibration_path = MODELS / "mimic_adapter_calibration.json"
    return _mimic_adapter_cached(path.stat().st_mtime_ns if path.is_file() else 0,
                                 calibration_path.stat().st_mtime_ns if calibration_path.is_file() else 0)


@lru_cache(maxsize=2)
def _longitudinal_head_cached(modified_ns: int):
    path = MODELS / "longitudinal_10y_head.pkl"
    return joblib.load(path) if path.is_file() else None


def longitudinal_head():
    path = MODELS / "longitudinal_10y_head.pkl"
    return _longitudinal_head_cached(path.stat().st_mtime_ns if path.is_file() else 0)


@app.get("/api/health")
def health():
    return {"status": "ok", "diagnostic_model_available": (MODELS / "best_multimodal_cvd.pt").is_file(),
            "research_score_available": os.getenv("CVG_ENABLE_RISK_OUTPUT", "1") == "1"}


@app.get("/api/training-status")
def training_status():
    path = MODELS / "slow_train_status.json"
    if not path.is_file():
        return {"phase": "not_started", "processed_records": 0,
                "total_records": 21799, "percent_complete": 0, "eta_minutes": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(503, "Training status is temporarily unavailable") from error


class SimulationRequest(BaseModel):
    clinical: dict
    changes: dict
    disease_probabilities: dict[str, float] | None = None


@app.post("/api/simulate")
def simulate(request: SimulationRequest):
    try:
        validate_clinical(request.clinical)
        validate_clinical({**request.clinical, **request.changes})
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    allowed = {"smoking_status", "systolic_bp", "bmi", "physical_activity_mins_per_week", "sleep_hours", "ldl"}
    if set(request.changes) - allowed:
        raise HTTPException(422, "Only smoking, systolic BP, BMI, activity, sleep, and LDL can be varied")
    before = calculate_research_score(request.clinical, request.disease_probabilities)
    after = calculate_research_score({**request.clinical, **request.changes}, request.disease_probabilities)
    cohort = longitudinal_head()
    before_cohort = predict_risk(cohort, request.clinical) if cohort else None
    after_cohort = predict_risk(cohort, {**request.clinical, **request.changes}) if cohort else None
    feature_deltas = {}
    for key in sorted(allowed):
        value = request.changes.get(key, request.clinical.get(key))
        if value is None:
            feature_deltas[key] = {"changed": False, "composite_index_points": None,
                                   "cohort_chd_percentage_points": None}
            continue
        single = {**request.clinical, key: value}
        single_score = calculate_research_score(single, request.disease_probabilities)
        single_cohort = predict_risk(cohort, single) if cohort else None
        feature_deltas[key] = {
            "changed": key in request.changes,
            "composite_index_points": round(single_score["cvd_risk_score"] - before["cvd_risk_score"], 3),
            "cohort_chd_percentage_points": round(single_cohort["percent"] - before_cohort["percent"], 3) if cohort else None,
        }
    return {"before": before, "after": after,
            "delta_index_points": round(after["cvd_risk_score"] - before["cvd_risk_score"], 2),
            "before_learned_cohort_10y_risk": before_cohort,
            "after_learned_cohort_10y_risk": after_cohort,
            "scenario_feature_deltas": feature_deltas,
            "disclaimer": "Research & Educational Simulation Only. This is model sensitivity, not treatment effect."}


@app.post("/api/parse-report")
async def parse_report_endpoint(report: UploadFile = File(...)):
    data = await report.read(10_000_001)
    try:
        extracted = parse_report(data, report.filename or "", report.content_type or "", include_evidence=True)
        values=extracted['values']
    except (ValueError, ImportError, OSError) as error:
        raise HTTPException(422, str(error)) from error
    import hashlib
    return {"values": values, "requires_review": True,
            "provenance": {"document_sha256": hashlib.sha256(data).hexdigest(),
                           "source_filename": Path(report.filename or '').name,
                           "extraction": "automated; review original document before confirming values",
                           "timestamp": None, "timestamp_note": "Measurement date not verified",
                           "fields": extracted['fields']}}


@app.post("/api/predict")
async def predict(clinical_json: str = Form("{}"), ecg: UploadFile | None = File(None),
                  header: UploadFile | None = File(None), sample_rate: int | None = Form(None)):
    try:
        clinical = json.loads(clinical_json)
        if not isinstance(clinical, dict):
            raise ValueError("clinical_json must be an object")
        validate_clinical(clinical)
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(422, str(error)) from error
    checkpoint_path = MODELS / "best_multimodal_cvd.pt"
    if not checkpoint_path.is_file() or not (MODELS / "clinical_transform.joblib").is_file():
        raise HTTPException(503, "Diagnostic model is not trained. Run ml_pipeline.train first.")
    import torch
    checkpoint, transform, model, calibration = diagnostic_assets()
    waveform = None
    waveform_quality = None
    lead_mode = None
    lead_mode_confidence = None
    superclass_probabilities = None
    ptb_calibration = None
    input_quality = None
    mimic_waveform = None
    mimic_embedding_raw = None
    rhythm_result = None
    embedding = np.zeros((1, checkpoint["ecg_dim"]), np.float32)
    if ecg is not None:
        if (ecg.size or 0) > 10_000_000:
            raise HTTPException(413, "ECG file exceeds 10 MB")
        suffix = Path(ecg.filename or "").suffix.lower()
        if suffix not in {".csv", ".npy", ".dat", ".hea", ".png", ".jpg", ".jpeg"}:
            raise HTTPException(422, "Supported ECG formats: WFDB, CSV, NPY, PNG, JPG")
        if suffix in {".dat", ".hea"} and header is None:
            raise HTTPException(422, "WFDB requires both .dat and .hea files")
        with tempfile.TemporaryDirectory() as temporary:
            stem = Path(ecg.filename or "record").stem
            destination = Path(temporary) / (stem + suffix)
            destination.write_bytes(await ecg.read(10_000_001))
            if header is not None:
                other_suffix = ".hea" if suffix == ".dat" else ".dat"
                if Path(header.filename or "").stem != stem:
                    raise HTTPException(422, "WFDB .dat and .hea filenames must share a stem")
                (Path(temporary) / (stem + other_suffix)).write_bytes(await header.read(10_000_001))
            try:
                if suffix in {".png", ".jpg", ".jpeg"}:
                    waveform, waveform_quality = digitize_ecg_image(destination)
                else:
                    def checked_processor(signal, fs, names):
                        nonlocal input_quality
                        from ml_pipeline.ecg_branch import preprocess
                        input_quality=assess_signal(signal,fs,names)
                        return preprocess(signal,fs,names)
                    waveform = load_ecg(destination, sample_rate, processor=checked_processor)
                lead_mode = detect_lead_mode(waveform)
                if suffix not in {'.png','.jpg','.jpeg'} and lead_mode['mode']=='12-lead' and not input_quality['warnings']:
                    mimic_waveform=load_ecg(destination,sample_rate,processor=preprocess_mimic)
            except (ValueError, ImportError, OSError) as error:
                raise HTTPException(422, str(error)) from error
        try:
            encoder = ecg_encoder()
        except FileNotFoundError as error:
            raise HTTPException(503, str(error)) from error
        with torch.no_grad():
            _, features = encoder(torch.from_numpy(waveform[None]))
        embedding = features.numpy()
        if mimic_waveform is not None:
            with torch.inference_mode():
                _,mimic_features=encoder(torch.from_numpy(mimic_waveform[None]))
            mimic_embedding_raw=mimic_features.numpy()
        rhythm_path=MODELS/'af_rhythm_head.joblib'
        if lead_mode['mode']=='12-lead' and waveform_quality is None and not input_quality['warnings'] and rhythm_path.is_file():
            bundle=rhythm_head(rhythm_path.stat().st_mtime_ns)
            probability=float(predict_rhythm(bundle,embedding)[0])
            rhythm_result={'target':'AFIB rhythm annotation','probability':probability,
                           'threshold':bundle['threshold'],'above_review_marker':probability>=bundle['threshold'],
                           'scope':'Internal PTB digital 12-lead research; no external clinical validation',
                           'test_metrics':bundle['metrics']['test']}
        head = ptb_head()
        if lead_mode and lead_mode["mode"] != "12-lead":
            active_lead_adapter = lead_adapter()
            mode_metrics = (active_lead_adapter[0].get("metrics", {}).get(lead_mode["mode"])
                            if active_lead_adapter else None)
            lead_mode_confidence = {"level": "experimental", "held_out_macro_auroc": mode_metrics.get("test_auroc_adapted") if mode_metrics else None,
                                    "held_out_records": mode_metrics.get("test_rows") if mode_metrics else None,
                                    "note": "Population-level research metric, not confidence in this individual result."}
            if active_lead_adapter and mode_metrics and mode_metrics.get("use_adapter") and head:
                ptb_checkpoint = head[0]
                normalized = (embedding - ptb_checkpoint["mean"]) / ptb_checkpoint["scale"]
                lead_mask = np.asarray(lead_mode["lead_mask"], np.float32)[None]
                with torch.no_grad():
                    corrected = active_lead_adapter[1](torch.from_numpy(normalized.astype(np.float32)),
                                                       torch.from_numpy(lead_mask)).numpy()
                embedding = corrected * ptb_checkpoint["scale"] + ptb_checkpoint["mean"]
        elif lead_mode:
            lead_mode_confidence = {"level": "standard 12-lead research input",
                                    "held_out_macro_auroc": None, "held_out_records": None,
                                    "note": "Model scores remain research outputs, not clinical confidence."}
        if head is not None:
            ptb_checkpoint, ptb_model = head
            normalized = (embedding - ptb_checkpoint["mean"]) / ptb_checkpoint["scale"]
            if ptb_checkpoint.get("input_dim") == 1026:
                age = clinical.get("age")
                try:
                    age = float(age) if age is not None else float(ptb_checkpoint["age_median"])
                except (TypeError, ValueError):
                    age = float(ptb_checkpoint["age_median"])
                sex = clinical.get("sex")
                sex_value = 1.0 if str(sex).lower() in {"female", "f", "1"} else 0.0 if sex is not None else 0.5
                normalized = np.concatenate((normalized, np.array([[(age - 55) / 20, sex_value]], np.float32)), axis=1)
            with torch.no_grad():
                ptb_logits = ptb_model(torch.from_numpy(normalized.astype(np.float32)))[0].numpy()
            if lead_mode['mode'] == '12-lead' and waveform_quality is None and not input_quality['warnings']:
                ptb_values, ptb_calibration = calibrate_ptb(ptb_logits, MODELS)
            else:
                ptb_values = 1 / (1 + np.exp(-np.clip(ptb_logits, -50, 50)))
            superclass_probabilities = dict(zip(ptb_checkpoint["labels"], (float(x) for x in ptb_values)))
    mimic_use_ecg = mimic_embedding_raw is not None
    mimic_embedding = mimic_embedding_raw if mimic_use_ecg else np.zeros_like(embedding)
    trained_fields = checkpoint.get("trained_clinical_fields", ("age", "sex", "creatinine", "fasting_blood_sugar") if checkpoint.get("source") == "MIMIC cached ECGFounder" else tuple(clinical))
    diagnostic_clinical = {key: clinical[key] for key in trained_fields if key in clinical}
    # MIMIC training used the most recent lab glucose, which need not be fasting.
    # Preserve that distinction in the report/UI while mapping it to the
    # historical transform column name used by this checkpoint.
    if "fasting_blood_sugar" in trained_fields and "fasting_blood_sugar" not in diagnostic_clinical and "glucose" in clinical:
        diagnostic_clinical["fasting_blood_sugar"] = clinical["glucose"]
    tab = transform.transform([diagnostic_clinical])
    with torch.no_grad():
        logits, risk_logits = model(torch.from_numpy(mimic_embedding), torch.from_numpy(tab),
                                    torch.tensor([[float(mimic_use_ecg)]]), torch.ones(1, 1))
    modality = "ecg_clinical" if mimic_use_ecg else "clinical_only"
    active_adapter = mimic_adapter()
    if active_adapter:
        adapter_model, adapter_calibration = active_adapter
        with torch.no_grad():
            adapted_logits, _ = adapter_model(torch.from_numpy(mimic_embedding), torch.from_numpy(tab),
                                              torch.tensor([[float(mimic_use_ecg)]]), torch.ones(1, 1))
        rules = adapter_calibration["modalities"][modality]
        probabilities = apply_adapter_calibration(adapted_logits.numpy(), rules)[0]
        thresholds = adapter_calibration["thresholds"][modality]
        decisions = probabilities >= np.asarray(thresholds)
        decision_scores = 1 / (1 + np.exp(-(np.log(np.clip(probabilities, 1e-7, 1 - 1e-7) /
                                                 np.clip(1 - probabilities, 1e-7, 1)) -
                                          np.log(np.asarray(thresholds) / (1 - np.asarray(thresholds))))))
    elif calibration:
        probabilities, decision_scores, decisions = apply_calibration(logits.numpy(), calibration, modality)
        thresholds = calibration["modalities"][modality]["thresholds"]
        probabilities, decision_scores, decisions = probabilities[0], decision_scores[0], decisions[0]
    else:
        probabilities = torch.sigmoid(logits)[0].numpy()
        decision_scores, decisions = probabilities, probabilities >= .5
        thresholds = [.5] * len(probabilities)
    disease_probabilities = dict(zip(checkpoint["labels"], (float(x) for x in probabilities)))
    disease_decision_scores = dict(zip(checkpoint["labels"], (float(x) for x in decision_scores)))
    disease_flags = dict(zip(checkpoint["labels"], (bool(x) for x in decisions)))
    has_demographics = clinical.get("age") not in (None, "") and str(clinical.get("sex", "")).lower() in {"male", "female"}
    has_labs = any(clinical.get(key) not in (None, "") for key in ("creatinine", "glucose", "fasting_blood_sugar"))
    abstained_codes = {"I21", "I44"} if mimic_use_ecg or (has_demographics and has_labs) else set(checkpoint["labels"])
    score = calculate_research_score(clinical, disease_probabilities)
    cohort = longitudinal_head()
    cohort_risk = predict_risk(cohort, clinical) if cohort else None
    engineered = engineer_record(clinical)
    ratios = {key: round(float(engineered[key]), 3) if np.isfinite(engineered[key]) else None
              for key in ENGINEERED}
    icd_index = 100 * max(disease_probabilities.values()) if disease_probabilities else 0.0
    ptb_abnormal = [value for key, value in (superclass_probabilities or {}).items() if key != "NORM"]
    diagnostic_index = round((icd_index + 100 * max(ptb_abnormal)) / 2, 1) if ptb_abnormal else round(icd_index, 1)
    if os.getenv("CVG_ENABLE_RISK_OUTPUT", "1") != "1":
        score["cvd_risk_score"] = None
        score["health_score"] = None
    tier = ("Lower research index" if score["health_score"] >= 80 else "Midrange research index" if score["health_score"] >= 50 else "Higher research index") if score["health_score"] is not None else None
    return {**score, "risk_tier": tier,
            "prevent_10y_risk": score["prevent_10y_cvd_percent"],
            "learned_cohort_10y_risk": cohort_risk["percent"] if cohort_risk else None,
            "learned_cohort_10y_quality": cohort_risk,
            "multimodal_diagnostic_index": diagnostic_index,
            "engineered_clinical_ratios": ratios,
            "lead_mode": lead_mode,
            "lead_mode_confidence": lead_mode_confidence,
            "input_quality": input_quality,
            "rhythm_assessment": rhythm_result,
            "evidence_report": build_evidence_report(clinical,modality,input_quality,rhythm_result,disease_probabilities),
            "ecg_probability_calibration": ptb_calibration,
            "reliability": {"icd_waveform_fusion": "verified_dedicated_mimic_preprocessing" if mimic_use_ecg else "clinical_only_fallback",
                            "clinical_only": "limited discrimination; weak classes abstain",
                            "ecg_patterns": "calibrated research scores" if ptb_calibration else "experimental uncalibrated scores",
                            "health_index": "heuristic; no outcome validation"},
            "disease_probabilities": disease_probabilities,
            "disease_decision_scores": disease_decision_scores,
            "disease_flags": {code: None if code in abstained_codes else flag for code, flag in disease_flags.items()},
            "disease_thresholds": dict(zip(checkpoint["labels"], (float(x) for x in thresholds))),
            "diagnostic_modality": modality,
            "clinical_icd_conditions": {code: {"name": ICD_NAMES.get(code, code), "probability": probability,
                                               "threshold": float(thresholds[i]), "flag": None if code in abstained_codes else disease_flags[code],
                                               "assessment": "inconclusive" if code in abstained_codes else "limited_research_estimate",
                                               "reliability_note": ("Insufficient reliability for a positive or negative diagnostic decision." if mimic_use_ecg or (has_demographics and has_labs) else "Required demographic or trained laboratory inputs are missing; no condition decision is made.") if code in abstained_codes else "Research estimate of a recorded diagnosis group; a low score cannot exclude disease.",
                                               "decision_score": disease_decision_scores[code]}
                                        for i, (code, probability) in enumerate(disease_probabilities.items())},
            "ecg_superclass_probabilities": superclass_probabilities,
            "ecg_superclasses": {code: {"name": PTB_NAMES[code], "probability": probability,
                                         "threshold": ptb_calibration['thresholds'][code] if ptb_calibration else .5}
                                   for code, probability in superclass_probabilities.items()} if superclass_probabilities else None,
            "waveform": {lead: waveform[i, ::25].round(3).tolist() for i, lead in enumerate(LEADS)} if waveform is not None else None,
            "waveform_quality": waveform_quality,
            "feature_attribution": attribute_score(clinical, disease_probabilities),
            "action_plan": action_plan(clinical, disease_probabilities),
            "modality_warning": "Dedicated verified ECG preprocessing used for ICD estimates." if mimic_use_ecg else "Clinical-only ICD fallback: partial leads, scans, signal warnings, or absent ECG cannot use verified MIMIC waveform fusion. Low scores cannot exclude disease.",
            "disclaimer": "Research & Educational Simulation Only",
            "limitations": "Composite index is uncalibrated and is not a CVD event probability. Diagnostic probabilities are research outputs. Scenario changes are not causal treatment effects."}
