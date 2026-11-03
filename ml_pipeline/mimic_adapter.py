"""Incremental MIMIC projection adapter with validation-only calibration."""
from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import f1_score, precision_recall_curve, roc_auc_score
from torch import nn

from .fusion_model import FusionModel


class FusionWithAdapter(nn.Module):
    def __init__(self, base: FusionModel, ecg_dim: int, tab_dim: int, classes: int):
        super().__init__()
        self.base = base
        self.adapter = nn.Sequential(nn.Linear(ecg_dim + tab_dim, 32), nn.SiLU(), nn.Linear(32, classes))

    def forward(self, ecg, tab, mask_ecg, mask_tab):
        logits, risk = self.base(ecg, tab, mask_ecg, mask_tab)
        projected = self.adapter(torch.cat((ecg * mask_ecg, tab), dim=1))
        return logits + projected, risk


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for i in range(bins):
        mask = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= 1)
        if mask.any():
            total += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(total)


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -50, 50)))


def select_calibrator(y: np.ndarray, logits: np.ndarray) -> list[dict]:
    result = []
    shuffled = np.random.default_rng(42).permutation(len(y))
    fit_indices, holdout_indices = np.array_split(shuffled, 2)
    for j in range(y.shape[1]):
        truth = y[holdout_indices, j]
        raw = sigmoid(logits[holdout_indices, j])
        raw_brier = float(np.mean((truth - raw) ** 2))
        raw_ece = ece(truth, raw)
        options = []
        temperatures = np.linspace(.5, 3, 26)
        fit_truth = y[fit_indices, j]
        temperature = min(temperatures, key=lambda t: np.mean((fit_truth - sigmoid(logits[fit_indices, j] / t)) ** 2))
        p = sigmoid(logits[holdout_indices, j] / temperature)
        options.append((float(np.mean((truth - p) ** 2)), ece(truth, p),
                        {"method": "temperature", "temperature": float(temperature)}))
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
        iso.fit(sigmoid(logits[fit_indices, j]), fit_truth)
        ip = iso.predict(raw)
        options.append((float(np.mean((truth - ip) ** 2)), ece(truth, ip),
                        {"method": "isotonic", "x": iso.X_thresholds_.tolist(),
                         "y": iso.y_thresholds_.tolist()}))
        valid = [(b, c, params) for b, c, params in options if b < raw_brier and c < raw_ece]
        chosen = min(valid, key=lambda item: (item[0], item[1])) if valid else None
        result.append({**(chosen[2] if chosen else {"method": "none"}),
                       "raw_brier": raw_brier, "raw_ece": raw_ece,
                       "calibrated_brier": chosen[0] if chosen else raw_brier,
                       "calibrated_ece": chosen[1] if chosen else raw_ece})
    return result


def apply_adapter_calibration(logits: np.ndarray, rules: list[dict]) -> np.ndarray:
    out = sigmoid(logits)
    for j, rule in enumerate(rules):
        if rule["method"] == "temperature":
            out[:, j] = sigmoid(logits[:, j] / rule["temperature"])
        elif rule["method"] == "isotonic":
            out[:, j] = np.interp(out[:, j], rule["x"], rule["y"])
    return out


def _metrics(y, p):
    aucs = [roc_auc_score(y[:, j], p[:, j]) for j in range(y.shape[1]) if len(np.unique(y[:, j])) == 2]
    return {"macro_auroc": float(np.mean(aucs)),
            "macro_f1_at_0_5": float(f1_score(y, p >= .5, average="macro", zero_division=0)),
            "rows": len(y)}


