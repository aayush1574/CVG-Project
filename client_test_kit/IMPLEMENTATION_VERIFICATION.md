# Prediction improvements implemented — 2026-11-03

## Implemented and locally verified

1. Dedicated MIMIC waveform preprocessing reproduces the encoder cache. Eleven finite sampled recordings across train/validation/test matched within 0.000004. One nonfinite sampled recording was rejected by the input gate. A raw WFDB upload's ICD probabilities also matched cached-feature inference within 0.0001. PTB uses its existing separate preprocessing, head, and calibration.
2. Full digital ECG+clinical ICD inference restored only when the input is twelve-lead and passes technical quality checks without warnings. Partial leads and scans use clinical-only ICD fallback. I21/I44 decisions remain inconclusive because this technical fix does not establish diagnostic reliability.
3. AF rhythm head trained on 16,854 PTB records with rhythm annotations, using the frozen existing embeddings and a regularized logistic head. Fold 9 is split by patient for calibration/threshold fitting and assessment; fold 10 is reported after validation gating. The target is AFIB annotation versus other annotated rhythms; absent rhythm annotations are excluded, not relabeled normal.
4. AF held-out results: 2,103 records, 152 AFIB positives; AUROC 0.98875, average precision 0.95672, precision 0.92466, recall 0.88816, F1 0.90604, Brier 0.01030, ECE 0.00796. Patient bootstrap (200 replicates) gives AUROC 95% interval [0.97461, 0.99631] and average precision [0.93092, 0.97795]. Age/sex subgroup results are in `prediction_upgrade_verification.json`. Small subgroup counts limit conclusions.
5. Signal gates cover duration, finite samples, amplitude/declared millivolt units, supported active leads, flat signals and high-frequency noise. Flat, short, extreme-gain and seeded white-noise uploads return HTTP 422. Technical checks are not clinical signal-quality certification or lead-placement verification.
6. Evidence reports use deterministic templates with assessment scope, supplied measurements/units, missing inputs, quality checks, limitations and clinician discussion prompts. Screen and print preserve the assessed-input snapshot. No LLM-generated diagnosis, medicine instruction or invented measurement is introduced.
7. Report extraction provides document SHA256, source filename, source lines when unambiguous, original/canonical units, conversion factors and explicitly labeled reference intervals. Supported explicit mmol/L lipid/glucose and umol/L creatinine units convert to canonical units. Missing units/dates remain unverified. Both demo reports still extract nine expected values exactly; conversion and reference-interval tests pass. Reference intervals are not model thresholds.
8. Expanded measured-lab HistGradientBoosting and regularized logistic baselines were fitted with train-only preprocessing and patient-separated validation calibration. Neither passed promotion against the current clinical-only model. Candidates and metrics are saved for research, not used by the API. Hospital context, insurance/race and fabricated longitudinal summaries were not used.
9. Standalone staged Space test passes ECG+clinical prediction, AF scoring and evidence generation using only staged models. TypeScript/build checks and live verification are recorded separately.

## Not established by these tests

- No untouched external clinical, actual wearable-device, temporal or paired real-scan evaluation was available in the workspace. `scripts/evaluate_external_cohort.py` now accepts an independently labeled manifest, preserves blank labels as missing, and reports accepted/rejected cases. Supplying a manifest is not itself evidence of independence.
- Existing test folds have been observed in earlier development. They are internal benchmarks, not a pristine prospective trial.
- Clinical-only discrimination and heuristic health-score validation remain limited. More model complexity and threshold changes did not resolve missing information.
- New encoder fine-tuning was not justified by the experiments; full pretrained encoder and existing classifier weights remain intact. The AF head is a new fitted artifact.

## Reproduction

From the workspace root with `PYTHONPATH=.`:

```powershell
.venv\Scripts\python scripts/train_research_upgrades.py
.venv\Scripts\python scripts/compare_linear_clinical.py
.venv\Scripts\python scripts/verify_prediction_upgrades.py
```

Training scripts overwrite research candidates; do not rerun merely to reproduce a report. Verification does not fit models. External evaluation example:

```powershell
.venv\Scripts\python scripts/evaluate_external_cohort.py --manifest path\to\independent_manifest.csv --dataset-name independent-cohort --output external_results.json
```

## Live verification

The deployed Cloudflare Pages proxy returned HTTP 200 for standard MI/normal/AF digital ECGs with restored ECG+clinical scoring, clinical-only inputs, one- and six-lead inputs, scans, PDF/PNG parsing and simulation. Both demo lab reports extracted nine expected fields exactly with source evidence. A flat upload returned HTTP 422. The final frontend bundle, health endpoint and Space RUNNING state were checked. Results: `prediction_upgrade_live_results.json`. Expanded linear candidates at C=0.01, 0.1 and 1 also failed validation promotion.
