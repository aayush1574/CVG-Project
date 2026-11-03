"""Class-balanced low-rank bottleneck experiments on cached PTB-XL and MIMIC vectors."""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"

import argparse
import ast
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, roc_auc_score
from torch import nn

from .fusion_model import FusionModel
from .mimic_adapter_inference import FusionWithAdapter


def lower_priority():
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000)


class Bottleneck(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(dim, 128), nn.LayerNorm(128), nn.GELU(),
                                 nn.Dropout(.2), nn.Linear(128, dim))
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self, x):
        return x + self.net(x)


class PtbProjectedHead(nn.Module):
    def __init__(self, head: nn.Module, projection: Bottleneck):
        super().__init__()
        self.head = head
        self.projection = projection

    def forward(self, x):
        vector = self.projection(x[:, :1024])
        return self.head(torch.cat((vector, x[:, 1024:]), dim=1))


class MimicProjectedModel(nn.Module):
    def __init__(self, model: FusionWithAdapter, ecg_dim: int, tab_dim: int):
        super().__init__()
        self.model = model
        self.ecg_dim = ecg_dim
        self.tab_dim = tab_dim
        self.projection = Bottleneck(ecg_dim + tab_dim)

    def forward(self, ecg, tab, mask_ecg, mask_tab):
        combined = torch.cat((ecg * mask_ecg, tab), dim=1)
        adapted = self.projection(combined)
        ecg_new = adapted[:, :self.ecg_dim] * mask_ecg
        tab_new = adapted[:, self.ecg_dim:]
        return self.model(ecg_new, tab_new, mask_ecg, mask_tab)


def _metric(y, p):
    auc = [roc_auc_score(y[:, j], p[:, j]) for j in range(y.shape[1]) if len(np.unique(y[:, j])) == 2]
    f1 = f1_score(y, p >= .5, average=None, zero_division=0)
    return {"macro_auroc": float(np.mean(auc)), "macro_f1_at_0_5": float(np.mean(f1)),
            "per_class_f1": [float(v) for v in f1], "rows": int(len(y))}


def _focal(logits, target, positive_weight):
    prob = logits.sigmoid()
    pt = prob * target + (1 - prob) * (1 - target)
    gamma = torch.where(target > 0, 1.0, 3.0)
    weights = torch.where(target > 0, positive_weight, 1.0)
    return (nn.functional.binary_cross_entropy_with_logits(logits, target, reduction="none")
            * (1 - pt).pow(gamma) * weights).mean()


