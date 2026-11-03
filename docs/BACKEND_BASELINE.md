# CardioScope research workspace

CardioScope is a research and educational simulation. It is not validated for diagnosis, patient care, or individual 10-year CVD prediction. The composite health index is heuristic; the separate AHA PREVENT estimate reports input completeness.

## Frozen training results

The final low-priority run processed **all 21,837 PTB-XL 500 Hz records with zero extraction failures**. The cache contains 20,413 records with one or more mapped five-superclass diagnostic labels. The separate ECGFounder superclass head uses official PTB-XL folds 1–8 for training, fold 9 for validation, and fold 10 for test. On 2,055 labeled fold-10 ECGs, macro AUROC was **0.92199** and macro F1 at 0.5 was **0.72640**. The five outputs are `NORM`, `MI`, `STTC`, `CD`, and `HYP`.

The MIMIC projection adapter uses 24,000 aligned ECGFounder and clinical records for five ICD conditions (`I48`, `I50`, `I25`, `I21`, `I44`). On its internal 2,000-row test set, ECG + clinical macro AUROC was **0.85852** and macro F1 at 0.5 was **0.39561**; clinical-only macro AUROC was **0.71319** and macro F1 at 0.5 was **0.13361**. Class calibrators were retained only when held-out validation Brier score and ECE both strictly improved over raw probabilities. The complete frozen metrics, including earlier baseline results, are in `D:\CVG Project\models\research_metrics.json`. These are internal results, not external or prospective validation.

## Local use

Use Python 3.11. On Windows, run `setup_windows.bat` if the virtual environment has not been created. Then start the API:

```powershell
.venv\Scripts\python -m uvicorn app.backend.main:app --port 8000
```

For the frontend:

```powershell
cd app/frontend
npm install
npm run dev
```

`GET /api/training-status` reads the persisted trainer status. `POST /api/predict` accepts clinical values alone or with a 12-, 6-, or lead-I WFDB/CSV/NPY waveform, or experimental 3×4 ECG scan. `POST /api/parse-report` extracts reviewable lab values from PDF, image, CSV, or JSON. `POST /api/simulate` computes research scenario deltas. The three UI sample profiles are synthetic; the sample PTB-XL ECG belongs to a different de-identified person than the illustrative clinical values.

## V2 research additions

The versioned clinical preprocessor computes pulse pressure, mean arterial pressure, non-HDL cholesterol, TG/HDL and total/HDL ratios, TyG, CKD-EPI 2021 eGFR, and age/BP and BMI/HbA1c interactions from supplied values. Missing source measurements remain missing before train-fitted imputation. The 24,000-row MIMIC training table has age, sex, creatinine, and glucose for the served condition model, but lacks the BP and lipid measurements needed to train most of these ratios. A five-label HistGradientBoosting stack was trained on observed fields; validation selected a 0.0 tree blend. Its test clinical-only macro AUROC was 0.71319, below the earlier 0.71977 baseline, so it was **not promoted**.

