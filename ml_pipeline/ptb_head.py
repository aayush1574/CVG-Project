"""Frozen ECGFounder embedding cache and PTB-XL five-superclass head."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset

from .ecg_branch import load_ecg, load_official_founder

LABELS = ("NORM", "MI", "STTC", "CD", "HYP")
ROOT = Path(r"D:\CVG Project")


class Waveforms(Dataset):
    def __init__(self, frame: pd.DataFrame, root: Path):
        self.frame = frame.reset_index(drop=True)
        self.root = root

    def __len__(self):
        return len(self.frame)

    def __getitem__(self, index):
        row = self.frame.iloc[index]
        return torch.from_numpy(load_ecg((self.root / row.filename_hr).with_suffix(".hea"))), torch.tensor(index)


def select_subset(frame: pd.DataFrame, counts=(2400, 300, 300)) -> pd.DataFrame:
    chosen = []
    for split, count in zip(("train", "val", "test"), counts):
        part = frame[frame.split == split].copy()
        if len(part) < count:
            raise ValueError(f"Only {len(part)} records in {split}, need {count}")
        y = part[list(LABELS)].to_numpy()
        dominant = np.where(y.any(axis=1), y.argmax(axis=1), len(LABELS))
        try:
            _, selected = train_test_split(np.arange(len(part)), test_size=count,
                                           stratify=dominant, random_state=42)
        except ValueError:
            selected = np.random.default_rng(42).choice(len(part), count, replace=False)
        chosen.append(part.iloc[selected])
    return pd.concat(chosen, ignore_index=True)


def extract_embeddings(root: Path, cache: Path, workers: int, batch_size: int) -> None:
    manifest = pd.read_csv(root / "artifacts/ptb/manifest.csv")
    source = pd.read_csv(root / "ptb-xl-1.0.1/ptbxl_database.csv")[["ecg_id", "filename_hr"]]
    frame = select_subset(manifest.merge(source, on="ecg_id", validate="one_to_one"))
    loader = DataLoader(Waveforms(frame, root / "ptb-xl-1.0.1"), batch_size=batch_size,
                        num_workers=workers, persistent_workers=workers > 0)
    model = load_official_founder(root / "pretrained/ECGFounder/12_lead_ECGFounder.pth",
                                  Path(__file__).parent / "vendor/ECGFounder")
    model.eval()
    torch.set_num_threads(max(1, min(8, torch.get_num_threads())))
    embeddings = np.zeros((len(frame), 1024), np.float32)
    start = time.monotonic()
    with torch.inference_mode():
        for batch, (signals, indices) in enumerate(loader, 1):
            _, features = model(signals)
            embeddings[indices.numpy()] = features.numpy()
            if batch % 10 == 0 or batch == len(loader):
                print(json.dumps({"embedded": min(batch * batch_size, len(frame)),
                                  "total": len(frame), "elapsed_seconds": round(time.monotonic() - start, 1)}), flush=True)
    cache.parent.mkdir(exist_ok=True)
    np.savez_compressed(cache, embeddings=embeddings, targets=frame[list(LABELS)].to_numpy(np.float32),
                        split=frame.split.to_numpy(dtype="U8"), ecg_id=frame.ecg_id.to_numpy(), labels=np.array(LABELS))


def train_head(cache: Path, output: Path, epochs: int) -> None:
    data = np.load(cache, allow_pickle=False)
    x, y, split = data["embeddings"], data["targets"], data["split"]
    scaler = StandardScaler().fit(x[split == "train"])
    x = scaler.transform(x).astype(np.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = torch.nn.Sequential(torch.nn.Linear(1024, 256), torch.nn.SiLU(),
                                torch.nn.Dropout(.2), torch.nn.Linear(256, len(LABELS))).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
    best = -1.
    xt = torch.from_numpy(x[split == "train"]).to(device)
    yt = torch.from_numpy(y[split == "train"]).to(device)
    xv = torch.from_numpy(x[split == "val"]).to(device)
    for epoch in range(epochs):
        model.train()
        for indices in torch.randperm(len(xt), device=device).split(128):
            logits = model(xt[indices])
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, yt[indices])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            p = model(xv).sigmoid().cpu().numpy()
        truth = y[split == "val"]
        auc = float(np.mean([roc_auc_score(truth[:, j], p[:, j]) for j in range(len(LABELS)) if len(np.unique(truth[:, j])) == 2]))
        print(json.dumps({"ptb_epoch": epoch + 1, "val_macro_auroc": auc}), flush=True)
        if auc > best:
            best = auc
            torch.save({"state_dict": model.cpu().state_dict(), "mean": scaler.mean_.astype(np.float32),
                        "scale": scaler.scale_.astype(np.float32), "labels": LABELS,
                        "validation_macro_auroc": auc, "subset_size": len(x)}, output)
            model.to(device)
    checkpoint = torch.load(output, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    with torch.no_grad():
        p = model(torch.from_numpy(x[split == "test"])).sigmoid().numpy()
    truth = y[split == "test"]
    metrics = {"test_macro_auroc": float(np.mean([roc_auc_score(truth[:, j], p[:, j]) for j in range(len(LABELS)) if len(np.unique(truth[:, j])) == 2])),
               "test_macro_f1_at_0_5": float(f1_score(truth, p >= .5, average="macro", zero_division=0))}
    print(json.dumps(metrics), flush=True)
    output.with_suffix(".metrics.json").write_text(json.dumps(metrics, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=15)
    args = parser.parse_args()
    cache = args.project_root / "models/ptbxl_cached_embeddings.npz"
    output = args.project_root / "models/ptbxl_superclass_head.pt"
    if not cache.exists():
        extract_embeddings(args.project_root, cache, args.workers, args.batch_size)
    train_head(cache, output, args.epochs)


if __name__ == "__main__":
    main()
