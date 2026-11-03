"""Low-priority, resumable ECGFounder extraction and incremental research heads."""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"

import argparse
import ast
import ctypes
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, roc_auc_score
from torch import nn

from .ecg_branch import load_ecg, load_official_founder

LABELS = ("NORM", "MI", "STTC", "CD", "HYP")
ROOT = Path(r"D:\CVG Project")
torch.set_num_threads(2)
torch.set_num_interop_threads(1)


def lower_priority() -> None:
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.SetPriorityClass.restype = ctypes.c_int
        if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00004000):
            raise OSError("Could not set BELOW_NORMAL_PRIORITY_CLASS")


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.stem + ".tmp" + path.suffix)
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def atomic_torch(path: Path, value: dict) -> None:
    temporary = path.with_name(path.stem + ".tmp" + path.suffix)
    torch.save(value, temporary)
    os.replace(temporary, path)


def prepare_manifest(root: Path) -> pd.DataFrame:
    source = root / "ptb-xl-1.0.1"
    frame = pd.read_csv(source / "ptbxl_database.csv")
    statements = pd.read_csv(source / "scp_statements.csv", index_col=0)
    mapping = statements.loc[statements.diagnostic == 1, "diagnostic_class"].dropna().to_dict()
    if frame.ecg_id.duplicated().any() or not frame.strat_fold.between(1, 10).all():
        raise ValueError("Invalid PTB-XL ID or official fold")
    frame = frame.sort_values("ecg_id").reset_index(drop=True)
    targets = []
    valid = []
    for raw in frame.scp_codes:
        codes = ast.literal_eval(raw)
        classes = {mapping[code] for code, certainty in codes.items() if code in mapping and certainty >= 50}
        targets.append([float(label in classes) for label in LABELS])
        valid.append(bool(classes))
    frame["labels_5class"] = targets
    frame["label_valid"] = valid
    return frame


def load_cache(frame: pd.DataFrame, path: Path) -> dict[str, np.ndarray]:
    total = len(frame)
    ids = frame.ecg_id.to_numpy(np.int64)
    labels = np.asarray(frame.labels_5class.tolist(), dtype=np.float32)
    age = pd.to_numeric(frame.age, errors="coerce").to_numpy(np.float32)
    sex = pd.to_numeric(frame.sex, errors="coerce").to_numpy(np.float32)
    cache = {"embeddings": np.full((total, 1024), np.nan, np.float32),
             "labels_5class": labels, "age": age, "sex": sex,
             "ecg_id": ids, "strat_fold": frame.strat_fold.to_numpy(np.int8),
             "label_valid": frame.label_valid.to_numpy(bool),
             "processed_mask": np.zeros(total, bool)}
    if path.is_file():
        with np.load(path, allow_pickle=False) as old:
            old_ids = old["ecg_id"]
            positions = np.searchsorted(ids, old_ids)
            if np.any(positions >= total) or not np.array_equal(ids[positions], old_ids):
                raise ValueError("Cached PTB-XL IDs do not match source metadata")
            vectors = old["embeddings"]
            good = np.isfinite(vectors).all(axis=1)
            if "processed_mask" in old.files:
                good &= old["processed_mask"].astype(bool)
            cache["embeddings"][positions[good]] = vectors[good]
            cache["processed_mask"][positions[good]] = True
    return cache


def save_cache(path: Path, cache: dict[str, np.ndarray]) -> None:
    temporary = path.with_name("ptbxl_cached_embeddings.tmp.npz")
    # Keep aliases for the existing fast-head tooling.
    content = {**cache, "targets": cache["labels_5class"],
               "split": np.where(cache["strat_fold"] == 10, "test",
                                 np.where(cache["strat_fold"] == 9, "val", "train")),
               "labels": np.asarray(LABELS)}
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **content)
    os.replace(temporary, path)


