# Reliability changes

The audit found a MIMIC raw-input preprocessing mismatch: ECG study 42981003 produced a fresh embedding with maximum absolute difference 1.3293 and cosine similarity 0.9197 versus its cached training vector. Several normalization variants also failed to reproduce the cached vector. This remains unresolved. The serving API therefore withholds MIMIC waveform fusion and explicitly uses the clinical-only classifier for ICD estimates. The PTB waveform path separately passed cache parity checks.

## Measured calibration improvement

The frozen PTB head weights are unchanged. Five positive-slope sigmoid calibrators were fitted on 1,029 fold-9 rows and assessed on 1,014 different fold-9 rows, with patient-separated groups. A calibrator was retained only when assessment Brier score and ECE both improved. Fold 10 was used for reporting, not selecting calibrators.

| Fold-10 measure | Raw scores | Calibrated scores |
|---|---:|---:|
| Macro ECE (10 bins) | 0.1604 | 0.0143 |
| Macro Brier | 0.1103 | 0.0789 |
| Macro AUROC | 0.9220 | 0.9220 |
| Macro F1 at corresponding mapped decision cutoffs | 0.7264 | 0.7264 |
| Macro F1 at a fixed 0.5 cutoff | 0.7264 | 0.6973 |

Mapped cutoffs preserve existing classifications; calibration improves the probability scale, not discrimination. The JSON calibrator is bound to the PTB checkpoint SHA256. Calibration is served only for standard digital 12-lead inputs; partial leads and scans remain uncalibrated experimental inputs.

## Serving safeguards

- I21 and I44 clinical-only flags are null/inconclusive, rather than unsupported positive/negative decisions.
- All ICD flags are null/inconclusive if age/sex or trained lab inputs are missing. Remaining numeric scores are research outputs with explicit limitations.
- Nonfinite, negative numeric inputs and reversed blood pressure values are rejected with HTTP 422.
- The UI and printed report render null flags as inconclusive. The report retains the exact input snapshot used for its assessment.
- The health index is explicitly identified as a heuristic without outcome validation.

## Remaining work

Clinical-only discrimination remains limited; its measured AUROC is 0.7132. The MIMIC waveform preprocessing must be reproduced and independently verified before reenabling fusion. Independent clinical, real-wearable, and real-scan validation is still needed. The improvements here do not establish diagnostic reliability or correct every missed disease label.