The public [Framingham teaching CSV](https://github.com/stanford-mse-125/book/blob/main/data/framingham/README.md) provides a **10-year coronary heart disease (CHD)** outcome, not total CVD. It has no HDL, LDL, or physical-activity column. The 4,240-row supervised monotonic boosted/logistic model uses a 2,544/848/848 train/validation/test split. Held-out CHD AUROC was **0.68959**, Brier score **0.12188**, and ECE **0.01856**. `/api/predict` returns this as a separate research estimate from the PREVENT-based total-CVD estimate, with missing-input quality. Neither model is externally validated for individual use.

The experimental lead-mask adapter was trained on a stratified 300-record PTB-XL subset. On 50 held-out ECGs per mode, lead-I AUROC changed from 0.77315 to **0.80329** and six-lead AUROC from 0.86111 to **0.88212**. The API reports the active lead mask and the small held-out metric, which is not confidence in an individual result. A low-rank bottleneck was also tested on the complete cached PTB-XL vectors and 24,000 MIMIC vectors. Neither candidate met the combined AUROC/F1 validation gate, so the existing PTB head, MIMIC adapter, and ONNX artifact remain the serving versions.

The scanned-ECG path now estimates grid spacing, removes grid ink, and uses a calibration pulse when detectable. If the pulse is absent, it uses the measured grid with assumed 10 mm/mV gain and 25 mm/s speed. It rejects scans without a measurable grid. A 3×4 printout supplies short lead strips, so strips are repeated to fill the ECG encoder window; scan output remains experimental.

To resume extraction and incremental training after an interruption:

```powershell
.venv\Scripts\python -m ml_pipeline.slow_train --project-root 'D:\CVG Project' --batch-size 8 --sleep-ms 100
```

The trainer reuses `D:\CVG Project\models\ptbxl_cached_embeddings.npz`, writes each 250-record shard atomically, and runs at BelowNormal priority with two Torch threads.

## Deployment

`hf_space_build/` is a standalone free-tier Gradio ZeroGPU Space bundle containing only inference code and runtime models. Gradio Server mode preserves the FastAPI `/api/*` routes without requesting GPU time for CPU inference. It excludes PTB-XL and MIMIC datasets and the large embedding cache. The former Docker recipe remains under `deploy/`. `app/frontend/dist` is the Cloudflare Pages output; `deploy/wrangler.toml` and `deploy/functions` provide the Pages configuration and API proxy. The public `HF_SPACE_URL` in the Wrangler configuration points to `https://aayush1574-cardioscope-api.hf.space`.

The free-tier deployment is live at `https://cardioscope-research.pages.dev/`, backed by `https://aayush1574-cardioscope-api.hf.space`. On 2026-11-02, all four hosted smoke paths returned HTTP 200 through Cloudflare Pages: digital ECG prediction, scanned ECG prediction, PDF report parsing with clinical-only prediction, and lifestyle simulation. The Gradio `score_ecg_embedding` ZeroGPU endpoint also responded.

## Verified prediction improvements (2026-11-03)

The live upload path now uses separate preprocessing for the two ECG branches. The dedicated MIMIC path matches eleven finite sampled cached embeddings within 0.000004 and reproduces cached-feature ICD predictions; a nonfinite sampled source recording was rejected. Standard digital 12-lead inputs that pass technical checks can use ECG+clinical ICD fusion again. Partial leads, scans and warning-bearing signals fall back to clinical-only ICD scoring. Existing PTB preprocessing and calibration are preserved.

A new AFIB rhythm head uses frozen PTB embeddings from 16,854 rhythm-annotated training records. On 2,103 fold-10 records (152 AFIB positives), AUROC is 0.98875, average precision 0.95672, precision 0.92466, recall 0.88816 and F1 0.90604 at its validation-selected research marker. Patient-bootstrap AUROC 95% interval is [0.97461, 0.99631]. These are internal standard-digital-12-lead results, not clinical, wearable or scan validation. AF annotation, ICD I48 diagnosis groups and long-term risk remain separate targets.

Digital uploads are checked for duration, finite samples, amplitude scale, supported active leads and high-frequency noise. Reports include deterministic evidence summaries, units, missing fields and uncertainty. Extraction records source lines when unambiguous, explicit reference ranges and supported unit conversions; measurement dates and source accuracy still require review. Expanded measured-lab linear and boosted candidates failed validation promotion checks and are not served.

Detailed verification and remaining validation gaps are in `client_test_kit/IMPLEMENTATION_VERIFICATION.md`. `scripts/evaluate_external_cohort.py` supports evaluation of a separately supplied independent labeled manifest without model fitting. No independent external cohort has yet been evaluated, and no prospective diagnostic performance is claimed.

The ECG scan digitizer cannot reliably recover paper speed or gain from arbitrary images even when a grid is measured. OCR and regex report extraction can make errors, so extracted values require review. Clinical-only, manual-only, partial-lead, scanned ECG, subgroup, and workflow performance require further validation. The diagnostic outputs and lifestyle scenario deltas are not causal treatment estimates.
