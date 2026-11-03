# Model audit — 2026-11-02

## Verdict

The models are fitted and inference works. The saved held-out metrics reproduce from the serving checkpoints. This is a functioning research prototype, with materially different reliability across components. The evidence does not support clinical diagnostic reliability or a medically validated health score.

No models were retrained and no weights were changed during this audit. Numerical results are in `model_audit.json`; the evaluation script is `scripts/audit_models.py`.

## Recomputed serving metrics

| Component | Test rows | Macro AUROC | Macro average precision | Macro F1 at served threshold | Macro F1 at 0.5 |
|---|---:|---:|---:|---:|---:|
| PTB-XL waveform labels | 2,055 | 0.9220 | 0.7908 | 0.7264 | 0.7264 |
| MIMIC ECG + clinical | 2,000 | 0.8585 | 0.5101 | 0.5111 | 0.3956 |
| MIMIC clinical only | 2,000 | 0.7132 | 0.2656 | 0.3134 | 0.1336 |

AUROC measures ranking, not diagnostic accuracy or the reliability of the displayed percentage. Average precision, per-class precision/recall, F1 at the serving threshold, and calibration must be examined together. F1-selected thresholds can produce many false positives for rare labels.

## Data and split checks

- MIMIC: 24,000 records from 6,807 people. Zero subject overlap across train/validation/test. Prepared metadata declares labs restricted to the 24 hours before ECG and excludes outcome/leakage fields; this audit inspected the declaration but did not rescan the 13-GB raw lab file.
- PTB-XL: 21,837 records from 18,885 people. Zero patient overlap between folds 1–8, 9, and 10. All cached embeddings are finite. Fresh embeddings for IDs 1, 17, and 77 match cached vectors with maximum absolute differences below 0.000001.
- Only 20,413 PTB records are supervised by the head. The label policy requires diagnostic statement likelihood >=50 and excludes 1,424 records without mapped labels under that policy. Results apply to this labeled subset, not all 21,837 records or all possible diagnostic labels.
- The cohort CSV contains no exact duplicate rows. Its split is stratified 60/20/20; imputation and scaling fit the training partition.
- PTB normalization statistics are fitted on training folds. A sigmoid multi-label head and binary/focal losses are appropriate for overlapping labels.

## Material limitations

1. **Clinical-only acute MI and conduction-block prediction is weak.** At the served thresholds, I21 precision/recall/F1 are 0.091/0.162/0.116; I44 precision/recall/F1 are 0.054/0.725/0.100. These do not support dependable diagnosis or exclusion.
2. **PTB probabilities are not calibrated.** Mean 10-bin ECE is 0.1604. HYP F1 is 0.505 and recall 0.457. The macro AUROC of 0.922 should not be described as 92.2% accuracy.
3. **Sparse clinical training inputs.** The served ICD model uses age, sex, creatinine, and glucose. Creatinine is missing in 57.2% of the MIMIC table and glucose in 59.2%. Lipids, BP, lifestyle, and most calculated ratios are not learned ICD predictors; they affect separate equations/heuristics.
4. **Health score is a fixed heuristic.** It has no supervised outcome validation. PREVENT is a separate equation. The Framingham model predicts 10-year CHD, not total CVD: AUROC 0.6896, Brier 0.1219, ECE 0.0186 on 848 rows. Its Brier improvement over a test-prevalence constant predictor is only about 5.5% (descriptive comparison).
5. **Partial-lead evidence is small.** Each mode has only 50 held-out ECGs. These are digitally masked PTB signals, not a validation on actual smartwatch/Kardia recordings. The ICD branch correctly uses clinical-only inputs for partial-lead uploads.
6. **Scan tests establish pipeline operation only.** A clean generated scan passing extraction does not establish accuracy on real photographs, unusual grids, paper speeds, or layouts. Short strips are repeated for the encoder window.
7. **Test results were repeatedly observed.** Incremental training and later experiments evaluate the same held-out folds. Promotion uses validation, but repeated test exposure weakens claims of a pristine final test. A new locked external test is needed.
8. **MIMIC raw-to-embedding parity is not independently verified here.** Cached-feature metadata says official model-specific preprocessing; the live encoder uses filtering and per-lead normalization. Raw MIMIC extraction provenance must be checked against that exact implementation before claiming end-to-end equivalence. The PTB parity check above does pass.
9. **Candidate improvements were not established.** The stack selected alpha=0, and bottleneck candidates failed the promotion gate. These artifacts do not establish a V2 clinical AUROC improvement.

## Live observations

Both the MI-labeled and normal demo ECG uploads returned HTTP 200 with five PTB and five ICD outputs. Under identical age/sex/lab inputs, the MI-labeled ECG produced MI waveform score 0.309 and NORM score 0.670, demonstrating an individual missed MI label at the fixed 0.5 cutoff. PTB MI labels and MIMIC acute-MI ICD labels are different targets and must not be equated. The demos use known local records and illustrative profiles, so they are not independent validation cases.

## Next evidence needed

Before claims beyond a research demonstration: verify MIMIC preprocessing parity; lock an untouched patient-separated external test; report per-class precision, recall, average precision and confidence intervals; assess calibration on independent data; assess age/sex/device subgroups; validate real wearable and scanned inputs; and evaluate any health-score claim against a clearly defined longitudinal outcome. No threshold change alone can create missing predictive information.

Source for official PTB fold policy: https://physionet.org/content/ptb-xl/1.0.3/
