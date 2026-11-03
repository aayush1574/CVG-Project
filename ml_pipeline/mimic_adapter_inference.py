"""Runtime-only projection adapter and probability calibration."""
from __future__ import annotations

import numpy as np
import torch
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


def apply_adapter_calibration(logits: np.ndarray, rules: list[dict]) -> np.ndarray:
    out = 1 / (1 + np.exp(-np.clip(logits, -50, 50)))
    for j, rule in enumerate(rules):
        if rule["method"] == "temperature":
            out[:, j] = 1 / (1 + np.exp(-np.clip(logits[:, j] / rule["temperature"], -50, 50)))
        elif rule["method"] == "isotonic":
            out[:, j] = np.interp(out[:, j], rule["x"], rule["y"])
    return out
