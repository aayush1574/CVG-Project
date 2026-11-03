"""Fit Platt maps and max-F1 thresholds on validation; evaluate once on test."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, precision_recall_curve, roc_auc_score

from ml_pipeline.calibration import apply_calibration
from ml_pipeline.fusion_model import FusionModel

ROOT = Path(r"D:\CVG Project")
ARTIFACT = ROOT / "artifacts"
checkpoint_path = ROOT / "models/best_multimodal_cvd.pt"
checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
transform = joblib.load(ROOT / "models/clinical_transform.joblib")
frame = pd.read_csv(ARTIFACT / "clinical-ext-icd-prepared-24k/manifest.csv")
ecg_manifest = pd.read_csv(ARTIFACT / "ecgfounder_ext_icd_prepared_24k/manifest.csv")
if not frame.study_id.equals(ecg_manifest.study_id):
    raise ValueError("Clinical and ECG artifact order differs")
features = np.load(ARTIFACT / "ecgfounder_ext_icd_features_24k/ecgfounder_features.npy", mmap_mode="r", allow_pickle=False)
metadata = json.loads((ARTIFACT / "ecgfounder_ext_icd_prepared_24k/metadata.json").read_text())
label_indices = [metadata["labels"].index(label) for label in checkpoint["labels"]]
y = np.array([[float(j in ast.literal_eval(value)) for j in label_indices]
              for value in frame.targets], dtype=np.float32)
records = [{"age": row.age, "sex": "female" if row.gender == "F" else "male",
            "creatinine": row.creatinine_last, "fasting_blood_sugar": row.glucose_last}
           for row in frame.itertuples()]
tab = transform.transform(records)
model = FusionModel(checkpoint["ecg_dim"], checkpoint["tab_dim"], len(checkpoint["labels"]))
model.load_state_dict(checkpoint["state_dict"])
model.eval()


def logits_for(split: str, with_ecg: bool) -> tuple[np.ndarray, np.ndarray]:
    ix_all = np.flatnonzero(frame.split.to_numpy() == split)
    output = []
    with torch.inference_mode():
        for offset in range(0, len(ix_all), 256):
            ix = ix_all[offset:offset + 256]
            ecg = torch.from_numpy(np.asarray(features[ix]).copy()) if with_ecg else torch.zeros(len(ix), checkpoint["ecg_dim"])
            logits, _ = model(ecg, torch.from_numpy(tab[ix]),
                              torch.full((len(ix), 1), float(with_ecg)), torch.ones(len(ix), 1))
            output.append(logits.numpy())
    return np.concatenate(output), y[ix_all]


bundle = {"checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
          "labels": list(checkpoint["labels"]), "fit_split": "val", "modalities": {}}
metrics = json.loads((ROOT / "models/research_metrics.json").read_text())
for key, with_ecg in (("ecg_clinical", True), ("clinical_only", False)):
    val_logits, val_y = logits_for("val", with_ecg)
    slopes, intercepts, thresholds = [], [], []
    for j in range(val_y.shape[1]):
        classifier = LogisticRegression(C=1e4, max_iter=1000).fit(val_logits[:, j, None], val_y[:, j])
        slope = float(classifier.coef_[0, 0])
        intercept = float(classifier.intercept_[0])
        p = classifier.predict_proba(val_logits[:, j, None])[:, 1]
        precision, recall, candidates = precision_recall_curve(val_y[:, j], p)
        f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
        index = int(np.argmax(f1))
        slopes.append(slope)
        intercepts.append(intercept)
        thresholds.append(float(np.clip(candidates[index], 1e-5, 1 - 1e-5)))
    bundle["modalities"][key] = {"platt_slope": slopes, "platt_intercept": intercepts,
                                  "thresholds": thresholds}
    test_logits, test_y = logits_for("test", with_ecg)
    p, decision_scores, decisions = apply_calibration(test_logits, bundle, key)
    raw = 1 / (1 + np.exp(-np.clip(test_logits, -50, 50)))
    result = {"macro_auroc": float(np.mean([roc_auc_score(test_y[:, j], p[:, j]) for j in range(p.shape[1])])),
              "macro_f1_at_0_5_raw": float(f1_score(test_y, raw >= .5, average="macro", zero_division=0)),
              "macro_f1_at_validation_thresholds": float(f1_score(test_y, decisions, average="macro", zero_division=0)),
              "macro_brier_raw": float(np.mean([brier_score_loss(test_y[:, j], raw[:, j]) for j in range(p.shape[1])])),
              "macro_brier_calibrated": float(np.mean([brier_score_loss(test_y[:, j], p[:, j]) for j in range(p.shape[1])])),
              "per_class_f1": dict(zip(checkpoint["labels"], [float(x) for x in f1_score(test_y, decisions, average=None, zero_division=0)]))}
    metrics[key] = result
    print(json.dumps({"modality": key, **result}), flush=True)
metrics["thresholds_ecg_clinical"] = dict(zip(checkpoint["labels"], bundle["modalities"]["ecg_clinical"]["thresholds"]))
metrics["thresholds_clinical_only"] = dict(zip(checkpoint["labels"], bundle["modalities"]["clinical_only"]["thresholds"]))
(ROOT / "models/modality_calibration.json").write_text(json.dumps(bundle, indent=2))
(ROOT / "models/research_metrics.json").write_text(json.dumps(metrics, indent=2))
