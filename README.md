# CardioScope connected application

The redesigned frontend is connected to the frozen research API on main. The model-backend and frontend branches preserve the separate baselines. Model weights and inference preprocessing are unchanged.

## Local setup

Requires Python 3.11, Node.js, and Tesseract on PATH for image OCR.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts/restore_models.py
$env:CVG_PROJECT_ROOT = (Get-Location).Path
$env:CVG_MODELS_DIR = Join-Path (Get-Location).Path 'models'
.venv\Scripts\python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend-preview
npm ci
npm run dev
```

Open http://127.0.0.1:5174. Vite proxies /api to local port 8000. Existing local models can instead be selected through CVG_MODELS_DIR. If the encoder remains in pretrained/ECGFounder, point CVG_PROJECT_ROOT to that original workspace. Restoration downloads about 375 MB from immutable URLs and verifies checksums; it does not train models.

## Workflows

Manual and CSV/JSON inputs, PDF/image extraction with reviewable evidence, ECG CSV/NPY/WFDB and experimental scans, separate ICD/ECG/AF outputs, PREVENT and cohort CHD estimates, clinical ratios, explanations, scenario controls, live demos, input export and printing are connected. Reports retain submitted inputs; subsequent edits invalidate results. Reports and assessments are processed on the backend; browser state clears on refresh.

Processed server waveforms use standardized amplitude and 20 Hz display sampling. Raw CSV viewing uses the declared recording rate. Neither viewer is a diagnostic tracing.

## Verification

Start the API on port 8000 and frontend on 5175 (`npm exec vite -- --host 127.0.0.1 --port 5175 --strictPort`), then:

```powershell
.venv\Scripts\python scripts/verify_integration.py
cd frontend-preview
npm run build
npx playwright install chromium
npm run check:ui
npm run check:motion
```

CVG_TEST_URL overrides the API test target; CVG_UI_URL overrides connected browser tests. Motion checks use port 5175. Historical offline input/report tests belong to the preserved frontend baseline. See docs/INTEGRATION_VERIFICATION.md for results and limits.

## Hosting

Build output is frontend-preview/dist. deploy/wrangler.toml selects it and retains the existing Pages Function proxy to the Hugging Face API. Git publication does not deploy either hosting service. app/frontend is retained as the original UI reference.

Research and educational use only. Internal results do not establish external clinical validity. Scenario changes are model sensitivity, not treatment effects.