def status(models: Path, cache: dict, started: float, phase: str, **extra) -> None:
    done = int(cache["processed_mask"].sum())
    total = len(cache["ecg_id"])
    elapsed = max(time.monotonic() - started, 0.01)
    new = max(done - int(extra.get("initial_records", 0)), 0)
    eta = (total - done) * elapsed / new / 60 if new else None
    payload = {"phase": phase, "pid": os.getpid(), "processed_records": done,
               "total_records": total, "percent_complete": round(100 * done / total, 3),
               "eta_minutes": round(eta, 1) if eta is not None else None,
               "last_updated": datetime.now(timezone.utc).isoformat(), **extra}
    atomic_json(models / "slow_train_status.json", payload)
    print(json.dumps(payload), flush=True)


def scores(y: np.ndarray, p: np.ndarray) -> dict:
    auc = [roc_auc_score(y[:, j], p[:, j]) for j in range(y.shape[1]) if len(np.unique(y[:, j])) == 2]
    return {"macro_auroc": float(np.mean(auc)) if auc else None,
            "macro_f1_at_0_5": float(f1_score(y, p >= .5, average="macro", zero_division=0)),
            "rows": len(y)}


def train_ptb_head(cache: dict, models: Path, epochs: int) -> dict:
    mask = cache["processed_mask"] & cache["label_valid"]
    fold = cache["strat_fold"]
    train = np.flatnonzero(mask & (fold <= 8))
    val = np.flatnonzero(mask & (fold == 9))
    test = np.flatnonzero(mask & (fold == 10))
    if not len(train) or len(val) < 30 or len(test) < 30:
        return {"skipped": "Insufficient labeled records in official folds"}
    vectors = cache["embeddings"]
    mean = vectors[train].mean(axis=0)
    scale = np.maximum(vectors[train].std(axis=0), 1e-5)
    age = cache["age"]
    age_median = float(np.nanmedian(age[train]))
    def make_x(ix):
        auxiliary = np.column_stack(((np.nan_to_num(age[ix], nan=age_median) - 55) / 20,
                                     np.nan_to_num(cache["sex"][ix], nan=0.5)))
        return torch.from_numpy(np.column_stack(((vectors[ix] - mean) / scale, auxiliary)).astype(np.float32))
    x_train, x_val, x_test = make_x(train), make_x(val), make_x(test)
    y_train = torch.from_numpy(cache["labels_5class"][train])
    y_val, y_test = cache["labels_5class"][val], cache["labels_5class"][test]
    model = nn.Sequential(nn.Linear(1026, 256), nn.SiLU(), nn.Dropout(.15), nn.Linear(256, 5))
    optimizer = torch.optim.AdamW(model.parameters(), lr=4e-4, weight_decay=1e-3)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    best = None
    best_state = None
    for epoch in range(epochs):
        model.train()
        for ix in torch.randperm(len(train)).split(128):
            logits = model(x_train[ix])
            target = y_train[ix]
            bce = nn.functional.binary_cross_entropy_with_logits(logits, target, reduction="none")
            prob = logits.sigmoid()
            pt = prob * target + (1 - prob) * (1 - target)
            loss = (bce * (1 - pt).pow(torch.where(target > 0, 1.0, 3.0))).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            time.sleep(.01)
        schedule.step()
        model.eval()
        with torch.inference_mode():
            p = torch.cat([model(x).sigmoid() for x in x_val.split(512)]).numpy()
        metric = scores(y_val, p)
        if best is None or (metric["macro_auroc"] or 0) > (best["macro_auroc"] or 0):
            best = metric
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()
    with torch.inference_mode():
        test_p = torch.cat([model(x).sigmoid() for x in x_test.split(512)]).numpy()
    tested = scores(y_test, test_p)
    candidate = {"state_dict": best_state, "mean": mean.astype(np.float32),
                 "scale": scale.astype(np.float32), "age_median": age_median,
                 "labels": LABELS, "input_dim": 1026, "validation": best,
                 "test": tested, "subset_size": int(mask.sum())}
    old_path = models / "ptbxl_superclass_head.pt"
    old_auc = -1.0
    old_f1 = -1.0
    if old_path.is_file():
        old = torch.load(old_path, map_location="cpu", weights_only=False)
        old_metric = old.get("validation", {})
        old_auc = float(old_metric.get("macro_auroc", old.get("validation_macro_auroc", -1)))
        old_f1 = float(old_metric.get("macro_f1_at_0_5", -1))
    promoted = (best["macro_auroc"] or 0) > old_auc or best["macro_f1_at_0_5"] > old_f1
    if promoted:
        atomic_torch(old_path, candidate)
        metric_path = models / "research_metrics.json"
        metrics = json.loads(metric_path.read_text()) if metric_path.is_file() else {}
        metrics["ptbxl_superclasses"] = {"validation": best, "test": tested,
                                          "cached_records": int(cache["processed_mask"].sum()),
                                          "labeled_records": int(mask.sum()), "labels": LABELS}
        atomic_json(metric_path, metrics)
    return {"validation": best, "test": tested, "promoted": promoted}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--sleep-ms", type=int, default=100)
    parser.add_argument("--chunk-size", type=int, default=250)
    parser.add_argument("--head-epochs", type=int, default=15)
    args = parser.parse_args()
    if args.batch_size < 1 or args.sleep_ms < 0 or args.chunk_size < 1:
        parser.error("Batch size and chunk size must be positive; sleep must be nonnegative")
    lower_priority()
    models = args.project_root / "models"
    models.mkdir(exist_ok=True)
    frame = prepare_manifest(args.project_root)
    cache_path = models / "ptbxl_cached_embeddings.npz"
    cache = load_cache(frame, cache_path)
    initial = int(cache["processed_mask"].sum())
    started = time.monotonic()
    status(models, cache, started, "loading_encoder", initial_records=initial)
    encoder = load_official_founder(args.project_root / "pretrained/ECGFounder/12_lead_ECGFounder.pth",
                                    Path(__file__).parent / "vendor/ECGFounder")
    encoder.eval()
    remaining = np.flatnonzero(~cache["processed_mask"])
    failed = []
    since_train = 0
    for offset in range(0, len(remaining), args.chunk_size):
        indices = remaining[offset:offset + args.chunk_size]
        for part in np.array_split(indices, math.ceil(len(indices) / args.batch_size)):
            signals = []
            accepted = []
            for ix in part:
                try:
                    signals.append(load_ecg((args.project_root / "ptb-xl-1.0.1" / frame.iloc[ix].filename_hr).with_suffix(".hea")))
                    accepted.append(ix)
                except (OSError, ValueError) as error:
                    failed.append({"ecg_id": int(cache["ecg_id"][ix]), "error": str(error)[:160]})
            if accepted:
                with torch.inference_mode():
                    _, features = encoder(torch.from_numpy(np.stack(signals)))
                cache["embeddings"][accepted] = features.numpy()
                cache["processed_mask"][accepted] = True
            time.sleep(args.sleep_ms / 1000)
        save_cache(cache_path, cache)
        new_count = int(cache["processed_mask"].sum()) - initial
        status(models, cache, started, "extracting", initial_records=initial,
               newly_cached=new_count, failed_records=failed[-10:], failed_count=len(failed))
        since_train += len(indices)
        if since_train >= 2000 or offset + args.chunk_size >= len(remaining):
            status(models, cache, started, "training_ptb_head", initial_records=initial,
                   newly_cached=new_count, failed_count=len(failed))
            result = train_ptb_head(cache, models, args.head_epochs)
            from .mimic_adapter import train_mimic_adapter
            try:
                mimic_result = train_mimic_adapter(args.project_root)
            except Exception as error:
                mimic_result = {"error": f"{type(error).__name__}: {error}"}
                print(json.dumps({"mimic_adapter_error": mimic_result["error"]}), flush=True)
            status(models, cache, started, "extracting", initial_records=initial,
                   newly_cached=new_count, ptb_head=result, mimic_adapter=mimic_result,
                   failed_count=len(failed))
            since_train = 0
    status(models, cache, started, "complete" if not failed else "complete_with_errors",
           initial_records=initial, newly_cached=int(cache["processed_mask"].sum()) - initial,
           failed_records=failed, failed_count=len(failed))


if __name__ == "__main__":
    main()
