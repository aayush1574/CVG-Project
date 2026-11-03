# Evidence-based prediction and report improvement plan

Investigation date: 2026-11-03. No model training, serving-code changes, or deployment was performed during this investigation.

## 1. Restore the correct MIMIC encoder path first

The upstream ECGFounder implementation uses canonical lead order, a 50-Hz notch (Q=30), fourth-order 0.67–40-Hz bandpass, 201-point median baseline subtraction at 500 Hz, and global z-score normalization. Reproducing that pipeline matches local cached MIMIC embeddings within a few millionths. Detailed technical comparisons are in `mimic_preprocessing_discovery.json`.

This is the highest-priority fix. The current API deliberately withholds MIMIC waveform fusion because the previous live filter/normalization failed cache parity. Use a dedicated MIMIC preprocessor and a separately encoded embedding; retain the existing PTB preprocessing because its head and lead adapter were trained against that pipeline. A single shared changed preprocessor would invalidate PTB calibration and adapters.

Before reenabling MIMIC fusion: expand parity checks across records/devices/quality; verify live raw-upload logits against cached logits; test header lead-order variations; verify missing/flat/noisy inputs; confirm active artifact hashes and calibrators. The original cached-test ECG+clinical AUROC 0.8585 is a reference result, not a promised new accuracy gain. Its validity still depends on population and label limitations.

Official sources:
- https://github.com/PKUDigitalHealth/ECGFounder/blob/master/dataset.py
- https://github.com/PKUDigitalHealth/ECGFounder/blob/master/util.py

## 2. Define each target precisely and add a rhythm-specific head

PTB NORM/MI/STTC/CD/HYP are waveform label groups. MIMIC ICD labels originate from linked ED/hospital discharge diagnoses; neither directly establishes an acute diagnosis at upload time. Long-term incident CHD is a third target. Present each with its own meaning, evidence, and limitations rather than averaging them into an asserted disease probability.

AF is not a target of the current five-class PTB head. An AF demo therefore cannot be expected to yield a direct PTB AF probability. Train a separately validated AF/rhythm head from PTB rhythm annotations and/or a suitable labeled rhythm dataset. Do not infer current AF from a broad MIMIC I48 discharge-code estimate alone.

Source: https://physionet.org/content/mimic-iv-ecg-ext-icd-labels/1.0.1/

## 3. Improve clinical inputs with deployment-compatible features

The current served MIMIC clinical branch uses age, sex, creatinine, and glucose. Existing prepared tables additionally contain pre-ECG potassium, sodium, hemoglobin, WBC, and lab summaries. An older local 134-feature clinical model has archived test macro AUROC 0.7652 and average precision 0.3085, compared with current clinical-only 0.7132 and 0.2656. This is a candidate worth investigating, not an approved replacement: it also uses admission timing/context and insurance/language/race/marital-status categories that may introduce hospital-specific shortcuts and unavailable inputs.

Compare models on identical patient partitions with three input sets: current four fields; additional available measured labs; and historical inpatient context as an ablation only. Fit preprocessing only on training data. Prefer features available from the actual client workflow. Missing timeline summaries must remain missing; one uploaded measurement must not be fabricated into min/max/mean/count history. Add BP/lipid/HbA1c predictors only with real labeled training measurements.

## 4. Use a limited experiment suite with a locked external test

Start with regularized logistic regression, HistGradientBoosting, and a residual tabular model using the same inputs. Test missingness indicators, modality dropout, balanced batches, and loss weighting on training/validation. For minority classes, compare average precision and precision/recall at the intended operating point; do not promote merely because one macro metric increases. Existing focal/bottleneck experiments did not improve enough to justify promotion. Synthetic oversampling does not create real independent minority cases.

Thresholds should reflect an explicit research use case and be fitted only on validation or inner CV. Estimate performance uncertainty using patient-level bootstrap confidence intervals; include age/sex/device/missing-input subgroups and the fraction of requests where the model abstains. Keep a new external/temporal test locked until the pipeline and operating points are frozen. Existing test folds have been repeatedly inspected.

Sources:
- https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html
- https://scikit-learn.org/stable/modules/classification_threshold.html
- https://scikit-learn.org/stable/modules/calibration.html

## 5. Gate input quality before inference

Add duration, sample-rate, lead identity, units/gain, saturation, baseline drift, flat-line and noise checks. Reject inadequate records rather than normalizing arbitrary noise into a usable-looking signal. Evaluate actual wearable recordings; simulated lead masking is not device validation. Require scan layout/calibration quality and avoid clinical claims from repeated short strips. Compare scanned reconstructions to paired digital traces before treating scan predictions as equivalent.

For reports, persist source document, extraction text/row, units, timestamp, confidence and user confirmation per value. Distinguish casual from fasting glucose. Preserve missing and out-of-range inputs in the report. Use report-specific lab reference intervals when available and distinguish them from validated risk-model inputs.

## 6. Generate informative reports from structured evidence

Every finding should include the predicted target, input source and date, calibrated research score, decision status, supporting measurements, missing measurements, relevant validation quality, and an appropriate clinician discussion prompt. Show that a percentage can change because of imputation or measurement differences. Do not convert a population-level AUROC into personal confidence.

Use deterministic, reviewed templates first. If an LLM is added for readable prose, it should summarize only the structured output and retrieved approved references, preserve inconclusive states, and cite evidence. It must not invent measurements, alter numerical predictions, convert missing data into normal findings, or issue medication instructions. An LLM improves explanation quality, not the classifier's discrimination. Evaluate these generated narratives for factual consistency and unsupported claims.

Use measured clinical values for observation sections; a clearly labeled heuristic index may remain illustrative. Do not present a high health index as a medically validated probability of being healthy. A valid long-term risk claim requires an endpoint-matched longitudinal cohort and independent validation.

## Suggested order

1. Dedicated MIMIC preprocessing plus raw/cached/live parity, then cautiously restore waveform fusion.
2. Input-quality gates and evidence-linked report templates, preserving abstention.
3. A direct AF/rhythm head and deployment-compatible expanded-lab clinical model.
4. Independent patient/device/temporal validation with calibration, threshold, subgroup, and abstention metrics.
5. Consider broader encoder fine-tuning only if these changes leave a demonstrated representation bottleneck.