def _atomic_json(path: Path, data: dict):
    temporary = path.with_name(path.stem + ".tmp" + path.suffix)
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def train_mimic_adapter(root: Path, epochs: int = 3) -> dict:
    models = root / "models"
    checkpoint = torch.load(models / "best_multimodal_cvd.pt", map_location="cpu", weights_only=False)
    labels = tuple(checkpoint["labels"])
    base = FusionModel(checkpoint["ecg_dim"], checkpoint["tab_dim"], len(labels), checkpoint["risk_head"])
    base.load_state_dict(checkpoint["state_dict"])
    base.eval()
    for parameter in base.parameters():
        parameter.requires_grad_(False)
    model = FusionWithAdapter(base, checkpoint["ecg_dim"], checkpoint["tab_dim"], len(labels))
    clinical = pd.read_csv(root / "artifacts/clinical-ext-icd-prepared-24k/manifest.csv")
    ecg_manifest = pd.read_csv(root / "artifacts/ecgfounder_ext_icd_prepared_24k/manifest.csv")
    if not clinical.study_id.equals(ecg_manifest.study_id):
        raise ValueError("MIMIC ECG and clinical rows are not aligned")
    features = np.load(root / "artifacts/ecgfounder_ext_icd_features_24k/ecgfounder_features.npy", mmap_mode="r")
    metadata = json.loads((root / "artifacts/ecgfounder_ext_icd_prepared_24k/metadata.json").read_text())
    indices = [metadata["labels"].index(label) for label in labels]
    targets = np.asarray([[float(index in ast.literal_eval(value)) for index in indices]
                          for value in clinical.targets], np.float32)
    records = [{"age": row.age, "sex": "female" if row.gender == "F" else "male",
                "creatinine": row.creatinine_last, "fasting_blood_sugar": row.glucose_last}
               for row in clinical.itertuples()]
    transform = joblib.load(models / "clinical_transform.joblib")
    tab = transform.transform(records)
    splits = clinical.split.to_numpy()
    train = np.flatnonzero(splits == "train")
    val = np.flatnonzero(splits == "val")
    test = np.flatnonzero(splits == "test")
    if min(len(train), len(val), len(test)) == 0:
        raise ValueError("MIMIC artifact needs train, val, and test splits")
    optimizer = torch.optim.AdamW(model.adapter.parameters(), lr=2e-4, weight_decay=1e-3)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    for epoch in range(epochs):
        model.train()
        model.base.eval()
        shuffled = np.random.default_rng(100 + epoch).permutation(train)
        for offset in range(0, len(shuffled), 256):
            ix = shuffled[offset:offset + 256]
            ecg = torch.from_numpy(np.asarray(features[ix]).copy())
            clinical_tensor = torch.from_numpy(tab[ix])
            mask = torch.from_numpy((np.random.default_rng(epoch * len(train) + offset).random((len(ix), 1)) > .3).astype(np.float32))
            logits, _ = model(ecg * mask, clinical_tensor, mask, torch.ones_like(mask))
            loss = nn.functional.binary_cross_entropy_with_logits(logits, torch.from_numpy(targets[ix]))
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            time.sleep(.01)
        schedule.step()
    model.eval()
    def predict(ix, use_ecg):
        output = []
        with torch.inference_mode():
            for part in np.array_split(ix, max(1, int(np.ceil(len(ix) / 512)))):
                mask = torch.full((len(part), 1), float(use_ecg))
                ecg = torch.from_numpy(np.asarray(features[part]).copy()) * mask
                logits, _ = model(ecg, torch.from_numpy(tab[part]), mask, torch.ones_like(mask))
                output.append(logits.numpy())
        return np.concatenate(output)
    validation = {}
    testing = {}
    calibration = {}
    thresholds = {}
    for modality, use_ecg in (("ecg_clinical", True), ("clinical_only", False)):
        val_logits = predict(val, use_ecg)
        rules = select_calibrator(targets[val], val_logits)
        val_prob = apply_adapter_calibration(val_logits, rules)
        cutoffs = []
        for j in range(len(labels)):
            precision, recall, cut = precision_recall_curve(targets[val, j], val_prob[:, j])
            f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
            cutoffs.append(float(cut[int(np.argmax(f1))]) if len(cut) else .5)
        thresholds[modality] = cutoffs
        test_logits = predict(test, use_ecg)
        validation[modality] = _metrics(targets[val], sigmoid(val_logits))
        calibrated_test = apply_adapter_calibration(test_logits, rules)
        testing[modality] = _metrics(targets[test], calibrated_test)
        testing[modality]["macro_f1_at_validation_thresholds"] = float(
            f1_score(targets[test], calibrated_test >= np.asarray(cutoffs), average="macro", zero_division=0))
        calibration[modality] = rules
    previous_path = models / "mimic_projection_adapter.pt"
    previous = torch.load(previous_path, map_location="cpu", weights_only=False) if previous_path.is_file() else None
    new_metric = validation["ecg_clinical"]
    old_metric = previous.get("validation", {}).get("ecg_clinical", {}) if previous else {}
    promote = previous is None or new_metric["macro_auroc"] > old_metric.get("macro_auroc", -1) or new_metric["macro_f1_at_0_5"] > old_metric.get("macro_f1_at_0_5", -1)
    if promote:
        temporary = previous_path.with_name("mimic_projection_adapter.tmp.pt")
        torch.save({"state_dict": model.adapter.state_dict(), "validation": validation,
                    "test": testing, "labels": labels}, temporary)
        os.replace(temporary, previous_path)
        _atomic_json(models / "mimic_adapter_calibration.json", {"labels": labels, "modalities": calibration,
                                                                  "thresholds": thresholds})
        # The ONNX file retains the existing four-input contract. Export and quantize
        # to temporary paths, then replace the serving artifact only after validation.
        from onnxruntime.quantization import QuantType, quantize_dynamic
        onnx_tmp = models / "model_adapter.tmp.onnx"
        quant_tmp = models / "model_quantized.tmp.onnx"
        torch.onnx.export(model, (torch.zeros(1, checkpoint["ecg_dim"]),
                                  torch.zeros(1, checkpoint["tab_dim"]), torch.ones(1, 1), torch.ones(1, 1)),
                          onnx_tmp, input_names=["ecg", "tab", "mask_ecg", "mask_tab"],
                          output_names=["disease_logits", "risk_logits"] if checkpoint["risk_head"] else ["disease_logits"],
                          opset_version=18, dynamo=False)
        quantize_dynamic(onnx_tmp, quant_tmp, weight_type=QuantType.QInt8)
        os.replace(quant_tmp, models / "model_quantized.onnx")
        onnx_tmp.unlink(missing_ok=True)
        metrics_path = models / "research_metrics.json"
        metrics = json.loads(metrics_path.read_text()) if metrics_path.is_file() else {}
        metrics["mimic_projection_adapter"] = {"validation": validation, "test": testing,
                                                "calibration": calibration}
        _atomic_json(metrics_path, metrics)
    return {"validation": validation, "test": testing, "promoted": promote}
