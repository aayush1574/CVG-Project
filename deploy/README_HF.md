---
title: CardioScope Research API
emoji: 🫀
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
---

# CardioScope Research API

Research & Educational Simulation Only. This API is not validated for diagnosis, treatment decisions, or individual CVD event prediction.

The staged Space repository is self-contained: `Dockerfile`, `requirements.txt`, `app/backend`, inference-only `ml_pipeline`, and runtime files under `models/`. It includes the official ECGFounder checkpoint to encode uploaded 500 Hz digital or experimental scanned ECGs. It excludes raw PTB-XL/MIMIC data and cached embeddings. Build from the staged repository root with `docker build .` or push the directory contents to a Hugging Face Docker Space.

Frozen internal metrics: all **21,837 PTB-XL records** were embedded with **0 failures**; the five-superclass head achieved **0.92199 test macro AUROC** and **0.72640 macro F1 at 0.5** on 2,055 labeled fold-10 ECGs. The 24,000-record MIMIC adapter achieved test macro AUROC **0.85852** with ECG + clinical data and **0.71319** clinical-only on 2,000 held-out rows. Complete metrics are in `models/research_metrics.json`.

Endpoints: `/api/health`, `/api/predict`, `/api/parse-report`, `/api/simulate`, and `/api/training-status`. The score is an educational index and scenario deltas are not causal effects. Review OCR-extracted report values before assessment.
