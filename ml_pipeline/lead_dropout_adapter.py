"""Experimental lead-mask-conditioned adapter for 1- and 6-lead ECGFounder input."""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from torch import nn

from .ecg_branch import load_ecg, load_official_founder

LABELS = ("NORM", "MI", "STTC", "CD", "HYP")


class LeadAdapter(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(1036, 128), nn.LayerNorm(128), nn.GELU(),
                                 nn.Dropout(.2), nn.Linear(128, 1024))

    def forward(self, embedding: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        return embedding + self.net(torch.cat((embedding, mask), dim=1))


def mask_for_mode(mode: str) -> np.ndarray:
    count = {"1-lead": 1, "6-lead": 6, "12-lead": 12}[mode]
    result = np.zeros(12, np.float32)
    result[:count] = 1
    return result


def _subset(indices: np.ndarray, targets: np.ndarray, count: int, seed: int) -> np.ndarray:
    if len(indices) <= count:
        return indices
    dominant = np.where(targets[indices].any(axis=1), targets[indices].argmax(axis=1), 5)
    try:
        _, selected = train_test_split(indices, test_size=count, stratify=dominant, random_state=seed)
    except ValueError:
        selected = np.random.default_rng(seed).choice(indices, count, replace=False)
    return np.sort(selected)


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean([roc_auc_score(y[:, j], p[:, j]) for j in range(y.shape[1])
                          if len(np.unique(y[:, j])) == 2]))


