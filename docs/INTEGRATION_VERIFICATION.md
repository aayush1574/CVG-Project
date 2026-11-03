# Integration verification — 2026-11-03

Tested locally with frozen artifacts. Canonical app/backend and ml_pipeline match the model-backend baseline. No model training or threshold changes.

- Strict TypeScript and production Vite build passed.
- 15 API cases passed: clinical-only, MI/normal/AF digital CSV, one and six leads, scan, WFDB pair, NPY, PDF/PNG extraction, flat/short/nonfinite rejection, simulation.
- Browser workflow passed: live demo, digital inference, input correction, PDF extraction/review and source evidence, scenario calculation, PDF export, mobile layout, no runtime errors.
- Request tests passed: categorical structured import, HTTP 422 without retry, cancellation on input edits, one retry on HTTP 503, clinical-only rendering.
- Automated report accessibility scan: zero violations.
- Motion checks: 22 passed. Vector/state checks: 11 passed. Welcome responsive checks include 320, 390, 768 and 1440 pixels.
- All 16 manifest artifacts were checked against SHA-256 hashes. I21/I44 abstentions and partial-lead/scan ICD fallback remain intact.

API checks were local; no hosting deployment was performed. Engine status reports reachability, not full asset readiness. Server waveform arrays are standardized 20 Hz overviews; raw CSV viewing retains its declared sampling rate. Future API waveform changes require metadata and adapter updates.

Existing backend behavior for clean 9.5–<10-second twelve-lead inputs remains unchanged: MIMIC preprocessing requires 10 seconds. Supply full 10-second recordings. Independent clinical, wearable and real-scan validation remains outstanding. Scenario deltas are not treatment effects.
