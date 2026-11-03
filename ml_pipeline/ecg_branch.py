"""ECG loading and the official ECGFounder encoder adapter."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt

LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")
LIMB_LEADS = LEADS[:6]


def detect_lead_mode(waveform: np.ndarray) -> dict:
    """Identify supported non-flat lead patterns after preprocessing."""
    x = np.asarray(waveform)
    if x.shape != (12, 5000):
        raise ValueError("ECG waveform must be 12 by 5000 after preprocessing")
    active = np.std(x, axis=1) > .01
    count = int(active.sum())
    if count == 12:
        return {"mode": "12-lead", "active_leads": list(LEADS), "lead_mask": active.astype(int).tolist()}
    if count == 6 and active[:6].all() and not active[6:].any():
        return {"mode": "6-lead", "active_leads": list(LIMB_LEADS), "lead_mask": active.astype(int).tolist()}
    if count == 1 and active[0]:
        return {"mode": "1-lead", "active_leads": ["I"], "lead_mask": active.astype(int).tolist()}
    raise ValueError("Supported ECG lead patterns are standard 12-lead, six limb leads, or lead I alone")


def preprocess(signal: np.ndarray, sample_rate: int, lead_names=LEADS) -> np.ndarray:
    if sample_rate <= 0 or sample_rate < 100:
        raise ValueError("Sample rate must be at least 100 Hz")
    x = np.asarray(signal, dtype=np.float32)
    supplied = [str(name).upper() for name in lead_names]
    standard = [name.upper() for name in LEADS]
    allowed = (set(standard), set(standard[:6]), {"I"})
    if x.ndim != 2 or x.shape[1] != len(supplied) or len(set(supplied)) != len(supplied) or set(supplied) not in allowed:
        raise ValueError("Expected standard 12 leads, six limb leads, or lead I alone")
    if not np.isfinite(x).all():
        raise ValueError("ECG contains non-finite values")
    reordered = np.zeros((len(x), 12), np.float32)
    for index, name in enumerate(standard):
        if name in supplied:
            reordered[:, index] = x[:, supplied.index(name)]
    x = reordered
    from math import gcd
    divisor = gcd(sample_rate, 500)
    x = resample_poly(x, 500 // divisor, sample_rate // divisor, axis=0)
    if len(x) < 5000:
        x = np.pad(x, ((0, 5000 - len(x)), (0, 0)))
    x = x[:5000]
    sos = butter(4, [0.5, 45], btype="bandpass", fs=500, output="sos")
    x = sosfiltfilt(sos, x, axis=0)
    mean = x.mean(axis=0, keepdims=True)
    std = x.std(axis=0, keepdims=True)
    return ((x - mean) / np.maximum(std, 1e-6)).T.astype(np.float32)


def load_ecg(path: str | Path, sample_rate: int | None = None, processor=preprocess) -> np.ndarray:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".hea", ".dat"}:
        import wfdb
        record = wfdb.rdrecord(str(path.with_suffix("")))
        return processor(record.p_signal, int(record.fs), tuple(record.sig_name))
    if suffix == ".npy":
        if sample_rate is None:
            raise ValueError("sample_rate is required for .npy")
        array = np.load(path, allow_pickle=False)
        names = {1: ("I",), 6: LIMB_LEADS, 12: LEADS}.get(array.shape[1] if array.ndim == 2 else -1)
        if names is None:
            raise ValueError("NPY needs [samples, 1], [samples, 6], or [samples, 12]")
        return processor(array, sample_rate, names)
    if suffix == ".csv":
        if sample_rate is None:
            raise ValueError("sample_rate is required for .csv")
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                raise ValueError("CSV needs named ECG lead columns")
            present = {name.strip().upper(): name for name in reader.fieldnames}
            if len(present) != len(reader.fieldnames):
                raise ValueError("Duplicate ECG column names")
            names = tuple(name for name in LEADS if name.upper() in present)
            if set(names) not in (set(LEADS), set(LIMB_LEADS), {"I"}):
                raise ValueError("CSV needs standard 12 leads, six limb leads, or lead I")
            data = np.array([[float(row[present[lead.upper()]]) for lead in names] for row in reader], dtype=np.float32)
        return processor(data, sample_rate, names)
    raise ValueError("Supported waveform formats: .hea/.dat pair, .npy, .csv")


def digitize_ecg_image(path: str | Path) -> tuple[np.ndarray, dict]:
    """Digitize paper in mV, then normalize for the frozen ECGFounder encoder."""
    from .ecg_digitizer import digitize_image
    millivolts, quality = digitize_image(path)
    quality["preview_millivolts"] = {lead: millivolts[i, ::25].round(3).tolist()
                                   for i, lead in enumerate(LEADS)}
    return preprocess(millivolts.T, 500, LEADS), quality


def load_official_founder(checkpoint: str | Path, source_dir: str | Path):
    """Load upstream architecture without reimplementing checkpoint-sensitive layers."""
    import torch
    source = Path(source_dir)
    if not (source / "net1d.py").is_file():
        raise FileNotFoundError("Clone https://github.com/PKUDigitalHealth/ECGFounder into " + str(source))
    sys.path.insert(0, str(source))
    from net1d import Net1D
    model = Net1D(in_channels=12, base_filters=64, ratio=1,
                  filter_list=[64, 160, 160, 400, 400, 1024, 1024],
                  m_blocks_list=[2, 2, 2, 3, 3, 4, 4], kernel_size=16, stride=2,
                  groups_width=16, use_bn=False, use_do=False, return_features=True,
                  verbose=False, n_classes=150)
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state = state.get("state_dict", state) if isinstance(state, dict) else state
    state = {k.removeprefix("module."): v for k, v in state.items() if not k.removeprefix("module.").startswith("dense.")}
    missing, unexpected = model.load_state_dict(state, strict=False)
    if set(missing) != {"dense.weight", "dense.bias"} or unexpected:
        raise ValueError(f"ECGFounder checkpoint mismatch: missing={missing}, unexpected={unexpected}")
    model.eval()
    return model