def train(root: Path, train_rows: int = 200, val_rows: int = 50, test_rows: int = 50,
          epochs: int = 20, batch_size: int = 8, sleep_ms: int = 100) -> dict:
    from .slow_train import prepare_manifest, lower_priority
    torch.set_num_threads(2)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass  # slow_train already configured interop threads during import
    lower_priority()
    models = root / "models"
    frame = prepare_manifest(root)
    with np.load(models / "ptbxl_cached_embeddings.npz", allow_pickle=False) as data:
        ids = data["ecg_id"]
        if not np.array_equal(ids, frame.ecg_id.to_numpy()):
            raise ValueError("PTB-XL metadata is misaligned with cached vectors")
        full = data["embeddings"].astype(np.float32)
        targets = data["labels_5class"].astype(np.float32)
        folds = data["strat_fold"]
        valid = data["label_valid"] & data["processed_mask"]
        ages = data["age"].astype(np.float32)
        sexes = data["sex"].astype(np.float32)
    selected = np.concatenate((_subset(np.flatnonzero(valid & (folds <= 8)), targets, train_rows, 41),
                               _subset(np.flatnonzero(valid & (folds == 9)), targets, val_rows, 42),
                               _subset(np.flatnonzero(valid & (folds == 10)), targets, test_rows, 43)))
    print(json.dumps({"selected_records": len(selected), "fold_counts": {
        "train": int((folds[selected] <= 8).sum()), "val": int((folds[selected] == 9).sum()),
        "test": int((folds[selected] == 10).sum())}}), flush=True)
    encoder = load_official_founder(root / "pretrained/ECGFounder/12_lead_ECGFounder.pth",
                                    Path(__file__).parent / "vendor/ECGFounder")
    encoder.eval()
    partial = np.zeros((len(selected), 2, 1024), np.float32)
    for offset in range(0, len(selected), batch_size):
        batch = selected[offset:offset + batch_size]
        waveforms = [load_ecg((root / "ptb-xl-1.0.1" / frame.iloc[ix].filename_hr).with_suffix(".hea"))
                     for ix in batch]
        for mode_index, count in enumerate((1, 6)):
            signals = np.stack(waveforms)
            signals[:, count:, :] = 0
            with torch.inference_mode():
                _, embeddings = encoder(torch.from_numpy(signals))
            partial[offset:offset + len(batch), mode_index] = embeddings.numpy()
            time.sleep(sleep_ms / 1000)
        if offset % (batch_size * 5) == 0 or offset + batch_size >= len(selected):
            print(json.dumps({"extracted_records": min(offset + batch_size, len(selected)),
                              "selected_records": len(selected)}), flush=True)
    head_checkpoint = torch.load(models / "ptbxl_superclass_head.pt", map_location="cpu", weights_only=False)
    head = nn.Sequential(nn.Linear(head_checkpoint["input_dim"], 256), nn.SiLU(),
                         nn.Dropout(.2), nn.Linear(256, len(LABELS)))
    head.load_state_dict(head_checkpoint["state_dict"])
    head.eval()
    for parameter in head.parameters():
        parameter.requires_grad_(False)
    mean = head_checkpoint["mean"].astype(np.float32)
    scale = head_checkpoint["scale"].astype(np.float32)
    full_z = (full[selected] - mean) / scale
    partial_z = (partial - mean) / scale
    aux = np.column_stack(((np.nan_to_num(ages[selected], nan=float(head_checkpoint["age_median"])) - 55) / 20,
                           np.nan_to_num(sexes[selected], nan=.5))).astype(np.float32)
    n = len(selected)
    x = np.concatenate((partial_z[:, 0], partial_z[:, 1]), axis=0)
    target_z = np.concatenate((full_z, full_z), axis=0)
    masks = np.concatenate((np.tile(mask_for_mode("1-lead"), (n, 1)),
                            np.tile(mask_for_mode("6-lead"), (n, 1))), axis=0)
    aux2 = np.concatenate((aux, aux), axis=0)
    y = np.concatenate((targets[selected], targets[selected]), axis=0)
    fold2 = np.concatenate((folds[selected], folds[selected]), axis=0)
    x_t, target_t, mask_t, aux_t, y_t = (torch.from_numpy(arr.astype(np.float32))
                                        for arr in (x, target_z, masks, aux2, y))
    adapter = LeadAdapter()
    optimizer = torch.optim.AdamW(adapter.parameters(), lr=3e-4, weight_decay=.01)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    train_idx = np.flatnonzero(fold2 <= 8)
    val_idx = np.flatnonzero(fold2 == 9)
    best_state, best_score = None, -1.0
    for epoch in range(epochs):
        adapter.train()
        for batch in np.array_split(np.random.default_rng(100 + epoch).permutation(train_idx),
                                    max(1, int(np.ceil(len(train_idx) / 32)))):
            adapted = adapter(x_t[batch], mask_t[batch])
            logits = head(torch.cat((adapted, aux_t[batch]), dim=1))
            bce = nn.functional.binary_cross_entropy_with_logits(logits, y_t[batch])
            loss = .02 * nn.functional.mse_loss(adapted, target_t[batch]) + bce
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        schedule.step()
        adapter.eval()
        with torch.inference_mode():
            adjusted = adapter(x_t[val_idx], mask_t[val_idx])
            p = head(torch.cat((adjusted, aux_t[val_idx]), dim=1)).sigmoid().numpy()
        metric = _auc(y[val_idx], p)
        if metric > best_score:
            best_score = metric
            best_state = {key: value.detach().clone() for key, value in adapter.state_dict().items()}
        print(json.dumps({"epoch": epoch + 1, "val_macro_auroc": metric}), flush=True)
    adapter.load_state_dict(best_state)
    adapter.eval()
    scores = {}
    with torch.inference_mode():
        for mode_index, mode in enumerate(("1-lead", "6-lead")):
            val = np.flatnonzero((fold2 == 9) & (np.arange(2 * n) // n == mode_index))
            test = np.flatnonzero((fold2 == 10) & (np.arange(2 * n) // n == mode_index))
            raw_val = head(torch.cat((x_t[val], aux_t[val]), dim=1)).sigmoid().numpy()
            adapted_val = head(torch.cat((adapter(x_t[val], mask_t[val]), aux_t[val]), dim=1)).sigmoid().numpy()
            raw_test = head(torch.cat((x_t[test], aux_t[test]), dim=1)).sigmoid().numpy()
            adapted_test = head(torch.cat((adapter(x_t[test], mask_t[test]), aux_t[test]), dim=1)).sigmoid().numpy()
            scores[mode] = {"val_auroc_raw": _auc(y[val], raw_val),
                            "val_auroc_adapted": _auc(y[val], adapted_val),
                            "test_auroc_raw": _auc(y[test], raw_test),
                            "test_auroc_adapted": _auc(y[test], adapted_test),
                            "test_rows": len(test)}
            scores[mode]["use_adapter"] = scores[mode]["val_auroc_adapted"] > scores[mode]["val_auroc_raw"]
    checkpoint = {"state_dict": best_state, "metrics": scores, "training_records": n,
                  "architecture": "lead-mask-conditioned residual 1036-128-1024"}
    temporary = models / "lead_dropout_adapter.tmp.pt"
    torch.save(checkpoint, temporary)
    os.replace(temporary, models / "lead_dropout_adapter.pt")
    metrics_path = models / "research_metrics.json"
    metrics = json.loads(metrics_path.read_text())
    metrics["lead_dropout_adapter_v2"] = {"modes": scores, "training_records": n,
                                            "limitations": "Small stratified subset; partial-lead outputs are experimental and not clinically validated."}
    temp = models / "research_metrics.tmp.json"
    temp.write_text(json.dumps(metrics, indent=2))
    os.replace(temp, metrics_path)
    return scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(r"D:\CVG Project"))
    parser.add_argument("--train-rows", type=int, default=200)
    parser.add_argument("--val-rows", type=int, default=50)
    parser.add_argument("--test-rows", type=int, default=50)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--sleep-ms", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(train(args.project_root, args.train_rows, args.val_rows, args.test_rows,
                           args.epochs, args.batch_size, args.sleep_ms), indent=2))
