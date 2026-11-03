"""PTB-XL diagnostic training. Ten-year event risk requires separate outcome labels."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, roc_auc_score
from torch import nn
from torch.utils.data import DataLoader, Dataset
from .clinical_lifestyle_branch import ClinicalTransform
from .ecg_branch import load_official_founder, preprocess
from .fusion_model import FusionModel

LABELS = ("NORM", "MI", "STTC", "CD", "HYP")


def train_cached(root: Path, epochs: int, batch_size: int) -> None:
    """Train on the existing, aligned MIMIC ECGFounder and clinical artifacts."""
    import ast
    labels = ("I48", "I50", "I25", "I21", "I44")
    artifact = root / "artifacts"
    ecg_manifest = pd.read_csv(artifact / "ecgfounder_ext_icd_prepared_24k/manifest.csv")
    clinical = pd.read_csv(artifact / "clinical-ext-icd-prepared-24k/manifest.csv")
    if len(ecg_manifest) != len(clinical) or not ecg_manifest.study_id.equals(clinical.study_id):
        raise ValueError("ECG and clinical artifact rows do not align by study_id")
    features = np.load(artifact / "ecgfounder_ext_icd_features_24k/ecgfounder_features.npy", allow_pickle=False, mmap_mode="r")
    if features.shape != (len(clinical), 1024):
        raise ValueError(f"Unexpected ECGFounder feature shape: {features.shape}")
    source_meta = json.loads((artifact / "ecgfounder_ext_icd_prepared_24k/metadata.json").read_text())
    class_indices = [source_meta["labels"].index(name) for name in labels]
    targets = np.array([[float(i in ast.literal_eval(value)) for i in class_indices] for value in clinical.targets], dtype=np.float32)
    records = []
    for row in clinical.itertuples():
        records.append({"age": row.age, "sex": "female" if row.gender == "F" else "male",
                        "creatinine": row.creatinine_last, "fasting_blood_sugar": row.glucose_last})
    train_indices = np.flatnonzero(clinical.split.to_numpy() == "train")
    val_indices = np.flatnonzero(clinical.split.to_numpy() == "val")
    if not len(train_indices) or not len(val_indices):
        raise ValueError("Prepared data has no train/val split")
    transform = ClinicalTransform().fit([records[i] for i in train_indices])
    tab = transform.transform(records)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = FusionModel(1024, transform.output_dim, len(labels)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")
    best = -1.
    output = root / "models"
    output.mkdir(exist_ok=True)
    print(json.dumps({"source": "MIMIC cached ECGFounder", "train": len(train_indices),
                      "val": len(val_indices), "labels": labels, "device": device}), flush=True)
    for epoch in range(epochs):
        model.train()
        shuffled = np.random.default_rng(42 + epoch).permutation(train_indices)
        for offset in range(0, len(shuffled), batch_size):
            ix = shuffled[offset:offset + batch_size]
            if len(ix) < 2:
                continue
            ecg = torch.from_numpy(np.asarray(features[ix]).copy()).to(device)
            clinical_tensor = torch.from_numpy(tab[ix]).to(device)
            y = torch.from_numpy(targets[ix]).to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                logits, _ = model(ecg, clinical_tensor, torch.ones(len(ix), 1, device=device),
                                  torch.ones(len(ix), 1, device=device), True)
                loss = nn.functional.binary_cross_entropy_with_logits(logits, y)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        scheduler.step()
        model.eval()
        probabilities = []
        with torch.no_grad():
            for offset in range(0, len(val_indices), 512):
                ix = val_indices[offset:offset + 512]
                logits, _ = model(torch.from_numpy(np.asarray(features[ix]).copy()).to(device),
                                  torch.from_numpy(tab[ix]).to(device), torch.ones(len(ix), 1, device=device),
                                  torch.ones(len(ix), 1, device=device))
                probabilities.append(logits.sigmoid().cpu().numpy())
        p, y = np.concatenate(probabilities), targets[val_indices]
        aucs = [roc_auc_score(y[:, j], p[:, j]) for j in range(len(labels)) if len(np.unique(y[:, j])) == 2]
        metrics = {"macro_auroc": float(np.mean(aucs)),
                   "macro_f1_at_0_5": float(f1_score(y, p >= .5, average="macro", zero_division=0))}
        print(json.dumps({"epoch": epoch + 1, **metrics}), flush=True)
        if metrics["macro_auroc"] > best:
            best = metrics["macro_auroc"]
            torch.save({"state_dict": model.cpu().state_dict(), "labels": labels,
                        "ecg_dim": 1024, "tab_dim": transform.output_dim,
                        "risk_head": False, "source": "MIMIC cached ECGFounder",
                        "trained_clinical_fields": ("age", "sex", "creatinine", "fasting_blood_sugar"),
                        "validation": metrics},
                       output / "best_multimodal_cvd.pt")
            joblib.dump(transform, output / "clinical_transform.joblib")
            model.to(device)


class PtbDataset(Dataset):
    def __init__(self, frame, root, transform, code_map):
        self.frame, self.root, self.transform, self.code_map = frame.reset_index(drop=True), root, transform, code_map

    def __len__(self):
        return len(self.frame)

    def __getitem__(self, index):
        import ast
        import wfdb
        row = self.frame.iloc[index]
        signal, fields = wfdb.rdsamp(str(self.root / row.filename_hr))
        ecg = preprocess(signal, int(fields["fs"]), tuple(fields["sig_name"]))
        record = {"age": None if pd.isna(row.age) else row.age,
                  "sex": "female" if row.sex == 1 else "male"}
        tab = self.transform.transform([record])[0]
        codes = ast.literal_eval(row.scp_codes)
        classes = {self.code_map[code] for code, certainty in codes.items() if code in self.code_map and certainty >= 50}
        targets = np.array([float(label in classes) for label in LABELS], np.float32)
        risk = np.float32(row.cvd_event_10y) if "cvd_event_10y" in self.frame.columns else np.float32(-1)
        return torch.from_numpy(ecg), torch.from_numpy(tab), torch.from_numpy(targets), torch.tensor([risk])


def evaluate(model, encoder, loader, device):
    model.eval()
    actual, predicted, risk_actual, risk_predicted = [], [], [], []
    with torch.no_grad():
        for ecg, tab, target, risk_target in loader:
            ecg, tab = ecg.to(device), tab.to(device)
            _, embedding = encoder(ecg)
            logits, risk_logits = model(embedding, tab, torch.ones(len(tab), 1, device=device), torch.ones(len(tab), 1, device=device))
            actual.append(target.numpy())
            predicted.append(logits.sigmoid().cpu().numpy())
            if risk_logits is not None:
                risk_actual.append(risk_target.numpy())
                risk_predicted.append(risk_logits.sigmoid().cpu().numpy())
    y, p = np.concatenate(actual), np.concatenate(predicted)
    aucs = [roc_auc_score(y[:, k], p[:, k]) for k in range(y.shape[1]) if len(np.unique(y[:, k])) == 2]
    metrics = {"macro_auroc": float(np.mean(aucs)), "macro_f1_at_0_5": float(f1_score(y, p >= .5, average="macro", zero_division=0))}
    if risk_actual:
        ry, rp = np.concatenate(risk_actual).ravel(), np.concatenate(risk_predicted).ravel()
        metrics["risk_brier"] = float(np.mean((ry - rp) ** 2))
        if len(np.unique(ry)) == 2:
            metrics["risk_auroc"] = float(roc_auc_score(ry, rp))
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(r"D:\CVG Project"))
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--risk-csv", type=Path, help="Adjudicated 10-year follow-up CSV: ecg_id,cvd_event_10y (0/1), matching PTB records")
    parser.add_argument("--source", choices=("auto", "ptb", "cached-mimic"), default="auto")
    args = parser.parse_args()
    root = args.project_root
    if args.source == "cached-mimic" or (args.source == "auto" and args.risk_csv is None and (root / "artifacts/ecgfounder_ext_icd_features_24k/ecgfounder_features.npy").is_file()):
        train_cached(root, args.epochs, args.batch_size)
        return
    ptb = root / "ptb-xl-1.0.1"
    frame = pd.read_csv(ptb / "ptbxl_database.csv")
    if args.risk_csv:
        risk_frame = pd.read_csv(args.risk_csv, usecols=["ecg_id", "cvd_event_10y"])
        if risk_frame.ecg_id.duplicated().any() or not risk_frame.cvd_event_10y.isin([0, 1]).all():
            raise ValueError("Risk labels require unique ECG IDs and binary 10-year outcomes")
        frame = frame.merge(risk_frame, on="ecg_id", validate="one_to_one")
        if len(frame) < 1000:
            raise ValueError("At least 1000 matched, labeled ECGs are required for risk training")
    statements = pd.read_csv(ptb / "scp_statements.csv", index_col=0)
    code_map = statements[statements.diagnostic == 1].diagnostic_class.dropna().to_dict()
    train, val = frame[frame.strat_fold <= 8], frame[frame.strat_fold == 9]
    transform = ClinicalTransform().fit([{"age": None if pd.isna(r.age) else r.age, "sex": "female" if r.sex == 1 else "male"} for r in train.itertuples()])
    train_loader = DataLoader(PtbDataset(train, ptb, transform, code_map), batch_size=args.batch_size, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(PtbDataset(val, ptb, transform, code_map), batch_size=args.batch_size, num_workers=0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    encoder = load_official_founder(root / "pretrained/ECGFounder/12_lead_ECGFounder.pth", Path(__file__).parent / "vendor/ECGFounder").to(device)
    for parameter in encoder.parameters():
        parameter.requires_grad_(False)
    model = FusionModel(1024, transform.output_dim, len(LABELS), risk_head=bool(args.risk_csv)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")
    best = -1.0
    output = root / "models"
    output.mkdir(exist_ok=True)
    for epoch in range(args.epochs):
        model.train()
        for ecg, tab, target, risk_target in train_loader:
            ecg, tab, target, risk_target = ecg.to(device), tab.to(device), target.to(device), risk_target.to(device)
            with torch.no_grad():
                _, embedding = encoder(ecg)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                logits, risk_logits = model(embedding, tab, torch.ones(len(tab), 1, device=device), torch.ones(len(tab), 1, device=device), True)
                loss = nn.functional.binary_cross_entropy_with_logits(logits, target)
                if risk_logits is not None:
                    loss = loss + nn.functional.mse_loss(risk_logits.sigmoid(), risk_target)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        schedule.step()
        metrics = evaluate(model, encoder, val_loader, device)
        print(json.dumps({"epoch": epoch + 1, **metrics}), flush=True)
        if metrics["macro_auroc"] > best:
            best = metrics["macro_auroc"]
            torch.save({"state_dict": model.cpu().state_dict(), "labels": LABELS,
                        "ecg_dim": 1024, "tab_dim": transform.output_dim,
                        "risk_head": bool(args.risk_csv), "validation": metrics}, output / "best_multimodal_cvd.pt")
            joblib.dump(transform, output / "clinical_transform.joblib")
            model.to(device)
    print("Checkpoint saved. Risk head trained only if adjudicated longitudinal outcomes were supplied.")


if __name__ == "__main__":
    main()