def train_ptb(root: Path, epochs: int = 10) -> dict:
    models = root / "models"
    with np.load(models / "ptbxl_cached_embeddings.npz", allow_pickle=False) as data:
        vectors = data["embeddings"].astype(np.float32)
        labels = data["labels_5class"].astype(np.float32)
        fold = data["strat_fold"]
        mask = data["label_valid"] & data["processed_mask"]
        age = data["age"]
        sex = data["sex"]
    checkpoint = torch.load(models / "ptbxl_superclass_head.pt", map_location="cpu", weights_only=False)
    if "projection_state_dict" in checkpoint:
        raise ValueError("PTB head already contains a bottleneck; do not stack another")
    head = nn.Sequential(nn.Linear(checkpoint["input_dim"], 256), nn.SiLU(),
                         nn.Dropout(.2), nn.Linear(256, 5))
    head.load_state_dict(checkpoint["state_dict"])
    head.eval()
    for parameter in head.parameters():
        parameter.requires_grad_(False)
    normalized = (vectors - checkpoint["mean"]) / checkpoint["scale"]
    aux = np.column_stack(((np.nan_to_num(age, nan=float(checkpoint["age_median"])) - 55) / 20,
                           np.nan_to_num(sex, nan=.5))).astype(np.float32)
    x = torch.from_numpy(np.column_stack((normalized, aux)).astype(np.float32))
    y = torch.from_numpy(labels)
    train = np.flatnonzero(mask & (fold <= 8))
    val = np.flatnonzero(mask & (fold == 9))
    test = np.flatnonzero(mask & (fold == 10))
    projection = Bottleneck(1024)
    model = PtbProjectedHead(head, projection)
    optimizer = torch.optim.AdamW(projection.parameters(), lr=2e-4, weight_decay=.01)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    prevalence = labels[train].mean(axis=0)
    positive_weight = torch.from_numpy(np.clip((1 - prevalence) / np.maximum(prevalence, .01), 1, 4).astype(np.float32))
    with torch.inference_mode():
        baseline_val = torch.cat([head(part) for part in x[val].split(512)]).sigmoid().numpy()
    baseline = _metric(labels[val], baseline_val)
    best_state, best_val = None, baseline
    for epoch in range(epochs):
        model.train(); head.eval()
        for ix in np.array_split(np.random.default_rng(202 + epoch).permutation(train),
                                 max(1, int(np.ceil(len(train) / 128)))):
            logits = model(x[ix])
            loss = _focal(logits, y[ix], positive_weight)
            optimizer.zero_grad(set_to_none=True)
            loss.backward(); optimizer.step()
        schedule.step(); model.eval()
        with torch.inference_mode():
            val_p = torch.cat([model(part) for part in x[val].split(512)]).sigmoid().numpy()
        current = _metric(labels[val], val_p)
        print(json.dumps({"ptb_epoch": epoch + 1, "validation": current["macro_auroc"]}), flush=True)
        if (current["macro_auroc"] > best_val["macro_auroc"]
                and current["macro_f1_at_0_5"] >= baseline["macro_f1_at_0_5"]
                and sum(current["per_class_f1"][j] for j in (3, 4)) >=
                    sum(baseline["per_class_f1"][j] for j in (3, 4))):
            best_state = {k: v.detach().clone() for k, v in projection.state_dict().items()}
            best_val = current
    promoted = best_state is not None
    if promoted:
        projection.load_state_dict(best_state); model.eval()
        with torch.inference_mode():
            test_p = torch.cat([model(part) for part in x[test].split(512)]).sigmoid().numpy()
        candidate_test = _metric(labels[test], test_p)
        candidate = {**checkpoint, "projection_state_dict": best_state,
                     "bottleneck_validation": best_val, "bottleneck_test": candidate_test}
        temp = models / "ptbxl_superclass_head.tmp.pt"
        torch.save(candidate, temp)
        os.replace(temp, models / "ptbxl_superclass_head.pt")
    else:
        candidate_test = None
    return {"baseline_validation": baseline, "candidate_validation": best_val,
            "candidate_test": candidate_test, "promoted": promoted,
            "minority_labels": ["CD", "HYP"]}


