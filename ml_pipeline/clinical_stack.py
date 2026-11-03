"""Clinical-only HistGB + frozen MIMIC MLP stack on the official artifact split."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path

os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import f1_score, precision_recall_curve, roc_auc_score

from .clinical_lifestyle_branch import engineer_record
from .mimic_adapter_inference import apply_adapter_calibration

LABELS = ("I48", "I50", "I25", "I21", "I44")
FIELDS = ("age", "sex_male", "creatinine", "fasting_blood_sugar", "egfr_ckd_epi_2021")


def _priority():
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    os.environ["OPENBLAS_NUM_THREADS"] = "2"
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000)
    except (AttributeError, OSError):
        pass
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)


def feature_matrix(records: list[dict]) -> np.ndarray:
    rows = []
    for record in records:
        rec = engineer_record(record)
        rec["sex_male"] = 1.0 if str(record.get("sex", "")).lower() in {"male", "m"} else 0.0 if record.get("sex") else np.nan
        row = []
        for field in FIELDS:
            try:
                value = float(rec.get(field, np.nan))
                row.append(value if np.isfinite(value) else np.nan)
            except (TypeError, ValueError):
                row.append(np.nan)
        rows.append(row)
    return np.asarray(rows, dtype=np.float32)


def score(y: np.ndarray, p: np.ndarray, thresholds: np.ndarray | float = .5) -> dict:
    aucs = [roc_auc_score(y[:, j], p[:, j]) for j in range(y.shape[1]) if len(np.unique(y[:, j])) == 2]
    return {"macro_auroc": float(np.mean(aucs)),
            "macro_f1": float(f1_score(y, p >= thresholds, average="macro", zero_division=0)),
            "macro_brier": float(np.mean((y - p) ** 2)), "rows": int(len(y))}


def thresholds(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    cuts = []
    for j in range(y.shape[1]):
        precision, recall, cut = precision_recall_curve(y[:, j], p[:, j])
        f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
        cuts.append(float(cut[np.argmax(f1)]) if len(cut) else .5)
    return np.asarray(cuts)


def predict_probabilities(bundle: dict, records: list[dict], mlp_prob: np.ndarray, modality: str) -> tuple[np.ndarray, np.ndarray]:
    x = feature_matrix(records)
    gb = np.stack([model.predict_proba(x)[:, 1] for model in bundle["models"]], axis=1)
    alpha = bundle["alpha"][modality]
    p = np.clip((1 - alpha) * mlp_prob + alpha * gb, 1e-6, 1 - 1e-6)
    return p, np.asarray(bundle["thresholds"][modality])


def train(root: Path) -> dict:
    _priority()
    import torch
    from .fusion_model import FusionModel
    from .mimic_adapter_inference import FusionWithAdapter

    models_dir = root / "models"
    clinical = pd.read_csv(root / "artifacts/clinical-ext-icd-prepared-24k/manifest.csv")
    ecg_manifest = pd.read_csv(root / "artifacts/ecgfounder_ext_icd_prepared_24k/manifest.csv")
    if not clinical.study_id.equals(ecg_manifest.study_id):
        raise ValueError("MIMIC clinical and ECG rows are misaligned")
    source_meta = json.loads((root / "artifacts/ecgfounder_ext_icd_prepared_24k/metadata.json").read_text())
    label_indices = [source_meta["labels"].index(name) for name in LABELS]
    y = np.asarray([[float(index in ast.literal_eval(value)) for index in label_indices]
                    for value in clinical.targets], dtype=np.float32)
    records = [{"age": row.age, "sex": "female" if row.gender == "F" else "male",
                "creatinine": row.creatinine_last, "fasting_blood_sugar": row.glucose_last}
               for row in clinical.itertuples()]
    x = feature_matrix(records)
    splits = clinical.split.to_numpy()
    train_idx, val_idx, test_idx = (np.flatnonzero(splits == split) for split in ("train", "val", "test"))
    if any(len(ix) == 0 for ix in (train_idx, val_idx, test_idx)):
        raise ValueError("Train, validation, and test rows are required")
    gb_models = []
    for j, label in enumerate(LABELS):
        gb = HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=15,
                                            learning_rate=.045, l2_regularization=5,
                                            early_stopping=False, random_state=42 + j)
        gb.fit(x[train_idx], y[train_idx, j])
        gb_models.append(gb)
        print(json.dumps({"trained_label": label}), flush=True)

    checkpoint = torch.load(models_dir / "best_multimodal_cvd.pt", map_location="cpu", weights_only=False)
    base = FusionModel(checkpoint["ecg_dim"], checkpoint["tab_dim"], len(LABELS), checkpoint["risk_head"])
    base.load_state_dict(checkpoint["state_dict"])
    adapter = torch.load(models_dir / "mimic_projection_adapter.pt", map_location="cpu", weights_only=False)
    model = FusionWithAdapter(base, checkpoint["ecg_dim"], checkpoint["tab_dim"], len(LABELS))
    model.adapter.load_state_dict(adapter["state_dict"])
    model.eval()
    transform = joblib.load(models_dir / "clinical_transform.joblib")
    tab = transform.transform(records)
    features = np.load(root / "artifacts/ecgfounder_ext_icd_features_24k/ecgfounder_features.npy", mmap_mode="r")
    calibration = json.loads((models_dir / "mimic_adapter_calibration.json").read_text())

    def mlp(ix: np.ndarray, modality: str) -> np.ndarray:
        chunks = []
        mask_value = float(modality == "ecg_clinical")
        with torch.inference_mode():
            for part in np.array_split(ix, max(1, int(np.ceil(len(ix) / 512)))):
                mask = torch.full((len(part), 1), mask_value)
                ecg = torch.from_numpy(np.asarray(features[part]).copy()) * mask
                logits, _ = model(ecg, torch.from_numpy(tab[part]), mask, torch.ones_like(mask))
                chunks.append(logits.numpy())
        return apply_adapter_calibration(np.concatenate(chunks), calibration["modalities"][modality])

    bundle = {"models": gb_models, "fields": FIELDS, "labels": LABELS, "alpha": {}, "thresholds": {},
              "source": "24k MIMIC; observed age/sex/creatinine/glucose plus derived eGFR"}
    results = {}
    for modality in ("clinical_only", "ecg_clinical"):
        val_mlp, test_mlp = mlp(val_idx, modality), mlp(test_idx, modality)
        val_gb = np.stack([m.predict_proba(x[val_idx])[:, 1] for m in gb_models], axis=1)
        val_scores = []
        for alpha in np.linspace(0, 1, 21):
            blended = (1 - alpha) * val_mlp + alpha * val_gb
            val_scores.append((score(y[val_idx], blended)["macro_auroc"], float(alpha)))
        best_auc, best_alpha = max(val_scores)
        bundle["alpha"][modality] = best_alpha
        val_prob = (1 - best_alpha) * val_mlp + best_alpha * val_gb
        cutoffs = thresholds(y[val_idx], val_prob)
        bundle["thresholds"][modality] = cutoffs.tolist()
        test_gb = np.stack([m.predict_proba(x[test_idx])[:, 1] for m in gb_models], axis=1)
        test_prob = (1 - best_alpha) * test_mlp + best_alpha * test_gb
        results[modality] = {"alpha": best_alpha,
                             "validation": score(y[val_idx], val_prob, cutoffs),
                             "test": score(y[test_idx], test_prob, cutoffs),
                             "mlp_test": score(y[test_idx], test_mlp, cutoffs),
                             "previous_baseline_test_macro_auroc": 0.7197704734973926 if modality == "clinical_only" else 0.860768831892169}
        print(json.dumps({"modality": modality, **results[modality]}), flush=True)
    output = models_dir / "clinical_stack.joblib"
    temporary = output.with_name("clinical_stack.tmp.joblib")
    bundle["results"] = results
    joblib.dump(bundle, temporary)
    os.replace(temporary, output)
    metrics_path = models_dir / "research_metrics.json"
    metrics = json.loads(metrics_path.read_text())
    metrics["clinical_stack_v2"] = results
    temp = metrics_path.with_name("research_metrics.tmp.json")
    temp.write_text(json.dumps(metrics, indent=2))
    os.replace(temp, metrics_path)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(r"D:\CVG Project"))
    args = parser.parse_args()
    print(json.dumps(train(args.project_root), indent=2))