def train_mimic(root: Path, epochs: int = 5) -> dict:
    models = root / "models"
    clinical = pd.read_csv(root / "artifacts/clinical-ext-icd-prepared-24k/manifest.csv")
    ecg_manifest = pd.read_csv(root / "artifacts/ecgfounder_ext_icd_prepared_24k/manifest.csv")
    if not clinical.study_id.equals(ecg_manifest.study_id):
        raise ValueError("MIMIC rows are misaligned")
    metadata = json.loads((root / "artifacts/ecgfounder_ext_icd_prepared_24k/metadata.json").read_text())
    checkpoint = torch.load(models / "best_multimodal_cvd.pt", map_location="cpu", weights_only=False)
    labels = checkpoint["labels"]
    indices = [metadata["labels"].index(name) for name in labels]
    targets = np.asarray([[float(i in ast.literal_eval(item)) for i in indices]
                          for item in clinical.targets], np.float32)
    records = [{"age": row.age, "sex": "female" if row.gender == "F" else "male",
                "creatinine": row.creatinine_last, "fasting_blood_sugar": row.glucose_last}
               for row in clinical.itertuples()]
    tab = torch.from_numpy(joblib.load(models / "clinical_transform.joblib").transform(records))
    ecg = np.load(root / "artifacts/ecgfounder_ext_icd_features_24k/ecgfounder_features.npy", mmap_mode="r")
    base = FusionModel(checkpoint["ecg_dim"], checkpoint["tab_dim"], len(labels), checkpoint["risk_head"])
    base.load_state_dict(checkpoint["state_dict"])
    old = torch.load(models / "mimic_projection_adapter.pt", map_location="cpu", weights_only=False)
    wrapped = FusionWithAdapter(base, checkpoint["ecg_dim"], checkpoint["tab_dim"], len(labels))
    wrapped.adapter.load_state_dict(old["state_dict"])
    wrapped.eval()
    for parameter in wrapped.parameters():
        parameter.requires_grad_(False)
    model = MimicProjectedModel(wrapped, checkpoint["ecg_dim"], checkpoint["tab_dim"])
    optimizer = torch.optim.AdamW(model.projection.parameters(), lr=1e-4, weight_decay=.01)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    split = clinical.split.to_numpy()
    train = np.flatnonzero(split == "train")
    val = np.flatnonzero(split == "val")
    test = np.flatnonzero(split == "test")
    positive_weight = torch.from_numpy(np.clip((1 - targets[train].mean(axis=0)) /
                                               np.maximum(targets[train].mean(axis=0), .01), 1, 4).astype(np.float32))

    def predict(indices, use_ecg, projected):
        outputs = []
        model.eval()
        with torch.inference_mode():
            for batch in np.array_split(indices, max(1, int(np.ceil(len(indices) / 512)))):
                mask = torch.full((len(batch), 1), float(use_ecg))
                vectors = torch.from_numpy(np.asarray(ecg[batch]).copy()) * mask
                fn = model if projected else wrapped
                logits, _ = fn(vectors, tab[batch], mask, torch.ones_like(mask))
                outputs.append(logits.sigmoid().numpy())
        return np.concatenate(outputs)

    baseline = {mode: _metric(targets[val], predict(val, use_ecg, False))
                for mode, use_ecg in (("ecg_clinical", True), ("clinical_only", False))}
    best_state, best_val = None, baseline
    for epoch in range(epochs):
        model.train(); wrapped.eval()
        for offset, batch in enumerate(np.array_split(np.random.default_rng(330 + epoch).permutation(train),
                                                       max(1, int(np.ceil(len(train) / 256))))):
            mask = torch.from_numpy((np.random.default_rng(epoch * 1000 + offset).random((len(batch), 1)) > .3).astype(np.float32))
            vectors = torch.from_numpy(np.asarray(ecg[batch]).copy()) * mask
            logits, _ = model(vectors, tab[batch], mask, torch.ones_like(mask))
            loss = _focal(logits, torch.from_numpy(targets[batch]), positive_weight)
            optimizer.zero_grad(set_to_none=True)
            loss.backward(); optimizer.step()
            time.sleep(.01)
        schedule.step()
        current = {mode: _metric(targets[val], predict(val, use_ecg, True))
                   for mode, use_ecg in (("ecg_clinical", True), ("clinical_only", False))}
        print(json.dumps({"mimic_epoch": epoch + 1, "validation": {k: v["macro_auroc"] for k, v in current.items()}}), flush=True)
        if (current["ecg_clinical"]["macro_auroc"] > best_val["ecg_clinical"]["macro_auroc"]
                and current["clinical_only"]["macro_auroc"] >= best_val["clinical_only"]["macro_auroc"]
                and all(current[mode]["macro_f1_at_0_5"] >= baseline[mode]["macro_f1_at_0_5"]
                        for mode in ("ecg_clinical", "clinical_only"))):
            best_state = {k: v.detach().clone() for k, v in model.projection.state_dict().items()}
            best_val = current
    promoted = best_state is not None
    testing = None
    if promoted:
        model.projection.load_state_dict(best_state)
        testing = {mode: _metric(targets[test], predict(test, use_ecg, True))
                   for mode, use_ecg in (("ecg_clinical", True), ("clinical_only", False))}
        # Runtime calibration and ONNX export require a new validation pass;
        # retain the live adapter until both are fitted and verified.
        temp = models / "mimic_bottleneck_candidate.tmp.pt"
        torch.save({"state_dict": best_state, "validation": best_val,
                    "test": testing, "labels": labels}, temp)
        os.replace(temp, models / "mimic_bottleneck_candidate.pt")
    return {"baseline_validation": baseline, "candidate_validation": best_val,
            "candidate_test": testing, "candidate_saved": promoted,
            "serving_promoted": False, "minority_labels": ["I21", "I44"]}


def train(root: Path, ptb_epochs: int, mimic_epochs: int, skip_ptb: bool = False) -> dict:
    torch.set_num_threads(2)
    try: torch.set_num_interop_threads(1)
    except RuntimeError: pass
    lower_priority()
    result = {"ptb": {"skipped": True} if skip_ptb else train_ptb(root, ptb_epochs),
              "mimic": train_mimic(root, mimic_epochs)}
    path = root / "models/research_metrics.json"
    metrics = json.loads(path.read_text())
    metrics["bottleneck_finetune_v2"] = result
    temp = path.with_name("research_metrics.tmp.json")
    temp.write_text(json.dumps(metrics, indent=2))
    os.replace(temp, path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(r"D:\CVG Project"))
    parser.add_argument("--ptb-epochs", type=int, default=10)
    parser.add_argument("--mimic-epochs", type=int, default=5)
    parser.add_argument("--skip-ptb", action="store_true")
    args = parser.parse_args()
    print(json.dumps(train(args.project_root, args.ptb_epochs, args.mimic_epochs, args.skip_ptb), indent=2))
